"""
L1-Trigger: mistake-analyzer
错题分析器 - 监听错题记录的创建和更新事件，自动分析并完善错题信息

Event Trigger: 
- databases.*.collections.mistake_records.documents.*.create
- databases.*.collections.mistake_records.documents.*.update

新设计：一条错题记录 = 一道题 = 一张图片

工作流程:
1. Flutter 端上传图片到 bucket，为每张图片创建一个 mistake_record (analysisStatus: "pending")
2. 本 function 被自动触发（create 事件）
3. 下载图片 -> OCR 分析 -> 创建题目 -> 更新错题记录
4. 更新 analysisStatus 为 "completed" 或 "failed"
5. Flutter 端通过 Realtime API 订阅更新，实时显示分析结果
"""
import os
import json
import asyncio
from datetime import datetime
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.exception import AppwriteException

from workers.mistake_analyzer.image_analyzer import extract_question_content, analyze_subject_and_knowledge_points
from workers.mistake_analyzer.question_service import create_question
from workers.mistake_analyzer.knowledge_point_service import ensure_knowledge_point, ensure_module, add_question_to_knowledge_point
from workers.mistake_analyzer.profile_stats_service import update_profile_stats_on_mistake_created
from workers.mistake_analyzer.utils import get_databases, get_storage


# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
MISTAKE_RECORDS_COLLECTION = 'mistake_records'
QUESTIONS_COLLECTION = 'questions'
ORIGIN_IMAGE_BUCKET = 'origin_question_image'


async def update_record_status(databases: Databases, record_id: str, status: str, error: str = None, update_data: dict = None):
    """更新错题记录的分析状态（异步）"""
    update_payload = {
        'analysisStatus': status,
    }
    
    if status == 'completed':
        update_payload['analyzedAt'] = datetime.utcnow().isoformat() + 'Z'
    
    if error:
        update_payload['analysisError'] = error[:1000]  # 限制错误信息长度
    
    if update_data:
        update_payload.update(update_data)
    
    try:
        # 在线程池中执行同步的数据库操作
        await asyncio.to_thread(
            databases.update_document,
            database_id=DATABASE_ID,
            collection_id=MISTAKE_RECORDS_COLLECTION,
            document_id=record_id,
            data=update_payload
        )
    except Exception as e:
        print(f"更新记录状态失败: {str(e)}")


def download_image_from_storage(storage: Storage, file_id: str) -> bytes:
    """从 storage bucket 下载图片"""
    try:
        result = storage.get_file_download(
            bucket_id=ORIGIN_IMAGE_BUCKET,
            file_id=file_id
        )
        return result
    except Exception as e:
        raise ValueError(f"下载图片失败: {str(e)}")


async def process_mistake_analysis(record_data: dict, databases: Databases, storage: Storage):
    """
    处理错题分析的核心逻辑 - 简化版：一条记录 = 一道题
    
    Args:
        record_data: 错题记录文档数据
        databases: Databases 服务实例
        storage: Storage 服务实例
    """
    record_id = record_data['$id']
    user_id = record_data['userId']
    original_image_id = record_data.get('originalImageId')
    
    # 验证必要字段
    if not original_image_id:
        raise ValueError("错题记录缺少图片ID")
    
    # 1. 更新状态为 processing
    await update_record_status(databases, record_id, 'processing')
    print(f"✓ 状态更新为 processing")
    
    try:
        # 2. 下载图片并转换为 base64
        print(f"下载图片: {original_image_id}")
        image_bytes = download_image_from_storage(storage, original_image_id)
        import base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 3. 第一步：OCR 提取题目内容和学科识别
        print("开始OCR识别和学科识别...")
        step1_result = await extract_question_content(image_base64)
        print(f"✓ OCR完成，题目类型: {step1_result.get('type', '未知')}，学科: {step1_result.get('subject', '未知')}")
        
        # 3.1 创建基本题目记录（包含 OCR 提取的内容和学科）
        print("创建基本题目记录...")
        basic_question = await asyncio.to_thread(
            create_question,
            databases=databases,
            subject=step1_result['subject'],  # 第一步已识别学科
            module_ids=[],      # 暂时为空，后续会更新
            knowledge_point_ids=[],  # 暂时为空，后续会更新
            content=step1_result['content'],
            question_type=step1_result['type'],
            difficulty=3,
            options=step1_result.get('options'),
            answer='',
            explanation='',
            image_ids=[original_image_id],
            created_by=user_id,
            source='ocr'
        )
        question_id = basic_question['$id']
        print(f"✓ 创建基本题目: {question_id}")
        
        # 3.2 OCR 完成，更新状态为 ocrOK 并关联题目ID和学科
        await update_record_status(
            databases, 
            record_id, 
            'ocrOK',
            update_data={
                'questionId': question_id,
                'subject': step1_result['subject']  # 同时更新学科信息
            }
        )
        print(f"✓ 状态更新为 ocrOK，题目ID: {question_id}，学科: {step1_result['subject']}")
        
        # 4. 第二步：分析模块和知识点（学科已在第一步识别）
        print("开始分析模块和知识点...")
        step2_result = await analyze_subject_and_knowledge_points(
            content=step1_result['content'],
            question_type=step1_result['type'],
            subject=step1_result['subject'],  # 从第一步获取学科
            user_id=user_id,
            databases=databases
        )
        
        # 合并两步的结果
        analysis_result = {
            **step1_result,
            **step2_result,
            'answer': '',
            'explanation': '',
            'difficulty': 3,
            'userAnswer': '',
            'confidence': 0.85
        }
        
        # 5. 获取 AI 识别的学科
        subject = analysis_result.get('subject')
        if not subject:
            raise ValueError("未能识别学科")
        
        # 6. 确保所有模块存在（支持多模块）
        module_ids = []
        modules = analysis_result.get('modules', [])
        
        if not modules:
            raise ValueError("未能识别模块")
        
        for module_name in modules:
            module_info = await asyncio.to_thread(
                ensure_module,
                databases=databases,
                subject=subject,
                module_name=module_name,
                user_id=user_id
            )
            module_ids.append(module_info['$id'])
        
        print(f"✓ 识别到 {len(modules)} 个模块: {', '.join(modules)}")
        
        # 7. 确保所有知识点都存在
        knowledge_points = analysis_result.get('knowledgePoints', [])
        
        if not knowledge_points:
            raise ValueError("未能识别知识点")
        
        knowledge_point_ids = []
        for kp_info in knowledge_points:
            kp_name = kp_info['name']
            kp_module_id = kp_info['moduleId']
            
            kp_doc = await asyncio.to_thread(
                ensure_knowledge_point,
                databases=databases,
                user_id=user_id,
                subject=subject,
                module_id=kp_module_id,
                knowledge_point_name=kp_name,
                description=None
            )
            knowledge_point_ids.append(kp_doc['$id'])
        
        print(f"✓ 识别到 {len(knowledge_points)} 个知识点")
        
        # 8. 更新题目，补充模块和知识点信息（学科已在创建时设置）
        print(f"更新题目信息: {question_id}")
        print(f"   - moduleIds: {module_ids}")
        print(f"   - knowledgePointIds: {knowledge_point_ids}")
        
        updated_question = await asyncio.to_thread(
            databases.update_document,
            database_id=DATABASE_ID,
            collection_id=QUESTIONS_COLLECTION,
            document_id=question_id,
            data={
                'moduleIds': module_ids,
                'knowledgePointIds': knowledge_point_ids
            }
        )
        print(f"✓ 成功更新题目: {question_id}")
        print(f"   - 更新后 subject: {updated_question.get('subject')}")
        print(f"   - 更新后 moduleIds: {updated_question.get('moduleIds')}")
        print(f"   - 更新后 knowledgePointIds: {updated_question.get('knowledgePointIds')}")
        
        # 9. 更新所有关联知识点，添加此题目ID
        for kp_id in knowledge_point_ids:
            try:
                await asyncio.to_thread(
                    add_question_to_knowledge_point,
                    databases=databases,
                    kp_id=kp_id,
                    question_id=question_id
                )
            except Exception as e:
                print(f"⚠️ 更新知识点 {kp_id} 的题目列表失败: {str(e)}")
                # 不影响主流程，继续执行
        
        # 10. 更新错题记录（补充模块和知识点信息）
        update_data = {
            'moduleIds': module_ids,
            'knowledgePointIds': knowledge_point_ids,
        }
        
        # 11. 更新状态为 completed
        await update_record_status(
            databases=databases,
            record_id=record_id,
            status='completed',
            update_data=update_data
        )
        
        # 12. 更新用户档案统计数据
        try:
            await asyncio.to_thread(
                update_profile_stats_on_mistake_created,
                databases=databases,
                user_id=user_id
            )
        except Exception as e:
            # 统计更新失败不影响主流程
            print(f"⚠️ 更新用户统计数据失败: {str(e)}")
        
        print(f"\n✅ 错题分析完成: {record_id}")
        print(f"   - 题目ID: {question_id}")
        print(f"   - 学科: {subject}")
        print(f"   - 模块数: {len(module_ids)}")
        print(f"   - 知识点数: {len(knowledge_point_ids)}")
        
    except Exception as e:
        # 分析失败，更新状态为 failed
        error_message = str(e)
        print(f"❌ 错题分析失败: {error_message}")
        await update_record_status(
            databases=databases,
            record_id=record_id,
            status='failed',
            error=error_message
        )
        raise


def main(context):
    """Main entry point for Appwrite Event Trigger"""
    try:
        req = context.req
        
        # 解析 event 数据
        event_body = req.body
        if isinstance(event_body, str):
            event_data = json.loads(event_body)
        else:
            event_data = event_body
        
        context.log(f"收到事件: {json.dumps(event_data, ensure_ascii=False)[:500]}")
        
        record_data = event_data
        
        # 检查是否需要分析（只处理 pending 状态）
        analysis_status = record_data.get('analysisStatus', 'pending')
        
        if analysis_status != 'pending':
            context.log(f"⏭️  跳过分析: 状态是 {analysis_status}")
            return context.res.empty()
        
        # 初始化服务
        databases = get_databases()
        storage = get_storage()
        
        # 执行分析
        process_mistake_analysis(record_data, databases, storage)
        
        context.log("✅ 分析完成")
        return context.res.empty()
        
    except Exception as e:
        context.error(f"❌ 处理失败: {str(e)}")
        return context.res.empty()
