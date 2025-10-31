"""
L1-Trigger: mistake-analyzer
错题分析器 - 监听错题记录的创建和更新事件，自动分析并完善错题信息

Event Trigger: 
- databases.*.collections.mistake_records.documents.*.create
- databases.*.collections.mistake_records.documents.*.update

工作流程:
1. Flutter 端上传图片到 bucket，创建 mistake_record (analysisStatus: "pending")
2. 本 function 被自动触发（create 事件）
3. 下载图片 -> OCR 分析 -> 创建题目 -> 更新错题记录
4. 更新 analysisStatus 为 "completed" 或 "failed"
5. Flutter 端通过 Realtime API 订阅更新，实时显示分析结果

重新分析:
1. Flutter 端更新 mistake_record 的 analysisStatus 为 "pending"
2. 本 function 被自动触发（update 事件）
3. 重新执行分析流程
"""
import os
import json
from datetime import datetime
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.exception import AppwriteException

from .image_analyzer import analyze_mistake_image
from .question_service import create_question
from .knowledge_point_service import ensure_knowledge_point, ensure_module
from .utils import get_databases, get_storage


# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
MISTAKE_RECORDS_COLLECTION = 'mistake_records'
ORIGIN_IMAGE_BUCKET = 'origin_question_image'


def update_record_status(databases: Databases, record_id: str, status: str, error: str = None, update_data: dict = None):
    """更新错题记录的分析状态"""
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
        databases.update_document(
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
        # 获取文件内容
        result = storage.get_file_download(
            bucket_id=ORIGIN_IMAGE_BUCKET,
            file_id=file_id
        )
        return result
    except Exception as e:
        raise ValueError(f"下载图片失败: {str(e)}")


def process_mistake_analysis(record_data: dict, databases: Databases, storage: Storage):
    """
    处理错题分析的核心逻辑
    
    Args:
        record_data: 错题记录文档数据
        databases: Databases 服务实例
        storage: Storage 服务实例
    """
    record_id = record_data['$id']
    user_id = record_data['userId']
    original_image_ids = record_data.get('originalImageIds', [])
    
    # 验证必要字段
    if not original_image_ids or len(original_image_ids) == 0:
        raise ValueError("错题记录缺少图片")
    
    # 1. 更新状态为 processing
    update_record_status(databases, record_id, 'processing')
    
    try:
        # 2. 下载第一张图片（目前只处理第一张）
        # originalImageIds 存储的是 fileId，图片已经在 bucket 中
        file_id = original_image_ids[0]
        
        # 下载图片并转换为 base64
        try:
            image_bytes = download_image_from_storage(storage, file_id)
            # 转换为 base64
            import base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        except Exception as e:
            raise ValueError(f"无法下载图片 {file_id}: {str(e)}")
        
        # 3. 分析图片（使用 LLM 视觉能力）
        # AI 会自动识别学科、模块和知识点
        analysis_result = analyze_mistake_image(
            image_base64=image_base64,
            databases=databases
        )
        
        """
        analysis_result 结构:
        {
            'subject': str,                 # 学科（AI 识别）
            'content': str,                 # 题目内容（Markdown格式）
            'type': str,                    # 题目类型
            'module': str,                  # 模块名称
            'knowledgePointNames': list,    # 知识点名称列表
            'options': list,                # 选项（选择题）
            'answer': str,                  # 正确答案
            'explanation': str,             # 解析
            'difficulty': int,              # 难度 1-5
            'userAnswer': str,              # 用户的错误答案
            'errorReason': str,             # 错误原因
            'confidence': float             # 识别置信度
        }
        
        注意：
        - 原始错题图片ID存储在 mistake_record 的 originalImageIds 字段中
        - 创建题目时，使用 originalImageIds 作为题目的 imageIds
        """
        
        # 4. 获取 AI 识别的学科
        subject = analysis_result.get('subject')
        if not subject:
            raise ValueError("未能识别学科")
        
        # 5. 确保模块存在
        module_name = analysis_result.get('module')
        if not module_name:
            raise ValueError("未能识别模块")
        
        module_info = ensure_module(
            databases=databases,
            subject=subject,
            module_name=module_name
        )
        
        # 6. 确保所有知识点都存在
        knowledge_point_names = analysis_result.get('knowledgePointNames', [])
        if not knowledge_point_names:
            raise ValueError("未能识别知识点")
        
        knowledge_point_ids = []
        
        for kp_name in knowledge_point_names:
            kp_info = ensure_knowledge_point(
                databases=databases,
                user_id=user_id,
                subject=subject,
                module_id=module_info['$id'],
                knowledge_point_name=kp_name,
                description=None
            )
            knowledge_point_ids.append(kp_info['$id'])
        
        # 7. 创建题目
        # 使用原始错题图片ID作为题目的imageIds
        question = create_question(
            databases=databases,
            subject=subject,
            module_ids=[module_info['$id']],
            knowledge_point_ids=knowledge_point_ids,
            content=analysis_result['content'],
            question_type=analysis_result['type'],
            difficulty=analysis_result.get('difficulty', 3),
            options=analysis_result.get('options'),
            answer=analysis_result.get('answer'),
            explanation=analysis_result.get('explanation'),
            image_ids=original_image_ids,  # 使用原始错题图片ID
            created_by=user_id,
            source='ocr'
        )
        
        # 8. 更新错题记录（完善信息，包括 AI 识别的学科）
        update_data = {
            'subject': subject,                         # AI 识别的学科
            'questionId': question['$id'],
            'moduleIds': [module_info['$id']],
            'knowledgePointIds': knowledge_point_ids,
            'errorReason': analysis_result.get('errorReason', 'other'),
        }
        
        # 如果分析结果包含用户答案，也更新
        if analysis_result.get('userAnswer'):
            update_data['userAnswer'] = analysis_result['userAnswer']
        
        # 9. 更新状态为 completed
        update_record_status(
            databases=databases,
            record_id=record_id,
            status='completed',
            update_data=update_data
        )
        
        print(f"✅ 错题分析完成: {record_id}")
        print(f"   - 题目ID: {question['$id']}")
        print(f"   - 模块: {module_name}")
        print(f"   - 知识点: {', '.join(knowledge_point_names)}")
        
    except Exception as e:
        # 分析失败，更新状态为 failed
        error_message = str(e)
        print(f"❌ 错题分析失败: {error_message}")
        update_record_status(
            databases=databases,
            record_id=record_id,
            status='failed',
            error=error_message
        )
        raise


def main(context):
    """Main entry point for Appwrite Event Trigger"""
    try:
        # Event trigger 的数据在 req.body 中
        req = context.req
        
        # 解析 event 数据
        # Appwrite event 的数据格式: 直接是文档数据
        event_body = req.body
        
        if isinstance(event_body, str):
            event_data = json.loads(event_body)
        else:
            event_data = event_body
        
        context.log(f"收到事件: {json.dumps(event_data, ensure_ascii=False)[:500]}")
        
        # 获取创建的文档数据
        # Event trigger 直接提供文档数据
        record_data = event_data
        
        # 检查是否需要分析（只处理 pending 状态）
        analysis_status = record_data.get('analysisStatus', 'pending')
        
        if analysis_status != 'pending':
            context.log(f"⏭️  跳过分析: 状态是 {analysis_status}，不需要处理")
            return context.res.empty()
        
        # 避免重复触发：如果已经在 processing 状态，说明正在处理中
        if analysis_status == 'processing':
            context.log(f"⏭️  跳过分析: 正在处理中")
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
        # Event trigger 失败不应该返回错误响应，只记录日志
        return context.res.empty()

