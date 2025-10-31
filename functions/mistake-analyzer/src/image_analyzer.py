"""
图片分析模块
负责处理错题图片的 AI 视觉分析

使用 LLM 的视觉能力直接分析图片，提取题目信息并转换为 Markdown 格式

内部统一使用 base64 格式处理图片
图片已由 Flutter 端上传到 bucket，此模块只负责分析
"""
import os
import json
import base64
from typing import Dict, List, Optional
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

from .llm_provider import get_llm_provider


# 常量配置
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_MODULES = 'knowledge_points_library'

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
    """
    清理 LLM 响应中的代码块标记
    
    注意：不处理 LaTeX 公式中的反斜杠，因为 json.loads 会正确处理它们
    """
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
        'confidence': 0.0,
        'error': error_msg
    }


# ============= 主要功能函数 =============

def analyze_mistake_image(
    image_base64: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    分析错题图片并提取题目信息
    
    统一使用 base64 格式，图片已经在 bucket 中，不需要保存
    AI 会自动识别学科、模块和知识点
    
    Args:
        image_base64: 图片 base64 编码（纯 base64 或包含 data:image 前缀）
        databases: Databases 实例（可选）
        
    Returns:
        包含学科、题目内容、类型、模块、知识点等的字典
    """
    if not image_base64:
        raise ValueError("必须提供 image_base64")
    
    # 清理 base64 字符串，去除可能的前缀
    clean_image_base64 = clean_base64(image_base64)
    
    if not clean_image_base64:
        raise ValueError("图片数据无效")
    
    # 分析图片：识别学科 + OCR + 知识点
    analysis_result = analyze_with_llm_vision(clean_image_base64, databases)
    
    return analysis_result


def analyze_with_llm_vision(
    image_base64: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    使用 LLM 两步分析法（内部函数，只接受 base64）
    
    1. OCR：提取题目内容和格式
    2. 分析：识别学科、模块和知识点
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        databases: Databases 实例（可选）
    """
    try:
        # 第一步：OCR 提取题目内容
        step1 = extract_question_content(image_base64)
        
        # 第二步：基于题目内容识别学科和知识点
        step2 = analyze_subject_and_knowledge_points(
            content=step1['content'],
            question_type=step1['type'],
            databases=databases
        )
        
        # 合并结果并设置默认值
        return {
            **step1,
            **step2,
            'answer': '',
            'explanation': '',
            'difficulty': 3,
            'userAnswer': '',
            'errorReason': 'other',
            'confidence': 0.85
        }
        
    except Exception as e:
        print(f"LLM 分析失败: {str(e)}")
        return create_fallback_result('unknown', str(e))


def extract_question_content(
    image_base64: str
) -> Dict:
    """
    第一步：OCR 提取题目内容（内部函数）
    
    只负责从图片中识别文字和格式，不分析学科和知识点
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        
    Returns:
        {'content': str, 'type': str, 'options': list}
    """
    system_prompt = "你是专业的题目 OCR 识别专家，擅长从图片中准确提取题目文字并转换为 Markdown 格式。"
    
    user_prompt = """请识别这张题目图片，提取以下信息：

1. **题目内容**：转换为 Markdown 格式
   - 数学/物理/化学公式使用 LaTeX 语法（行内 $...$，独立 $$...$$）
   - 保留题目的原始结构和格式
   - 尽可能准确地识别所有文字和符号
   
2. **题目类型**：choice(选择题)/fillBlank(填空题)/shortAnswer(简答题)/essay(论述题)

3. **选项**（仅选择题需要）：提取所有选项内容，保持原始顺序

返回 JSON 格式（直接返回 JSON，不要用代码块）：

**重要：JSON 中的反斜杠必须使用双反斜杠 \\\\ 转义！例如 LaTeX 的 \\frac 要写成 \\\\frac**

{
    "content": "题目内容的完整Markdown格式",
    "type": "choice",
    "options": ["A. 选项1", "B. 选项2", ...]
}

**示例（选择题）：**
{
    "content": "计算定积分：\\n\\n$$\\\\int_0^1 x^2 dx$$",
    "type": "choice",
    "options": ["A. $\\\\frac{1}{2}$", "B. $\\\\frac{1}{3}$", "C. $\\\\frac{1}{4}$", "D. $\\\\frac{2}{3}$"]
}

**示例（填空题）：**
{
    "content": "一个质量为 $m$ 的物体在水平面上受到 $F$ 的力，加速度为 ______。",
    "type": "fillBlank",
    "options": []
}"""

    response = None
    try:
        llm = get_llm_provider()
        response = llm.chat_with_vision(
            prompt=user_prompt,
            image_base64=image_base64,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=3000
        )
        
        # 清理响应
        cleaned_response = clean_json_response(response)
        
        # 尝试解析 JSON
        try:
            result = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            # LaTeX 公式中的反斜杠可能导致解析失败
            # 使用 raw string 解码器
            print(f"首次 JSON 解析失败，尝试使用 strict=False: {str(e)}")
            try:
                result = json.loads(cleaned_response, strict=False)
            except:
                # 如果还是失败，尝试替换问题字符
                print(f"尝试修复 JSON 字符串...")
                # 将 JSON 字符串中的单反斜杠替换为双反斜杠（除了已经是双反斜杠的）
                import re
                # 查找所有不是双反斜杠的单反斜杠，并替换为双反斜杠
                fixed_response = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', cleaned_response)
                result = json.loads(fixed_response)
        
        # 验证和规范化
        if 'content' not in result or not result['content']:
            raise ValueError("缺少题目内容")
        if 'type' not in result or result['type'] not in QUESTION_TYPES:
            result['type'] = 'shortAnswer'
        if not isinstance(result.get('options', []), list):
            result['options'] = []
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {str(e)}, 响应: {response if response else '无响应'}")
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


def analyze_subject_and_knowledge_points(
    content: str,
    question_type: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    第二步：基于题目内容识别学科、模块和知识点
    
    Args:
        content: 题目内容（Markdown 格式）
        question_type: 题目类型
        databases: Databases 实例（可选）
        
    Returns:
        {'subject': str, 'module': str, 'knowledgePointNames': list}
    """
    system_prompt = """你是专业的学科知识点分析专家。

注意：
- 先识别题目属于哪个学科
- 模块是学科的大分类（如"微积分"、"代数"、"电磁学"、"有机化学"等）
- 知识点是具体的概念和技能（如"导数"、"极限"、"牛顿第二定律"等）
- 一个题目可能涉及多个知识点"""
    
    user_prompt = f"""请分析这道题目，识别其学科和知识点信息：

**题目内容：**
{content}

**题目类型：** {question_type}

请识别：
1. **学科**：判断题目属于哪个学科
   - math（数学）
   - physics（物理）
   - chemistry（化学）
   - biology（生物）
   - chinese（语文）
   - english（英语）
   - history（历史）
   - geography（地理）
   - politics（政治）

2. **模块**：该学科下的模块分类

3. **知识点**：题目涉及的具体知识点（可以有多个）

返回 JSON 格式（直接返回 JSON，不要用代码块）：

{{
    "subject": "学科英文代码",
    "module": "模块名称",
    "knowledgePointNames": ["知识点1", "知识点2", "知识点3"]
}}

**示例（数学）：**
{{
    "subject": "math",
    "module": "微积分",
    "knowledgePointNames": ["定积分", "幂函数积分", "微积分基本定理"]
}}

**示例（物理）：**
{{
    "subject": "physics",
    "module": "力学",
    "knowledgePointNames": ["牛顿第二定律", "受力分析", "加速度计算"]
}}"""

    response = None
    try:
        llm = get_llm_provider()
        response = llm.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=1000
        )
        
        # 清理响应
        cleaned_response = clean_json_response(response)
        
        # 尝试解析 JSON（使用与 extract_question_content 相同的逻辑）
        try:
            result = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            print(f"首次 JSON 解析失败，尝试使用 strict=False: {str(e)}")
            try:
                result = json.loads(cleaned_response, strict=False)
            except:
                print(f"尝试修复 JSON 字符串...")
                import re
                fixed_response = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', cleaned_response)
                result = json.loads(fixed_response)
        
        # 验证和规范化
        if not result.get('subject'):
            result['subject'] = 'math'  # 默认数学
        
        if not result.get('module'):
            # 尝试从识别的学科获取现有模块
            subject = result['subject']
            existing_modules = get_existing_modules(subject, databases)
            if existing_modules:
                result['module'] = existing_modules[0]['name']
            else:
                result['module'] = f'{subject}_未分类'
        
        kp_names = result.get('knowledgePointNames', [])
        if not isinstance(kp_names, list):
            kp_names = [str(kp_names)] if kp_names else []
        result['knowledgePointNames'] = kp_names or [f"{result['subject']}_未分类"]
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {str(e)}, 响应: {response if response else '无响应'}")
        raise ValueError(f"知识点分析失败: {str(e)}")
    except Exception as e:
        print(f"知识点分析失败: {str(e)}")
        raise
