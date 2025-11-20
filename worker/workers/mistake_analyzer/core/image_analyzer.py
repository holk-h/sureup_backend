"""
图片分析模块
负责处理错题图片的 AI 视觉分析

使用 LLM 的视觉能力直接分析图片，提取题目信息并转换为 Markdown 格式

内部统一使用 base64 格式处理图片
图片已由 Flutter 端上传到 bucket，此模块只负责分析
"""
import os
import asyncio
import base64
import cv2
import numpy as np
from typing import Dict, List, Optional
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.id import ID
from appwrite.input_file import InputFile

from workers.mistake_analyzer.core.llm_provider import get_llm_provider
from workers.mistake_analyzer.core.parsers import parse_segmented_response, parse_knowledge_points_response
from workers.mistake_analyzer.helpers.appwrite_helpers import (
    get_existing_modules,
    get_existing_knowledge_points_by_module
)
from workers.mistake_analyzer.helpers.utils import get_subject_chinese_name
from workers.mistake_analyzer.services.knowledge_point_service import get_user_knowledge_points_by_subject
from workers.mistake_analyzer.core.prompts import (
    get_ocr_system_prompt,
    get_ocr_user_prompt,
    build_user_feedback_section,
    build_multi_image_hint,
    get_knowledge_points_system_prompt,
    get_knowledge_points_user_prompt,
    build_modules_hint,
    build_existing_kp_hint
)


# 常量配置
QUESTION_TYPES = ['choice', 'fillBlank', 'shortAnswer', 'essay']


# ============= 工具函数 =============

def get_storage() -> Storage:
    """Initialize Storage service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Storage(client)

def clean_base64(image_base64: str) -> str:
    """
    清理 base64 字符串，去除 data:image 前缀
    
    Args:
        image_base64: 可能包含前缀的 base64 字符串
        
    Returns:
        纯 base64 字符串
    """
    if ',' in image_base64:
        return image_base64.split(',', 1)[1]
    return image_base64


def create_fallback_result(subject: str, error_msg: str = '') -> Dict:
    """创建失败时的占位结果"""
    return {
        'content': f'分析失败: {error_msg}' if error_msg else '题目识别失败，请重试',
        'type': 'shortAnswer',
        'subject': subject,
        'modules': ['未分类'],
        'moduleIds': [],
        'knowledgePoints': [{'name': '未分类', 'module': '未分类', 'moduleId': None}],
        'options': [],
        'answer': '',
        'explanation': '',
        'difficulty': 3,
        'userAnswer': '',
        'confidence': 0.0,
        'error': error_msg
    }


def _normalize_module_name(module_name: str) -> str:
    """规范化模块名，去除括号和冒号后的描述"""
    if '(' in module_name or '（' in module_name:
        module_name = module_name.split('(')[0].split('（')[0].strip()
    if '：' in module_name or ':' in module_name:
        module_name = module_name.split('：')[0].split(':')[0].strip()
    return module_name


async def crop_and_upload_image(
    image_base64: str,
    bbox: List[int],
    subject: str
) -> Optional[str]:
    """
    根据 bbox 裁剪图片并上传到 storage
    
    Args:
        image_base64: 原始图片 base64 (无前缀)
        bbox: [x1, y1, x2, y2] 归一化坐标 (0-1000)
        subject: 学科代码
        
    Returns:
        str: 上传后的 file_id, 失败返回 None
    """
    try:
        # 1. 解码图片
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            print("❌ 图片解码失败")
            return None
            
        h, w = image.shape[:2]
        
        # 2. 转换坐标
        x1, y1, x2, y2 = bbox
        
        # 验证坐标范围
        if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
            print(f"⚠️ bbox 坐标无效: {bbox}")
            return None
            
        # 转换为实际像素坐标
        x_min = int(x1 * w / 1000)
        y_min = int(y1 * h / 1000)
        x_max = int(x2 * w / 1000)
        y_max = int(y2 * h / 1000)
        
        # 扩大一些边距 (5%)
        margin_x = int((x_max - x_min) * 0.05)
        margin_y = int((y_max - y_min) * 0.05)
        
        x_min = max(0, x_min - margin_x)
        y_min = max(0, y_min - margin_y)
        x_max = min(w, x_max + margin_x)
        y_max = min(h, y_max + margin_y)
        
        # 3. 裁剪
        cropped_image = image[y_min:y_max, x_min:x_max]
        
        if cropped_image.size == 0:
            print("❌ 裁剪结果为空")
            return None
            
        # 4. 编码为 JPEG
        _, encoded_image = cv2.imencode('.jpg', cropped_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        cropped_bytes = encoded_image.tobytes()
        
        # 5. 上传
        storage = get_storage()
        bucket_id = 'extracted_images' # 必须确保这个 bucket 存在
        file_id = ID.unique()
        file_name = f"extracted_{subject}_{file_id}.jpg"
        
        print(f"📤 正在上传提取的图片: {file_name}")
        
        await asyncio.to_thread(
            storage.create_file,
            bucket_id=bucket_id,
            file_id=file_id,
            file=InputFile.from_bytes(cropped_bytes, filename=file_name),
            permissions=['read("any")', 'update("users")', 'delete("users")']
        )
        
        print(f"✅ 图片提取并上传成功: {file_id}")
        return file_id
        
    except Exception as e:
        print(f"❌ 图片裁剪上传失败: {str(e)}")
        # 打印详细堆栈以便调试
        import traceback
        traceback.print_exc()
        return None


# ============= 主要功能函数 =============

async def analyze_mistake_image(
    image_base64: str,
    user_id: str,
    databases: Optional[Databases] = None,
    user_feedback: Optional[str] = None,
    previous_result: Optional[Dict] = None
) -> Dict:
    """
    分析错题图片并提取题目信息（异步）
    
    统一使用 base64 格式，图片已经在 bucket 中，不需要保存
    AI 会自动识别学科、模块和知识点
    
    Args:
        image_base64: 图片 base64 编码（纯 base64 或包含 data:image 前缀）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
        user_feedback: 用户反馈的错误原因（可选）
        previous_result: 上次识别的结果（可选）
        
    Returns:
        包含学科、题目内容、类型、模块、知识点等的字典
    """
    if not image_base64:
        raise ValueError("必须提供 image_base64")
    
    clean_image_base64 = clean_base64(image_base64)
    if not clean_image_base64:
        raise ValueError("图片数据无效")
    
    return await analyze_with_llm_vision(
        clean_image_base64, 
        user_id, 
        databases,
        user_feedback=user_feedback,
        previous_result=previous_result
    )


async def analyze_with_llm_vision(
    image_base64: str,
    user_id: str,
    databases: Optional[Databases] = None,
    user_feedback: Optional[str] = None,
    previous_result: Optional[Dict] = None
) -> Dict:
    """
    使用 LLM 两步分析法（内部函数，只接受 base64，异步）
    
    1. OCR：提取题目内容和格式
    2. 分析：识别学科、模块和知识点
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
        user_feedback: 用户反馈的错误原因（可选）
        previous_result: 上次识别的结果（可选）
    """
    try:
        step1 = await extract_question_content(
            image_base64,
            user_feedback=user_feedback,
            previous_result=previous_result
        )
        
        step2 = await analyze_subject_and_knowledge_points(
            content=step1['content'],
            question_type=step1['type'],
            subject=step1['subject'],
            user_id=user_id,
            databases=databases
        )
        
        return {
            **step1,
            **step2,
            'answer': '',
            'explanation': '',
            'difficulty': 3,
            'userAnswer': '',
            'confidence': 0.85
        }
        
    except Exception as e:
        print(f"LLM 分析失败: {str(e)}")
        return create_fallback_result('unknown', str(e))


async def extract_question_content(
    image_base64: [str, List[str]],
    user_feedback: Optional[str] = None,
    previous_result: Optional[Dict] = None
) -> Dict:
    """
    第一步：OCR 提取题目内容和学科识别（内部函数，异步）
    
    支持单图和多图（跨页题目）
    使用分段标记格式，避免 LaTeX 转义地狱
    
    Args:
        image_base64: 纯 base64 字符串或字符串列表（不含前缀）
                     - 单图：str
                     - 多图：List[str]（按页面顺序）
        user_feedback: 用户反馈的错误原因（可选）
        previous_result: 上次识别的结果（可选），包含 content, type, options, subject
        
    Returns:
        {'content': str, 'type': str, 'options': list, 'subject': str}
    """
    # 统一处理为列表格式
    if isinstance(image_base64, str):
        image_base64_list = [image_base64]
    else:
        image_base64_list = image_base64
    
    # 构建 prompt
    system_prompt = get_ocr_system_prompt()
    user_feedback_section = build_user_feedback_section(user_feedback, previous_result)
    multi_image_hint = build_multi_image_hint(len(image_base64_list))
    user_prompt = get_ocr_user_prompt(
        image_count=len(image_base64_list),
        multi_image_hint=multi_image_hint,
        user_feedback_section=user_feedback_section
    )

    # Agent 重试机制
    max_retries = 3
    llm = get_llm_provider()
    
    for attempt in range(max_retries):
        response = None
        try:
            if attempt == 0:
                print(f"开始OCR识别，共 {len(image_base64_list)} 张图片")
            else:
                print(f"🔄 第 {attempt + 1} 次重试...")
            
            response = await llm.chat_with_vision(
                prompt=user_prompt,
                image_base64=image_base64_list,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=32768,
                thinking={"type": "enabled"},
                reasoning_effort="low"
            )
            
            print(f"📋 LLM 返回的分段格式（前300字符）: {response[:300]}...")
            
            result = parse_segmented_response(response)
            
            print(f"✅ 分段格式解析成功！题目类型: {result.get('type', '未知')}, 学科: {result.get('subject', '未知')}")
            
            # 处理图片裁剪 (如果有 bboxes)
            image_ids = []
            if 'bboxes' in result and result['bboxes']:
                print(f"🖼️ 检测到 {len(result['bboxes'])} 个题目图片位置")
                for item in result['bboxes']:
                    img_idx = item.get('index', 0)
                    bbox = item.get('bbox')
                    
                    if 0 <= img_idx < len(image_base64_list):
                        target_image = image_base64_list[img_idx]
                        print(f"   - 处理第 {img_idx+1} 张图片的 bbox: {bbox}")
                        
                        image_id = await crop_and_upload_image(
                            target_image, 
                            bbox,
                            result.get('subject', 'unknown')
                        )
                        if image_id:
                            image_ids.append(image_id)
                    else:
                        print(f"⚠️ 图片索引 {img_idx} 超出范围 (共 {len(image_base64_list)} 张)")
            
            # 兼容旧代码 (如果 parser 只返回了 bbox)
            elif 'bbox' in result and result['bbox']:
                print(f"🖼️ 检测到题目图片 (单图模式)，bbox: {result['bbox']}")
                # 默认使用第一张图
                if image_base64_list:
                    image_id = await crop_and_upload_image(
                        image_base64_list[0], 
                        result['bbox'],
                        result.get('subject', 'unknown')
                    )
                    if image_id:
                        image_ids.append(image_id)
            
            if image_ids:
                result['imageIds'] = image_ids
            
            # 验证和规范化
            if 'content' not in result or not result['content']:
                raise ValueError("缺少题目内容")
            if 'type' not in result or result['type'] not in QUESTION_TYPES:
                result['type'] = 'shortAnswer'
            if not isinstance(result.get('options', []), list):
                result['options'] = []
            if 'subject' not in result or not result['subject']:
                result['subject'] = 'math'
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 题目提取失败（尝试 {attempt + 1}/{max_retries}）: {error_msg}")
            
            if attempt < max_retries - 1:
                # 构造格式化的错误反馈
                error_feedback = f"""⚠️ 你的上一次输出格式有错误，无法解析：

【错误信息】
{error_msg}

【要求的格式】
##TYPE##
题目类型（choice/fillBlank/shortAnswer/essay）

##SUBJECT##
学科代码（math/physics/chemistry/biology/chinese/english等）

##CONTENT##
题目内容（Markdown格式，LaTeX公式用 $ 或 $$ 包裹）

##OPTIONS##（选择题必需，其他题型可省略）
A. 选项1
B. 选项2
...

##END##

【你的输出】
{response[:500] if response else '无响应'}...

请严格按照上述格式重新输出，确保所有必需标记都存在。"""
                # 将错误反馈添加到聊天历史
                user_prompt = error_feedback
                print(f"📤 发送错误反馈给 LLM，准备重试...")
            else:
                # 最后一次尝试也失败了
                print(f"❌ 已达到最大重试次数，放弃")
                if response:
                    print(f"原始响应: {response[:500]}...")
                raise


async def analyze_subject_and_knowledge_points(
    content: str,
    question_type: str,
    subject: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    第二步：基于题目内容和学科识别模块和知识点（异步）
    
    根据用户学段提供相应的模块列表和知识点列表给 LLM
    
    核心功能：
    - 识别模块和知识点
    - 判断知识点的角色（category: primary/secondary/related）
    - 判断知识点的重要性（importance: high/basic/normal）
    - 生成解题提示
    
    Args:
        content: 题目内容（Markdown 格式）
        question_type: 题目类型
        subject: 学科代码（从第一步识别得到）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
        
    Returns:
        {
            'subject': str,
            'modules': list[str],
            'moduleIds': list[str],
            'knowledgePoints': list[dict],
            'primaryKnowledgePoints': list[dict],
            'solvingHint': str
        }
    """
    # 获取该学科在用户学段的模块列表
    available_modules = get_existing_modules(subject, user_id, databases)
    
    # 构建模块列表文本和ID映射
    modules_text = ""
    modules_dict = {}
    if available_modules:
        modules_list = []
        for mod in available_modules:
            modules_dict[mod['name']] = mod['$id']
            if mod.get('description'):
                modules_list.append(f"  - {mod['name']} ({mod['description']})")
            else:
                modules_list.append(f"  - {mod['name']}")
        modules_text = "\n".join(modules_list)
    
    # 获取用户在该学科下的所有已有知识点（防止重复）
    existing_knowledge_points = []
    if databases:
        print(f"🔍 [知识点查询] 开始查询用户知识点 - user_id: {user_id}, subject: {subject}")
        try:
            kp_docs = await asyncio.to_thread(
                get_user_knowledge_points_by_subject,
                databases=databases,
                user_id=user_id,
                subject=subject
            )
            existing_knowledge_points = kp_docs
            print(f"🔍 [知识点查询] 查询结果: 找到 {len(existing_knowledge_points)} 个知识点")
            if existing_knowledge_points:
                print(f"🔍 [知识点查询] 前3个知识点示例: {[{'name': kp.get('name'), 'moduleId': kp.get('moduleId'), 'subject': kp.get('subject')} for kp in existing_knowledge_points[:3]]}")
        except Exception as e:
            print(f"⚠️ 获取用户已有知识点失败: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        print(f"⚠️ [知识点查询] databases 为空，跳过查询")
    
    # 构建已有知识点列表文本（按模块分组）
    knowledge_points_text = ""
    if existing_knowledge_points:
        print(f"🔍 [知识点分组] 开始按模块分组，共 {len(existing_knowledge_points)} 个知识点")
        # 按模块ID分组知识点
        kp_by_module_id = {}
        for kp in existing_knowledge_points:
            module_id = kp.get('moduleId')
            kp_name = kp.get('name', '未知')
            if module_id:
                if module_id not in kp_by_module_id:
                    kp_by_module_id[module_id] = []
                kp_by_module_id[module_id].append(kp_name)
            else:
                print(f"⚠️ [知识点分组] 知识点 '{kp_name}' 没有 moduleId，跳过")
        
        print(f"🔍 [知识点分组] 分组完成，共 {len(kp_by_module_id)} 个模块")
        for module_id, kp_names in kp_by_module_id.items():
            print(f"  - 模块 {module_id}: {len(kp_names)} 个知识点 - {kp_names[:3]}{'...' if len(kp_names) > 3 else ''}")
        
        if kp_by_module_id:
            # 查询所有涉及的模块信息（获取模块名称）
            DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
            COLLECTION_MODULES = 'knowledge_points_library'
            
            module_ids = list(kp_by_module_id.keys())
            module_name_map = {}  # {module_id: module_name}
            
            print(f"🔍 [模块查询] 开始查询 {len(module_ids)} 个模块的名称")
            # 批量查询模块信息
            try:
                for module_id in module_ids:
                    try:
                        module_doc = await asyncio.to_thread(
                            databases.get_document,
                            database_id=DATABASE_ID,
                            collection_id=COLLECTION_MODULES,
                            document_id=module_id
                        )
                        module_name = module_doc.get('name', '未知模块')
                        module_name_map[module_id] = module_name
                        print(f"  ✓ 模块 {module_id} -> {module_name}")
                    except Exception as e:
                        print(f"⚠️ 获取模块 {module_id} 信息失败: {str(e)}")
                        module_name_map[module_id] = '未知模块'
            except Exception as e:
                print(f"⚠️ 批量查询模块信息失败: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # 格式化知识点文本（按模块分组）
            print(f"🔍 [格式化] 开始格式化知识点文本")
            kp_text_list = []
            for module_id, kp_names in kp_by_module_id.items():
                module_name = module_name_map.get(module_id, '未知模块')
                kp_text = f"**{module_name}模块**：{', '.join(kp_names)}"
                kp_text_list.append(kp_text)
                print(f"  - {kp_text}")
            
            if kp_text_list:
                knowledge_points_text = "\n".join(kp_text_list)
                print(f"✓ [格式化完成] 已获取 {len(existing_knowledge_points)} 个已有知识点，分布在 {len(kp_by_module_id)} 个模块中")
                print(f"🔍 [格式化结果] 知识点文本长度: {len(knowledge_points_text)} 字符")
                print(f"🔍 [格式化结果] 知识点文本预览:\n{knowledge_points_text[:200]}...")
            else:
                print(f"⚠️ [格式化] kp_text_list 为空")
        else:
            print(f"⚠️ [知识点分组] kp_by_module_id 为空")
    else:
        print(f"⚠️ [知识点查询] existing_knowledge_points 为空，没有找到知识点")
    
    # 构建 prompt
    system_prompt = get_knowledge_points_system_prompt()
    available_modules_hint = build_modules_hint(modules_text)
    existing_kp_hint = build_existing_kp_hint(knowledge_points_text)
    subject_chinese = get_subject_chinese_name(subject)
    
    user_prompt = get_knowledge_points_user_prompt(
        subject_chinese=subject_chinese,
        content=content,
        available_modules_hint=available_modules_hint,
        existing_kp_hint=existing_kp_hint
    )

    # Agent 重试机制
    max_retries = 3
    llm = get_llm_provider()
    
    for attempt in range(max_retries):
        response = None
        try:
            if attempt == 0:
                print(f"🔍 开始知识点分析...")
                print(f"🔍 用户提示: {user_prompt}")
            else:
                print(f"🔄 知识点分析第 {attempt + 1} 次重试...")
            
            response = await llm.chat(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.9,
                max_tokens=32768,
                thinking={"type": "enabled"},
                reasoning_effort="low"
            )
            
            print(f"📋 LLM 返回的知识点分析: {response[:200]}...")
            
            result = parse_knowledge_points_response(response)
            
            print(f"✅ 知识点分析解析成功！")
            
            # 设置学科
            result['subject'] = subject
            
            # 验证和规范化模块列表
            modules_list = result.get('modules', [])
            if not isinstance(modules_list, list):
                modules_list = []
            if not modules_list:
                modules_list = ['未分类']
            
            # 验证每个模块是否在可用列表中
            validated_modules = []
            validated_module_ids = {}
            
            for module_name in modules_list:
                original_name = module_name
                module_name = _normalize_module_name(module_name)
                
                if original_name != module_name:
                    print(f"⚠ 自动修正模块名: '{original_name}' -> '{module_name}'")
                
                if module_name in modules_dict:
                    validated_modules.append(module_name)
                    validated_module_ids[module_name] = modules_dict[module_name]
                    print(f"✓ 模块匹配: {module_name}")
                else:
                    print(f"⚠ 模块 '{module_name}' 不在列表中，忽略")
            
            if not validated_modules:
                print(f"⚠ 无有效模块，使用'未分类'")
                validated_modules = ['未分类']
                if '未分类' in modules_dict:
                    validated_module_ids['未分类'] = modules_dict['未分类']
            
            # 验证和规范化知识点
            knowledge_points = result.get('knowledgePoints', [])
            if not isinstance(knowledge_points, list):
                knowledge_points = []
            if not knowledge_points:
                knowledge_points = [{'name': '未分类', 'module': validated_modules[0], 'category': 'primary', 'importance': 'normal'}]
            
            processed_kps = []
            primary_kps = []
            
            for kp in knowledge_points:
                if not isinstance(kp, dict):
                    print(f"⚠ 知识点格式错误，跳过: {kp}")
                    continue
                
                kp_name = kp.get('name', '')
                kp_module = kp.get('module', validated_modules[0])
                kp_category = kp.get('category', 'secondary')
                kp_importance = kp.get('importance', 'normal')
                
                # 规范化模块名
                if isinstance(kp_module, str):
                    original_module = kp_module
                    kp_module = _normalize_module_name(kp_module)
                    if original_module != kp_module:
                        print(f"⚠ 自动修正知识点模块名: '{original_module}' -> '{kp_module}'")
                
                # 验证 category 和 importance
                if kp_category not in ['primary', 'secondary', 'related']:
                    kp_category = 'secondary'
                if kp_importance not in ['high', 'basic', 'normal']:
                    kp_importance = 'normal'
                
                if not kp_name:
                    continue
                
                # 确保知识点的模块在验证列表中
                if kp_module not in validated_modules:
                    print(f"⚠ 知识点 '{kp_name}' 的模块 '{kp_module}' 无效，改用 '{validated_modules[0]}'")
                    kp_module = validated_modules[0]
                
                # 获取该模块下已有的知识点进行匹配
                module_id = validated_module_ids.get(kp_module)
                if module_id and databases:
                    existing_kp_names = get_existing_knowledge_points_by_module(module_id, user_id, databases)
                    if kp_name in existing_kp_names:
                        print(f"  ✓ 知识点: {kp_name} ({kp_module}) | 题目角色={kp_category} | 重要性={kp_importance}")
                    else:
                        print(f"  + 新知识点: {kp_name} ({kp_module}) | 题目角色={kp_category} | 重要性={kp_importance}")
                
                # 记录主要考点
                kp_data = {
                    'name': kp_name,
                    'module': kp_module,
                    'moduleId': module_id,
                    'category': kp_category,
                    'importance': kp_importance
                }
                
                if kp_category == 'primary':
                    primary_kps.append(kp_data)
                
                processed_kps.append(kp_data)
            
            # 提取解题提示
            solving_hint = result.get('solvingHint', '')
            if not solving_hint or not isinstance(solving_hint, str):
                solving_hint = ''
            solving_hint = solving_hint.strip()
            
            print(f"📝 解题提示: {solving_hint[:50]}..." if solving_hint else "⚠ 未提供解题提示")
            print(f"🎯 主要考点（category=primary）: {len(primary_kps)} 个")
            for kp in primary_kps:
                print(f"   - {kp['name']} (重要性: {kp['importance']})")
            
            return {
                'subject': subject,
                'modules': validated_modules,
                'moduleIds': list(validated_module_ids.values()),
                'knowledgePoints': processed_kps,
                'primaryKnowledgePoints': primary_kps,
                'solvingHint': solving_hint
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 知识点分析失败（尝试 {attempt + 1}/{max_retries}）: {error_msg}")
            
            if attempt < max_retries - 1:
                # 构造格式化的错误反馈
                error_feedback = f"""⚠️ 你的上一次输出格式有错误，无法解析：

【错误信息】
{error_msg}

【要求的格式】
##MODULES##
模块名1
模块名2
...

##KNOWLEDGE_POINTS##
知识点名|模块名|category|importance
知识点名|模块名|category|importance
...

说明：
- category 必须是：primary（主要考点）/secondary（次要考点）/related（相关知识）
- importance 必须是：high（高频重点）/basic（基础必会）/normal（常规知识）

##SOLVING_HINT##
解题提示内容（可以包含 LaTeX 公式）

##END##

【可用的模块列表】
{modules_text if modules_text else '（无可用模块，请使用"未分类"）'}

【你的输出】
{response[:500] if response else '无响应'}...

请严格按照上述格式重新输出，确保：
1. 所有标记都存在
2. 知识点格式为：知识点名|模块名|category|importance（用 | 分隔）
3. category 和 importance 的值必须在允许的范围内"""
                # 将错误反馈添加到聊天历史
                user_prompt = error_feedback
                print(f"📤 发送错误反馈给 LLM，准备重试...")
            else:
                # 最后一次尝试也失败了
                print(f"❌ 已达到最大重试次数，放弃")
                if response:
                    print(f"原始响应: {response[:500]}...")
                raise
