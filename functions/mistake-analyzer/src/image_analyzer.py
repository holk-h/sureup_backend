"""
图片分析模块
负责处理错题图片的 AI 视觉分析

使用 LLM 的视觉能力直接分析图片，提取题目信息并转换为 Markdown 格式

内部统一使用 base64 格式处理图片
"""
import os
import json
import base64
from typing import Dict, List, Optional
from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query

from llm_provider import get_llm_provider


# 常量配置
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_MODULES = 'knowledge_points_library'
BUCKET_ORIGINAL_IMAGES = 'origin_question_image'

# 学科中文映射
SUBJECT_NAMES = {
    'math': '数学',
    'physics': '物理',
    'chemistry': '化学',
    'biology': '生物',
    'chinese': '语文',
    'english': '英语',
    'history': '历史',
    'geography': '地理',
    'politics': '政治'
}

# 题目类型
QUESTION_TYPES = ['choice', 'fillBlank', 'shortAnswer', 'essay']


# ============= 工具函数 =============

def create_appwrite_client() -> Client:
    """创建 Appwrite Client"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return client


def url_to_base64(image_url: str) -> str:
    """
    从 URL 下载图片并转换为 base64
    
    Args:
        image_url: 图片 URL
        
    Returns:
        纯 base64 字符串（不含 data:image 前缀）
    """
    import requests
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    return base64.b64encode(response.content).decode('utf-8')


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


def clean_json_response(response: str) -> str:
    """清理 LLM 响应中的代码块标记"""
    response = response.strip()
    if response.startswith('```json'):
        response = response[7:]
    if response.startswith('```'):
        response = response[3:]
    if response.endswith('```'):
        response = response[:-3]
    return response.strip()


def create_fallback_result(subject: str, error_msg: str = '') -> Dict:
    """创建失败时的占位结果"""
    return {
        'content': f'分析失败: {error_msg}' if error_msg else '题目识别失败，请重试',
        'type': 'shortAnswer',
        'module': f'{subject}_未分类',
        'knowledgePointNames': [f'{subject}_未分类'],
        'options': [],
        'answer': '',
        'explanation': '',
        'difficulty': 3,
        'userAnswer': '',
        'errorReason': 'other',
        'extractedImageUrls': [],
        'confidence': 0.0,
        'error': error_msg
    }


# ============= 主要功能函数 =============

def analyze_mistake_image(
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    subject: str = 'math',
    storage: Optional[Storage] = None,
    databases: Optional[Databases] = None
) -> Dict:
    """
    分析错题图片并提取题目信息（外部接口）
    
    接受 URL 或 base64，内部统一转换为 base64 处理
    
    Args:
        image_url: 图片 URL（二选一）
        image_base64: 图片 base64 编码（二选一，可包含或不包含 data:image 前缀）
        subject: 学科
        storage: Storage 实例（可选）
        databases: Databases 实例（可选）
        
    Returns:
        包含题目内容、类型、模块、知识点等的字典
    """
    if not image_url and not image_base64:
        raise ValueError("必须提供 image_url 或 image_base64 其中之一")
    
    # 统一转换为纯 base64（内部统一使用 base64）
    if image_url:
        image_base64 = url_to_base64(image_url)
    else:
        image_base64 = clean_base64(image_base64)
    
    # 保存原始图片
    original_image_url = save_original_image(image_base64, storage)
    
    # 两步分析：OCR + 知识点
    analysis_result = analyze_with_llm_vision(image_base64, subject, databases)
    analysis_result['originalImageUrl'] = original_image_url
    
    return analysis_result


def save_original_image(
    image_base64: str,
    storage: Optional[Storage] = None
) -> str:
    """
    保存原始图片到 Storage（内部函数，只接受 base64）
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        storage: Storage 实例（可选）
        
    Returns:
        保存后的图片 URL，失败返回空字符串
    """
    if not storage:
        storage = Storage(create_appwrite_client())
    
    try:
        # 解码 base64
        image_data = base64.b64decode(image_base64)
        
        # 上传到 Storage
        result = storage.create_file(
            bucket_id=BUCKET_ORIGINAL_IMAGES,
            file_id=ID.unique(),
            file=image_data
        )
        
        # 构建访问 URL
        endpoint = os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1')
        project_id = os.environ['APPWRITE_PROJECT_ID']
        return f"{endpoint}/storage/buckets/{BUCKET_ORIGINAL_IMAGES}/files/{result['$id']}/view?project={project_id}"
        
    except Exception as e:
        print(f"保存图片失败: {str(e)}")
        return ''


def analyze_with_llm_vision(
    image_base64: str,
    subject: str = 'math',
    databases: Optional[Databases] = None
) -> Dict:
    """
    使用 LLM 两步分析法（内部函数，只接受 base64）
    
    1. OCR + 格式转换
    2. 知识点分析（参考系统现有模块）
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        subject: 学科
        databases: Databases 实例（可选）
    """
    try:
        # 第一步：提取题目内容
        step1 = extract_question_content(image_base64, subject)
        
        # 第二步：分析知识点
        step2 = analyze_knowledge_points(step1['content'], step1['type'], subject, databases)
        
        # 合并结果并设置默认值
        return {
            **step1,
            **step2,
            'answer': '',
            'explanation': '',
            'difficulty': 3,
            'userAnswer': '',
            'errorReason': 'other',
            'confidence': 0.85,
            'extractedImageUrls': []
        }
        
    except Exception as e:
        print(f"LLM 分析失败: {str(e)}")
        return create_fallback_result(subject, str(e))


def extract_question_content(
    image_base64: str,
    subject: str = 'math'
) -> Dict:
    """
    第一步：从图片提取题目内容（OCR + 格式转换，内部函数）
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        subject: 学科
        
    Returns:
        {'content': str, 'type': str, 'options': list}
    """
    subject_name = SUBJECT_NAMES.get(subject, subject)
    
    system_prompt = "你是专业的题目识别专家，擅长从图片中提取题目信息并转换为结构化的 Markdown 格式。"
    
    user_prompt = f"""请识别这张 {subject_name} 题目图片，提取以下信息：

1. **题目内容**：转换为 Markdown 格式
   - 数学/物理/化学公式使用 LaTeX 语法（行内 $...$，独立 $$...$$）
   - 保留题目的原始结构和格式
   
2. **题目类型**：choice(选择题)/fillBlank(填空题)/shortAnswer(简答题)/essay(论述题)

3. **选项**（仅选择题需要）：提取所有选项内容，保持原始顺序

返回 JSON 格式（直接返回 JSON，不要用代码块）：

{{
    "content": "题目内容的完整Markdown格式",
    "type": "choice",
    "options": ["A. 选项1", "B. 选项2", ...]
}}

**示例（选择题）：**
{{
    "content": "计算定积分：\\n\\n$$\\\\int_0^1 x^2 dx$$",
    "type": "choice",
    "options": ["A. $\\\\frac{{1}}{{2}}$", "B. $\\\\frac{{1}}{{3}}$", "C. $\\\\frac{{1}}{{4}}$", "D. $\\\\frac{{2}}{{3}}$"]
}}

**示例（填空题）：**
{{
    "content": "已知函数 $f(x) = x^2 + 2x + 1$，则 $f'(1) = $ ______。",
    "type": "fillBlank",
    "options": []
}}"""

    try:
        llm = get_llm_provider()
        response = llm.chat_with_vision(
            prompt=user_prompt,
            image_base64=image_base64,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=3000
        )
        
        # 解析 JSON
        result = json.loads(clean_json_response(response))
        
        # 验证和规范化
        if 'content' not in result or not result['content']:
            raise ValueError("缺少题目内容")
        if 'type' not in result or result['type'] not in QUESTION_TYPES:
            result['type'] = 'shortAnswer'
        if not isinstance(result.get('options', []), list):
            result['options'] = []
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {str(e)}, 响应: {response}")
        raise ValueError(f"题目内容提取失败: {str(e)}")
    except Exception as e:
        print(f"题目提取失败: {str(e)}")
        raise


def get_existing_modules(subject: str, databases: Optional[Databases] = None) -> List[Dict]:
    """
    获取学科的现有模块列表
    
    Args:
        subject: 学科
        databases: Databases 实例（可选）
        
    Returns:
        [{'name': str, 'description': str}, ...]
    """
    if not databases:
        databases = Databases(create_appwrite_client())
    
    try:
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=[
                Query.equal('subject', subject),
                Query.equal('isActive', True),
                Query.order_asc('order'),
                Query.limit(100)
            ]
        )
        
        return [
            {'name': doc.get('name', ''), 'description': doc.get('description', '')}
            for doc in result.get('documents', [])
        ]
        
    except Exception as e:
        print(f"获取学科模块失败: {str(e)}")
        return []


def analyze_knowledge_points(
    content: str,
    question_type: str,
    subject: str = 'math',
    databases: Optional[Databases] = None
) -> Dict:
    """
    第二步：基于题目内容分析知识点
    
    Args:
        content: 题目内容（Markdown 格式）
        question_type: 题目类型
        subject: 学科
        databases: Databases 实例（可选）
        
    Returns:
        {'module': str, 'knowledgePointNames': list}
    """
    subject_name = SUBJECT_NAMES.get(subject, subject)
    existing_modules = get_existing_modules(subject, databases)
    
    # 构建模块提示文本
    if existing_modules:
        modules_list = '\n'.join([
            f"{i}. {m['name']}" + (f"（{m['description']}）" if m['description'] else "")
            for i, m in enumerate(existing_modules, 1)
        ])
        modules_hint = f"""

**系统中已有的模块：**
{modules_list}

**请优先从上述模块中选择最合适的。如果都不合适，可以提出新的模块名称。**"""
    else:
        modules_hint = "\n\n**注意：系统中暂无该学科的模块，请根据题目内容提出合适的模块名称。**"
    
    system_prompt = """你是专业的学科知识点分析专家。

注意：
- 模块是学科的大分类（如"微积分"、"代数"、"电磁学"、"有机化学"等）
- 知识点是具体的概念和技能（如"导数"、"极限"、"牛顿第二定律"等）
- 一个题目可能涉及多个知识点
- 优先从系统提供的现有模块中选择，没有合适的才创建新模块"""
    
    user_prompt = f"""请分析这道 {subject_name} 题目，识别其知识点信息：

**题目内容：**
{content}

**题目类型：** {question_type}
{modules_hint}

返回 JSON 格式（直接返回 JSON，不要用代码块）：

{{
    "module": "模块名称",
    "knowledgePointNames": ["知识点1", "知识点2", "知识点3"]
}}

**示例（数学）：**
{{
    "module": "微积分",
    "knowledgePointNames": ["定积分", "幂函数积分", "微积分基本定理"]
}}

**示例（物理）：**
{{
    "module": "力学",
    "knowledgePointNames": ["牛顿第二定律", "受力分析", "加速度计算"]
}}"""

    try:
        llm = get_llm_provider()
        response = llm.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=1000
        )
        
        # 解析 JSON
        result = json.loads(clean_json_response(response))
        
        # 验证和规范化
        if not result.get('module'):
            result['module'] = f'{subject}_未分类'
        
        kp_names = result.get('knowledgePointNames', [])
        if not isinstance(kp_names, list):
            kp_names = [str(kp_names)] if kp_names else []
        result['knowledgePointNames'] = kp_names or [f'{subject}_未分类']
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {str(e)}, 响应: {response}")
        raise ValueError(f"知识点分析失败: {str(e)}")
    except Exception as e:
        print(f"知识点分析失败: {str(e)}")
        raise
