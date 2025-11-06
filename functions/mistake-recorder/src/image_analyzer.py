"""
图片分析模块（Appwrite Function 版本）
负责处理错题图片的 AI 视觉分析（同步版本）
"""
import os
import json
from typing import Dict, List, Optional
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

# 尝试导入 LLM provider（需要根据实际路径调整）
try:
    from .llm_provider import get_llm_provider
except ImportError:
    # 如果当前目录导入失败，尝试从上级目录
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from llm_provider import get_llm_provider


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
    """清理 LLM 响应中的代码块标记"""
    response = response.strip()
    if response.startswith('```json'):
        response = response[7:]
    if response.startswith('```'):
        response = response[3:]
    if response.endswith('```'):
        response = response[:-3]
    return response.strip()


def parse_segmented_response(response: str) -> Dict:
    """
    解析分段标记格式的 LLM 响应
    
    格式示例：
    ##TYPE##
    choice
    
    ##SUBJECT##
    math
    
    ##CONTENT##
    题目内容...
    
    ##OPTIONS##
    A. 选项1
    B. 选项2
    
    ##END##
    
    Args:
        response: LLM 返回的分段标记格式文本
        
    Returns:
        {'content': str, 'type': str, 'options': list, 'subject': str}
        
    Raises:
        ValueError: 解析失败
    """
    import re
    
    # 清理可能的代码块标记
    response = response.strip()
    if response.startswith('```'):
        # 去除开头的代码块标记
        lines = response.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        response = '\n'.join(lines)
    
    # 使用正则提取各个部分（忽略前后空白）
    sections = {}
    
    # 提取 TYPE
    type_match = re.search(r'##TYPE##\s*\n\s*(\w+)', response, re.IGNORECASE)
    if type_match:
        sections['type'] = type_match.group(1).strip()
    
    # 提取 SUBJECT
    subject_match = re.search(r'##SUBJECT##\s*\n\s*(\w+)', response, re.IGNORECASE)
    if subject_match:
        sections['subject'] = subject_match.group(1).strip()
    
    # 提取 CONTENT（到下一个标记为止）
    content_match = re.search(r'##CONTENT##\s*\n(.*?)(?=##OPTIONS##|##END##)', response, re.DOTALL | re.IGNORECASE)
    if content_match:
        sections['content'] = content_match.group(1).strip()
    
    # 提取 OPTIONS（如果存在）
    options_match = re.search(r'##OPTIONS##\s*\n(.*?)(?=##END##)', response, re.DOTALL | re.IGNORECASE)
    if options_match:
        options_text = options_match.group(1).strip()
        if options_text:
            # 按行分割选项，过滤空行
            sections['options'] = [
                line.strip() 
                for line in options_text.split('\n') 
                if line.strip()
            ]
        else:
            sections['options'] = []
    else:
        sections['options'] = []
    
    # 验证必需字段
    if 'type' not in sections:
        raise ValueError("缺少 ##TYPE## 标记")
    if 'content' not in sections:
        raise ValueError("缺少 ##CONTENT## 标记")
    
    # 如果没有 SUBJECT，使用默认值
    if 'subject' not in sections:
        sections['subject'] = 'math'
    
    return sections


def create_fallback_result(subject: str, error_msg: str = '') -> Dict:
    """创建失败时的占位结果"""
    return {
        'content': f'分析失败: {error_msg}' if error_msg else '题目识别失败，请重试',
        'type': 'shortAnswer',
        'subject': subject,
        'module': '未分类',
        'knowledgePointNames': ['未分类'],
        'options': [],
        'confidence': 0.0,
        'error': error_msg
    }


# ============= 主要功能函数 =============

def analyze_mistake_image(
    image_base64: str,
    subject: str = 'math'
) -> Dict:
    """
    分析错题图片并提取题目信息（同步版本）
    
    Args:
        image_base64: 图片 base64 编码（纯 base64 或包含 data:image 前缀）
        subject: 学科代码（默认 math）
        
    Returns:
        包含题目内容、类型、模块、知识点等的字典
    """
    if not image_base64:
        raise ValueError("必须提供 image_base64")
    
    # 清理 base64 字符串
    clean_image_base64 = clean_base64(image_base64)
    
    if not clean_image_base64:
        raise ValueError("图片数据无效")
    
    try:
        # 第一步：OCR 提取题目内容
        step1 = extract_question_content(clean_image_base64)
        
        # 第二步：分析知识点
        step2 = analyze_knowledge_points(
            content=step1['content'],
            question_type=step1['type'],
            subject=step1.get('subject', subject)
        )
        
        # 合并结果
        return {
            **step1,
            **step2,
            'confidence': 0.85
        }
        
    except Exception as e:
        print(f"LLM 分析失败: {str(e)}")
        return create_fallback_result(subject, str(e))


def extract_question_content(image_base64: str) -> Dict:
    """
    第一步：OCR 提取题目内容和学科识别
    
    使用分段标记格式，避免 LaTeX 转义地狱
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        
    Returns:
        {'content': str, 'type': str, 'options': list, 'subject': str}
    """
    system_prompt = """你是专业的题目 OCR 识别专家，擅长从图片中准确提取题目文字并识别学科。

**核心要求：**
1. 所有数学、物理、化学公式必须使用 LaTeX 格式
2. 行内公式用 \( ... \) 包裹
3. 独立公式用 \[ ... \] 包裹，并独立成行
4. 识别完整的公式结构，包括分数、根号、积分、求和等
5. 使用分段标记格式返回，LaTeX 公式直接书写，不需要任何转义"""
    
    user_prompt = r"""请识别这张题目图片，提取以下信息：

**要提取的内容：**
1. **题目内容**：转换为 Markdown + LaTeX 格式
   - 所有公式用 LaTeX：变量、表达式、方程式等
   - 行内公式：\( ... \)
   - 独立公式：\[ ... \]（独立成行）
   - 保留原始结构和段落
   
2. **题目类型**：choice/fillBlank/shortAnswer/essay

3. **选项**（仅选择题）：每行一个选项，公式也用 LaTeX

4. **学科**：math/physics/chemistry/biology/chinese/english/history/geography/politics

**返回格式（分段标记，不要用代码块包裹）：**

##TYPE##
题目类型

##SUBJECT##
学科代码

##CONTENT##
题目内容（Markdown + LaTeX，LaTeX 公式直接书写，不需要转义）

##OPTIONS##
选项1
选项2
...

##END##

**示例1 - 选择题（数学）：**

##TYPE##
choice

##SUBJECT##
math

##CONTENT##
已知 \( m \)、\( n \) 是方程 \( x^2 + 2020x + 7 = 0 \) 的两个根，则 \( (m^2 + 2019m + 6)(n^2 + 2021n + 8) \) 的值为（）

##OPTIONS##
A. 1
B. 2
C. 3
D. 4

##END##

**示例2 - 填空题（物理）：**

##TYPE##
fillBlank

##SUBJECT##
physics

##CONTENT##
质量为 \( m \) 的物体受力 \( F \)，根据牛顿第二定律 \( F = ma \)，则加速度 \( a \) = ______。

##OPTIONS##

##END##

**示例3 - 解答题（数学）：**

##TYPE##
shortAnswer

##SUBJECT##
math

##CONTENT##
计算定积分：

\[
\int_0^1 x^2 \, dx
\]

请写出详细步骤。

##OPTIONS##

##END##

**LaTeX 常用语法：**
- 分数：\frac{a}{b}
- 上标：x^2, x^{n+1}
- 下标：x_i, a_{ij}
- 根号：\sqrt{x}, \sqrt[3]{x}
- 积分：\int_a^b
- 求和：\sum_{i=1}^n
- 希腊字母：\alpha, \beta, \theta, \pi
- 运算符：\times, \div, \pm, \leq, \geq
- 矩阵：\begin{bmatrix} ... \end{bmatrix}

**重要：**
- 标记符号必须独占一行
- 行内公式用 \( ... \)，块级公式用 \[ ... \]
- LaTeX 公式直接书写，不需要转义反斜杠
- OPTIONS 部分如果是非选择题，留空即可"""

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
        
        print(f"📋 LLM 返回的分段格式（前300字符）: {response[:300]}...")
        
        # 解析分段标记格式
        result = parse_segmented_response(response)
        
        print(f"✅ 分段格式解析成功！题目类型: {result.get('type', '未知')}, 学科: {result.get('subject', '未知')}")
        
        # 验证和规范化
        if 'content' not in result or not result['content']:
            raise ValueError("缺少题目内容")
        if 'type' not in result or result['type'] not in QUESTION_TYPES:
            result['type'] = 'shortAnswer'
        if not isinstance(result.get('options', []), list):
            result['options'] = []
        if 'subject' not in result or not result['subject']:
            result['subject'] = 'math'  # 默认数学
        
        return result
        
    except Exception as e:
        print(f"题目提取失败: {str(e)}")
        if response:
            print(f"原始响应: {response[:500]}...")
        raise


def parse_knowledge_points_response(response: str) -> Dict:
    """
    解析分段标记格式的知识点分析响应
    
    格式示例：
    ##MODULES##
    模块1
    
    ##KNOWLEDGE_POINTS##
    知识点名|模块名|category|importance
    
    ##SOLVING_HINT##
    解题提示
    
    ##END##
    
    Args:
        response: LLM 返回的分段标记格式文本
        
    Returns:
        {
            'modules': list[str],
            'knowledgePoints': list[dict],
            'solvingHint': str
        }
    """
    import re
    
    # 清理可能的代码块标记
    response = response.strip()
    if response.startswith('```'):
        lines = response.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        response = '\n'.join(lines)
    
    sections = {}
    
    # 提取 MODULES
    modules_match = re.search(r'##MODULES##\s*\n(.*?)(?=##KNOWLEDGE_POINTS##|##END##)', response, re.DOTALL | re.IGNORECASE)
    if modules_match:
        modules_text = modules_match.group(1).strip()
        if modules_text:
            sections['modules'] = [line.strip() for line in modules_text.split('\n') if line.strip()]
        else:
            sections['modules'] = []
    else:
        sections['modules'] = []
    
    # 提取 KNOWLEDGE_POINTS
    kp_match = re.search(r'##KNOWLEDGE_POINTS##\s*\n(.*?)(?=##SOLVING_HINT##|##END##)', response, re.DOTALL | re.IGNORECASE)
    if kp_match:
        kp_text = kp_match.group(1).strip()
        if kp_text:
            kp_list = []
            for line in kp_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if len(parts) >= 4:
                    kp_list.append({
                        'name': parts[0].strip(),
                        'module': parts[1].strip(),
                        'category': parts[2].strip(),
                        'importance': parts[3].strip()
                    })
                elif len(parts) >= 2:
                    kp_list.append({
                        'name': parts[0].strip(),
                        'module': parts[1].strip(),
                        'category': parts[2].strip() if len(parts) > 2 else 'secondary',
                        'importance': parts[3].strip() if len(parts) > 3 else 'normal'
                    })
            sections['knowledgePoints'] = kp_list
        else:
            sections['knowledgePoints'] = []
    else:
        sections['knowledgePoints'] = []
    
    # 提取 SOLVING_HINT
    hint_match = re.search(r'##SOLVING_HINT##\s*\n(.*?)(?=##END##)', response, re.DOTALL | re.IGNORECASE)
    if hint_match:
        sections['solvingHint'] = hint_match.group(1).strip()
    else:
        sections['solvingHint'] = ''
    
    # 验证必需字段
    if not sections.get('modules'):
        sections['modules'] = ['未分类']
    if not sections.get('knowledgePoints'):
        sections['knowledgePoints'] = [{
            'name': '未分类',
            'module': sections['modules'][0],
            'category': 'primary',
            'importance': 'normal'
        }]
    
    return sections


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
        {'module': str, 'knowledgePointNames': list, 'solvingHint': str}
    """
    subject_name = SUBJECT_NAMES.get(subject, subject)
    
    system_prompt = """你是专业的学科知识点分析专家。

注意：
- 模块是学科的大分类（如"微积分"、"代数"、"电磁学"、"有机化学"等）
- 知识点是具体的概念和技能（如"导数"、"极限"、"牛顿第二定律"等）
- 一个题目可能涉及多个知识点
- 解题提示要求（重点！）：
  - **必须具有通用性**：总结这一类题的通用方法，让学生举一反三
  - **不要只针对这道题**：要形成方法论，适用于同类问题
  - **包含关键要素**：思路、公式、步骤、注意事项
  - 可以使用 LaTeX：行内 \( ... \)，块级 \[ ... \]
  - 长度：2-3句话"""
    
    user_prompt = rf"""请分析这道 {subject_name} 题目，识别其知识点信息：

**题目内容：**
{content}

**题目类型：** {question_type}

**返回格式（分段标记，不要用代码块包裹）：**

##MODULES##
模块名称

##KNOWLEDGE_POINTS##
知识点名|模块名|category|importance
知识点名|模块名|category|importance
...

##SOLVING_HINT##
解题提示（可以包含 LaTeX 公式）

##END##

**说明：**
- category: primary（主要考点）/ secondary（次要考点）/ related（相关考点）
- importance: high（高频考点）/ basic（基础知识）/ normal（普通考点）
- 解题提示要求：
  - **通用性原则**：总结这一类题的通用方法，不只针对当前这道题
  - **举一反三**：让学生能解决同类问题
  - **方法论导向**：点出关键思路、公式、步骤
  - 可以包含公式：行内用 \( ... \)，块级用 \[ ... \]
  - 长度：2-3句话，既简洁又完整

**示例1（数学 - 强调通用方法）：**

##MODULES##
微积分

##KNOWLEDGE_POINTS##
定积分|微积分|primary|high
幂函数积分|微积分|primary|high

##SOLVING_HINT##
幂函数定积分问题的标准流程：先用不定积分公式 \( \int x^n \, dx = \frac{{x^{{n+1}}}}{{n+1}} + C \) 求出原函数，再代入上下限相减 \( F(b) - F(a) \)。记住：定积分 = 上限原函数值 - 下限原函数值。

##END##

**示例2（物理 - 强调解题步骤）：**

##MODULES##
力学

##KNOWLEDGE_POINTS##
牛顿第二定律|力学|primary|high
受力分析|力学|secondary|basic

##SOLVING_HINT##
力学问题解题三步骤：（1）画受力图，明确各力方向和大小；（2）用 \( F = ma \) 求加速度；（3）结合运动学公式求解。这类问题的关键是建立力和运动的桥梁。

##END##

**示例3（数学 - 强调思维路径）：**

##MODULES##
二次函数

##KNOWLEDGE_POINTS##
判别式|二次函数|primary|high
一元二次方程|二次函数|secondary|basic

##SOLVING_HINT##
遇到判断方程根的情况问题，核心是计算判别式 \( \Delta = b^2 - 4ac \)：\( \Delta > 0 \) 有两个不同实根，\( \Delta = 0 \) 有两个相等实根，\( \Delta < 0 \) 无实根。这是解决一元二次方程根的性质问题的通用方法。

##END##"""

    try:
        llm = get_llm_provider()
        response = llm.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=1500
        )
        
        print(f"📋 LLM 返回的知识点分析（前300字符）: {response[:300]}...")
        
        # 解析分段标记格式
        parsed = parse_knowledge_points_response(response)
        
        # 转换为旧格式（兼容现有代码）
        result = {
            'module': parsed['modules'][0] if parsed['modules'] else '未分类',
            'knowledgePointNames': [kp['name'] for kp in parsed['knowledgePoints']],
            'solvingHint': parsed.get('solvingHint', '')
        }
        
        print(f"✅ 知识点分析解析成功！模块: {result['module']}")
        
        return result
        
    except Exception as e:
        print(f"知识点分析失败: {str(e)}")
        if 'response' in locals():
            print(f"原始响应: {response[:500]}...")
        raise
