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

from workers.mistake_analyzer.llm_provider import get_llm_provider


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
    elif response.startswith('```'):
        response = response[3:]
    if response.endswith('```'):
        response = response[:-3]
    return response.strip()


def parse_segmented_response(response: str) -> Dict:
    """
    解析分段标记格式的 LLM 响应（题目内容提取）
    
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
    if 'subject' not in sections:
        raise ValueError("缺少 ##SUBJECT## 标记")
    if 'content' not in sections:
        raise ValueError("缺少 ##CONTENT## 标记")
    
    return sections


def parse_knowledge_points_response(response: str) -> Dict:
    """
    解析分段标记格式的知识点分析响应
    
    格式示例：
    ##MODULES##
    模块1
    模块2
    
    ##KNOWLEDGE_POINTS##
    知识点名|模块名|category|importance
    知识点名|模块名|category|importance
    
    ##SOLVING_HINT##
    解题提示（可以包含 LaTeX 公式）
    
    ##END##
    
    Args:
        response: LLM 返回的分段标记格式文本
        
    Returns:
        {
            'modules': list[str],
            'knowledgePoints': list[dict],
            'solvingHint': str
        }
        
    Raises:
        ValueError: 解析失败
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
            sections['modules'] = [
                line.strip() 
                for line in modules_text.split('\n') 
                if line.strip()
            ]
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
                # 解析格式：知识点名|模块名|category|importance
                parts = line.split('|')
                if len(parts) >= 4:
                    kp_list.append({
                        'name': parts[0].strip(),
                        'module': parts[1].strip(),
                        'category': parts[2].strip(),
                        'importance': parts[3].strip()
                    })
                elif len(parts) >= 2:
                    # 容错：如果只有部分字段，使用默认值
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


def fix_json_escaping(json_str: str) -> str:
    """
    修复 JSON 字符串中的转义问题
    
    问题：LLM 可能返回无效的转义字符，特别是 LaTeX 公式中的反斜杠
    例如：\( 应该是 \\(，\frac 应该是 \\frac
    
    策略：
    1. 保留合法的 JSON 转义序列：\n \t \r \" \\ \/
    2. 将其他单反斜杠（特别是 LaTeX 命令）转换为双反斜杠
    
    Args:
        json_str: 待修复的 JSON 字符串
        
    Returns:
        修复后的 JSON 字符串
    """
    import re
    
    # 定义合法的 JSON 转义序列（在 JSON 字符串值中）
    # 这些不需要修改
    legal_escapes = ['\\n', '\\t', '\\r', '\\b', '\\f', '\\"', '\\\\', '\\/']
    
    # LaTeX 相关的反斜杠模式（这些需要变成双反斜杠）
    # 匹配 \ 后面跟着字母或括号（LaTeX 命令或公式标记）
    latex_pattern = r'(?<!\\)\\(?=[a-zA-Z\(\)\[\]])'
    
    # 替换策略：
    # 1. 找到所有在引号内的字符串值
    # 2. 在这些字符串中，将 LaTeX 相关的单反斜杠替换为双反斜杠
    
    result = []
    i = 0
    in_string = False
    escape_next = False
    
    while i < len(json_str):
        char = json_str[i]
        
        # 处理字符串内容
        if char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
            i += 1
            continue
        
        # 在字符串内部处理转义
        if in_string:
            if escape_next:
                # 上一个字符是反斜杠
                if char in 'ntrfb"\\/':
                    # 合法的 JSON 转义序列，保持不变
                    result.append(char)
                else:
                    # 不是合法的转义序列，在反斜杠前再加一个反斜杠
                    # 例如 \( 变成 \\(，\frac 变成 \\frac
                    result.append('\\')
                    result.append(char)
                escape_next = False
            elif char == '\\':
                # 遇到反斜杠，标记下一个字符需要检查
                result.append(char)
                escape_next = True
            else:
                result.append(char)
        else:
            # 不在字符串内，直接添加
            result.append(char)
            escape_next = False
        
        i += 1
    
    return ''.join(result)


def safe_json_loads(json_str: str, debug_name: str = "JSON") -> dict:
    """
    安全地解析 JSON，带有多重容错机制
    
    Args:
        json_str: JSON 字符串
        debug_name: 调试用名称
        
    Returns:
        解析后的字典
        
    Raises:
        ValueError: 所有解析尝试都失败
    """
    import re
    
    # 尝试1：直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e1:
        print(f"⚠️ {debug_name} 解析失败（第1次）: {str(e1)}")
        print(f"   错误位置附近的内容: ...{json_str[max(0, e1.pos-30):e1.pos+30]}...")
    
    # 尝试2：使用 strict=False（允许控制字符）
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError as e2:
        print(f"⚠️ {debug_name} 解析失败（第2次，strict=False）: {str(e2)}")
    
    # 尝试3：修复转义问题
    try:
        fixed_json = fix_json_escaping(json_str)
        print(f"🔧 尝试修复转义字符...")
        return json.loads(fixed_json)
    except json.JSONDecodeError as e3:
        print(f"⚠️ {debug_name} 解析失败（第3次，修复转义后）: {str(e3)}")
        print(f"   修复后的JSON前200字符: {fixed_json[:200]}")
    
    # 尝试4：激进的修复 - 将所有单反斜杠都加倍（除了已经是双反斜杠的）
    try:
        aggressive_fix = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_str)
        print(f"🔧 尝试激进修复（所有单反斜杠加倍）...")
        return json.loads(aggressive_fix)
    except json.JSONDecodeError as e4:
        print(f"⚠️ {debug_name} 解析失败（第4次，激进修复）: {str(e4)}")
    
    # 所有尝试都失败，记录完整内容并抛出异常
    print(f"❌ {debug_name} 解析彻底失败！")
    print(f"📄 完整 JSON 内容：\n{json_str}\n")
    raise ValueError(f"{debug_name} 解析失败：尝试了4种方法都无法解析。最后一次错误：{str(e4)}")


def fix_latex_escaping(text: str) -> str:
    """
    修正 LaTeX 公式中的转义问题（用于 JSON 解析后的文本）
    
    注意：这个函数处理的是 JSON 解析**后**的 Python 字符串
    
    前端 gpt_markdown 要求的格式：
    - 行内公式：\( ... \)  (单反斜杠)
    - 独立公式：\[ ... \]  (单反斜杠)
    - LaTeX 命令：\frac、\sqrt 等 (单反斜杠)
    
    如果 LLM 在 JSON 中输出了 \\\\( （四个反斜杠），解析后会变成 \\(（双反斜杠）
    我们需要将其修正为 \(（单反斜杠）
    
    策略：在 LaTeX 公式上下文中，将双反斜杠的 LaTeX 命令替换为单反斜杠
    
    Args:
        text: JSON 解析后的文本（可能包含双反斜杠的 LaTeX 命令）
        
    Returns:
        修正后的文本（单反斜杠的 LaTeX 命令）
    """
    import re
    
    # LaTeX 常用命令列表（用于匹配）
    latex_commands = [
        'frac', 'sqrt', 'int', 'sum', 'prod', 'lim',
        'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
        'log', 'ln', 'exp',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'pi', 'sigma', 'omega', 'mu', 'nu', 'xi', 'rho', 'tau', 'phi', 'chi', 'psi',
        'Alpha', 'Beta', 'Gamma', 'Delta', 'Theta', 'Pi', 'Sigma', 'Omega',
        'times', 'div', 'pm', 'mp', 'cdot', 'ast',
        'leq', 'geq', 'neq', 'approx', 'equiv', 'sim',
        'infty', 'partial', 'nabla', 'forall', 'exists',
        'left', 'right', 'begin', 'end',
        'text', 'mathbf', 'mathrm', 'mathit', 'mathbb', 'mathcal',
    ]
    
    # 策略：找到所有公式区域，在公式内部将双反斜杠替换为单反斜杠
    def fix_formula(match):
        """修正单个公式内的转义"""
        prefix = match.group(1)  # \( 或 \[
        content = match.group(2)  # 公式内容
        suffix = match.group(3)  # \) 或 \]
        
        # 在公式内容中，将所有 LaTeX 命令的双反斜杠改为单反斜杠
        for cmd in latex_commands:
            content = content.replace(f'\\\\{cmd}', f'\\{cmd}')
        
        return prefix + content + suffix
    
    # 匹配所有公式：\( ... \) 或 \[ ... \]
    # 使用非贪婪匹配，支持嵌套的括号
    text = re.sub(
        r'(\\[\(\[])(.*?)(\\[\)\]])',
        fix_formula,
        text,
        flags=re.DOTALL
    )
    
    return text


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


# ============= 主要功能函数 =============

async def analyze_mistake_image(
    image_base64: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    分析错题图片并提取题目信息（异步）
    
    统一使用 base64 格式，图片已经在 bucket 中，不需要保存
    AI 会自动识别学科、模块和知识点
    
    Args:
        image_base64: 图片 base64 编码（纯 base64 或包含 data:image 前缀）
        user_id: 用户ID（用于获取学段信息）
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
    analysis_result = await analyze_with_llm_vision(clean_image_base64, user_id, databases)
    
    return analysis_result


async def analyze_with_llm_vision(
    image_base64: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> Dict:
    """
    使用 LLM 两步分析法（内部函数，只接受 base64，异步）
    
    1. OCR：提取题目内容和格式
    2. 分析：识别学科、模块和知识点
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
    """
    try:
        # 第一步：OCR 提取题目内容和学科识别
        step1 = await extract_question_content(image_base64)
        
        # 第二步：基于题目内容和学科识别模块和知识点
        step2 = await analyze_subject_and_knowledge_points(
            content=step1['content'],
            question_type=step1['type'],
            subject=step1['subject'],
            user_id=user_id,
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
            'confidence': 0.85
        }
        
    except Exception as e:
        print(f"LLM 分析失败: {str(e)}")
        return create_fallback_result('unknown', str(e))


async def extract_question_content(
    image_base64: str
) -> Dict:
    """
    第一步：OCR 提取题目内容和学科识别（内部函数，异步）
    
    使用分段标记格式，避免 LaTeX 转义地狱
    
    Args:
        image_base64: 纯 base64 字符串（不含前缀）
        
    Returns:
        {'content': str, 'type': str, 'options': list, 'subject': str}
    """
    system_prompt = """你是专业的题目 OCR 识别专家，精确提取题目文字并识别学科。

**核心要求：**
1. **准确提取**：逐字逐句识别，不遗漏不添加，忽略手写痕迹
2. **公式精确**：数学、物理、化学公式必须用 LaTeX，保持原题结构
3. 行内公式：\( ... \)，独立公式：\[ ... \]（独立成行）
4. 识别完整公式：分数、根号、积分、求和、矩阵等
5. 分段标记格式，LaTeX 直接书写，不转义"""
    
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

**示例4 - 矩阵（数学）：**

##TYPE##
shortAnswer

##SUBJECT##
math

##CONTENT##
求矩阵的行列式：

\[
\begin{bmatrix}
1 & 2 & 3 \\
4 & 5 & 6 \\
7 & 8 & 9
\end{bmatrix}
\]

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
        response = await llm.chat_with_vision(
            prompt=user_prompt,
            image_base64=image_base64,
            system_prompt=system_prompt,
            temperature=1,
            max_tokens=32768,
            thinking={"type": "enabled"},  # 启用思考模式
            reasoning_effort="low"          # 设置推理深度为 low
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


def get_existing_modules(
    subject: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> List[Dict]:
    """
    获取用户学段对应的学科模块列表
    
    Args:
        subject: 学科（英文代码如 'math'）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
        
    Returns:
        [{'$id': str, 'name': str, 'description': str}, ...]
    """
    if not databases:
        databases = Databases(create_appwrite_client())
    
    try:
        # 获取用户档案，确定学段
        from workers.mistake_analyzer.utils import get_user_profile, get_education_level_from_grade, get_subject_chinese_name
        
        user_profile = get_user_profile(databases, user_id)
        user_grade = user_profile.get('grade') if user_profile else None
        education_level = get_education_level_from_grade(user_grade)
        
        print(f"用户年级: {user_grade}, 学段: {education_level}")
        
        # 将学科英文代码转换为中文（数据库中存储的是中文）
        subject_chinese = get_subject_chinese_name(subject)
        
        # 查询对应学段的模块
        queries = [
            Query.equal('subject', subject_chinese),
            Query.equal('educationLevel', education_level),
            Query.equal('isActive', True),
            Query.order_asc('order'),
            Query.limit(100)
        ]
        
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=queries
        )
        
        modules = [
            {
                '$id': doc.get('$id', ''),
                'name': doc.get('name', ''),
                'description': doc.get('description', '')
            }
            for doc in result.get('documents', [])
        ]
        
        print(f"找到 {len(modules)} 个{SUBJECT_NAMES.get(subject, subject)}模块（学段: {education_level}，学科中文: {subject_chinese}）")
        return modules
        
    except Exception as e:
        print(f"获取学科模块失败: {str(e)}")
        return []


def get_existing_knowledge_points_by_module(
    module_id: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> List[str]:
    """
    获取用户在指定模块下已有的知识点名称列表
    
    Args:
        module_id: 模块ID
        user_id: 用户ID
        databases: Databases 实例（可选）
        
    Returns:
        知识点名称列表
    """
    if not databases:
        databases = Databases(create_appwrite_client())
    
    try:
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='user_knowledge_points',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.limit(100)
            ]
        )
        
        return [doc.get('name', '') for doc in result.get('documents', []) if doc.get('name')]
        
    except Exception as e:
        print(f"获取用户知识点失败: {str(e)}")
        return []


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
    - 判断知识点的角色（category: primary/secondary/related - 在这道题中的作用）
    - 判断知识点的重要性（importance: high/basic/normal - 知识点自身的重要程度）
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
            'knowledgePoints': list[{
                'name': str, 
                'module': str, 
                'moduleId': str,
                'category': str,      # 在题目中的角色: primary/secondary/related
                'importance': str     # 知识点自身重要度: high/basic/normal
            }],
            'primaryKnowledgePoints': list[dict],  # 主要考点列表（category=primary的）
            'solvingHint': str                     # 解题提示
        }
    """
    # 获取该学科在用户学段的模块列表
    available_modules = get_existing_modules(subject, user_id, databases)
    
    # 构建模块列表文本（用于 prompt）
    modules_text = ""
    modules_dict = {}  # 用于后续查找模块ID
    if available_modules:
        modules_list = []
        for mod in available_modules:
            modules_dict[mod['name']] = mod['$id']  # 保存模块ID映射
            # 使用括号形式展示描述，让 LLM 理解模块含义，但返回时只填写模块名
            if mod.get('description'):
                modules_list.append(f"  - {mod['name']} ({mod['description']})")
            else:
                modules_list.append(f"  - {mod['name']}")
        modules_text = "\n".join(modules_list)
    
    system_prompt = """你是学科知识点分析专家，专注于精确识别题目的考点。

核心原则：
- 必须从提供的模块列表中选择
- **知识点要精确**：使用标准学术术语，避免模糊表达
- 区分题目角色（category）和知识点重要性（importance）

分析要点：
1. **模块选择**：选择题目主要考查内容所在的模块（通常1个，综合题可能2个）
2. **知识点提取**（关键！）：
   - 必须精确、具体，如"一元二次方程判别式"而非"方程"
   - 避免过度概括（太宽泛）或过度细分（太琐碎）
   - 通常1-3个知识点，主要考点1-2个
3. **category（题目角色）**：
   - primary：这道题的主要考点，直接考查的核心内容
   - secondary：次要考点，间接涉及的内容
   - related：相关但不直接考查的内容
4. **importance（知识点重要性）**：
   - high：考试高频考点，核心重点知识
   - basic：基础必会内容，其他知识的前置
   - normal：普通考点
5. **解题提示**（核心！）：
   - 分两部分：【本题解法】+【方法论】
   - **本题解法**：说明这道具体题目的解题思路和关键步骤
     * **重要**：专注于思路解析，避免具体数值计算过程
     * 说明"应该怎么做"，而不是"算出等于多少"
     * 可以指出关键公式和计算方向，但不需要算出具体数值结果
   - **方法论**：总结这类题和知识点的通用方法、重点、易错点、注意事项
   - 可使用 LaTeX 公式表达思路
   - 目标：让学生既能理解当前题目的解题思路，又能掌握同类题型的通用方法"""
    
    available_modules_hint = ""
    if modules_text:
        available_modules_hint = f"""

**可用模块列表（必须从中选择）：**
{modules_text}"""
    else:
        available_modules_hint = "\n\n**注意**：系统暂无模块数据，请使用\"未分类\"。"
    
    # 获取学科中文名称
    from workers.mistake_analyzer.utils import get_subject_chinese_name
    subject_chinese = get_subject_chinese_name(subject)
    
    user_prompt = rf"""分析这道{subject_chinese}题目，提取模块、知识点和解题提示。

**题目：**
{content}
{available_modules_hint}

**返回格式（分段标记，不要用代码块）：**

##MODULES##
模块1
模块2
...

##KNOWLEDGE_POINTS##
知识点名|模块名|category|importance
知识点名|模块名|category|importance
...

##SOLVING_HINT##
解题提示（markdown 格式，可包含 LaTeX）

##END##

**字段说明：**
1. **MODULES**：只填模块名（不含括号描述），必须从上面列表中选择
2. **KNOWLEDGE_POINTS**：每行一个，格式为 `知识点名|模块名|category|importance`
   - **知识点名**：精确、具体，如"一元二次方程判别式"而非"方程"
   - **category**（题目中的角色）：primary（主要考点）/ secondary（次要）/ related（相关）
   - **importance**（知识点重要性）：high（高频考点）/ basic（基础）/ normal（普通）
3. **SOLVING_HINT**：分【本题解法】和【方法论】两部分
   - 专注于解题思路，避免具体数值计算
   - 解法部分说明"如何分析、如何应用公式、解题步骤"，而不是"计算出等于多少"
   - 可以写出关键公式和变换思路，但不需要算出具体数值结果
   - 方法论部分说明这类题和知识点的通用方法、重点、易错点、注意事项

**示例1（一元二次方程判别式）：**

##MODULES##
二次函数

##KNOWLEDGE_POINTS##
一元二次方程判别式|二次函数|primary|high

##SOLVING_HINT##
**【本题解法】**

这道题考查方程根的性质，关键思路如下：

1. **识别条件**：\( m \)、\( n \) 是方程 \( x^2 + 2020x + 7 = 0 \) 的两个根
2. **应用韦达定理**：得到 \( m + n = -2020 \)，\( mn = 7 \)
3. **代数变换**：利用韦达定理的结论，将目标式中的 \( m^2 + 2019m + 6 \) 改写为：
   - 注意到 \( m^2 + 2019m + 6 = m^2 + 2020m + 7 - m - 1 \)
   - 而 \( m^2 + 2020m + 7 = 0 \)（因为 \( m \) 是方程的根）
   - 所以 \( m^2 + 2019m + 6 = mn - m - 1 \)
4. **对称处理**：同理处理另一个因式
5. **整体代换**：将两个因式相乘化简即可

**思路核心**：利用"方程的根满足方程"这一性质，结合韦达定理进行整体代换。

---

**【方法论】**

判别式 \( \Delta = b^2 - 4ac \) 是判断一元二次方程根的情况的核心工具：
- \( \Delta > 0 \)：两个不等实根
- \( \Delta = 0 \)：两个相等实根  
- \( \Delta < 0 \)：无实根

**韦达定理**是处理根的关系式的重要工具：
- 两根之和：\( x_1 + x_2 = -\frac{{b}}{{a}} \)
- 两根之积：\( x_1 x_2 = \frac{{c}}{{a}} \)

**解题技巧**：遇到包含方程根的复杂代数式时，优先考虑代入韦达定理进行整体代换，避免直接求根导致计算复杂。

##END##

**示例2（物理综合题）：**

##MODULES##
力学
运动学

##KNOWLEDGE_POINTS##
牛顿第二定律|力学|primary|high
匀变速直线运动公式|运动学|primary|high
受力分析|力学|secondary|basic

##SOLVING_HINT##
**【本题解法】**

这道题是力学与运动学的综合问题，解题步骤：

1. **受力分析**：画出受力示意图，明确各力的大小和方向
2. **求加速度**：根据牛顿第二定律 \( F_{{合}} = ma \) 求出加速度
3. **求运动量**：根据题目要求选择合适的运动学公式求解

常用运动学公式：
- 速度公式：\( v = v_0 + at \)
- 位移公式：\( s = v_0 t + \frac{{1}}{{2}}at^2 \)
- 速度-位移关系：\( v^2 - v_0^2 = 2as \)

---

**【方法论】**

力学与运动学结合题的通用思路是 **"力→加速度→运动"** 三步法。

**核心要点**：加速度是连接力和运动的桥梁，必须先通过受力分析和牛顿第二定律求出加速度，再用运动学公式。

**常见易错点**：
1. 受力分析不全或方向错误
2. 忘记将合力分解到运动方向
3. 混淆运动学公式的适用条件（只适用于匀变速运动）

**注意事项**：
- 区分静摩擦力（平衡力）和滑动摩擦力（阻力）
- 使用正交分解法处理多个力的合成

##END##

**示例3（函数图像与性质）：**

##MODULES##
函数

##KNOWLEDGE_POINTS##
函数单调性|函数|primary|high
函数图像变换|函数|secondary|normal

##SOLVING_HINT##
**【本题解法】**

这道题考查函数图像的平移和对称变换。

**解题步骤**：
1. 识别基础函数 \( y = f(x) \) 的图像特征
2. 应用变换规律：
   - \( y = f(x - a) \)：向右平移 \( a \) 个单位（注意是 \( x - a \) 而非 \( x + a \)）
   - \( y = f(-x) \)：关于 y 轴对称

**重要提示**：多个变换时要注意先后顺序，通常先处理括号内的 x 变换，再处理外部的 y 变换。

---

**【方法论】**

函数图像变换的核心是掌握各类基本变换规律。

**平移变换**："左加右减，上加下减"
- \( y = f(x - a) \)：向右平移 \( a \) 单位
- \( y = f(x + a) \)：向左平移 \( a \) 单位
- \( y = f(x) + b \)：向上平移 \( b \) 单位

**对称变换**：
- \( y = f(-x) \)：关于 y 轴对称
- \( y = -f(x) \)：关于 x 轴对称
- \( y = f(|x|) \)：保留右半部分并对称到左边

**伸缩变换**：
- \( y = af(x) \)：纵向伸缩（\( a > 1 \) 拉伸，\( 0 < a < 1 \) 压缩）
- \( y = f(ax) \)：横向伸缩（\( a > 1 \) 压缩，\( 0 < a < 1 \) 拉伸）

**解题关键**：找准"关键点"（如极值点、零点、拐点），通过变换规律跟踪这些点的位置变化，从而确定新图像。

##END##

**示例4（化学实验题）：**

##MODULES##
化学实验
氧化还原反应

##KNOWLEDGE_POINTS##
氧化还原反应配平|氧化还原反应|primary|high
实验安全与操作|化学实验|secondary|basic

##SOLVING_HINT##
**【本题解法】**

这道题要求配平氧化还原反应方程式，步骤如下：

1. **标化合价**：标出各元素的化合价，找出化合价升降的元素
2. **确定角色**：
   - 氧化剂：化合价降低（得电子）
   - 还原剂：化合价升高（失电子）
3. **配平系数**：用化合价升降法，计算电子转移总数，使得 **升失 = 降得**
4. **配平其他物质**：用观察法配平剩余物质
5. **检查守恒**：检查原子守恒和电荷守恒

**注意**：本题中要注意介质（酸性或碱性），会影响产物的形式。

---

**【方法论】**

氧化还原反应配平的关键是 **"化合价升降法"** 和 **"电子守恒"**。

**标准步骤**：
1. 标化合价，找变价元素
2. 列出升降电子数
3. 用最小公倍数使 **升失 = 降得**
4. 配平化合价变化的物质系数
5. 用观察法配平其他物质
6. 检查原子守恒

**常见易错点**：
1. 忘记考虑一个分子中有多个相同元素原子时，电子转移数要乘以原子个数
2. 酸性条件下产物是水，碱性条件下是 OH⁻
3. 部分反应中，同一物质既是氧化剂又是还原剂（歧化反应）

**记忆口诀**：升失氧、降得还，氧化剂被还原。

##END##

**示例5（数列求和）：**

##MODULES##
数列

##KNOWLEDGE_POINTS##
错位相减法|数列|primary|high
等比数列求和|数列|secondary|high

##SOLVING_HINT##
**【本题解法】**

这道题是等差数列与等比数列乘积形式的求和，即：

\[
S_n = \sum_{{k=1}}^{{n}} a_k \cdot b_k
\]

其中 \( \{{a_k\}} \) 是等差数列，\( \{{b_k\}} \) 是等比数列。

**错位相减法步骤**：

1. 写出和式：
\[
S_n = a_1b_1 + a_2b_2 + \cdots + a_nb_n
\]

2. 两边同乘公比 \( q \)：
\[
qS_n = a_1b_2 + a_2b_3 + \cdots + a_nb_{{n+1}}
\]

3. 两式相减：
\[
S_n - qS_n = (1-q)S_n
\]

4. 右边会变成等比数列求和的形式，即可求出 \( S_n \)

**注意**：最后一项要单独处理。

---

**【方法论】**

数列求和根据数列特征选择方法。

**基本公式**：
- **等差数列**：\( S_n = \frac{{n(a_1+a_n)}}{{2}} \) 或 \( S_n = na_1 + \frac{{n(n-1)}}{{2}}d \)
- **等比数列**：\( S_n = \frac{{a_1(1-q^n)}}{{1-q}} \)（\( q \neq 1 \)）

**特殊数列求和技巧**：

1. **错位相减法**：用于"等差 × 等比"型
   - 适用：\( \sum a_n \cdot b_n \)（\( \{{a_n\}} \) 等差，\( \{{b_n\}} \) 等比）

2. **裂项相消法**：用于可裂项的分式
   - 例如：\( \frac{{1}}{{n(n+1)}} = \frac{{1}}{{n}} - \frac{{1}}{{n+1}} \)

3. **分组求和法**：将数列拆分成几个可求和的数列
   - 适用：数列可以分解为几个已知求和公式的数列

4. **倒序相加法**：\( S_n \) 正着写一遍，倒着写一遍，相加后简化
   - 适用：数列具有对称性质

**解题关键**：识别数列的通项公式特征，选择合适的方法。

##END##"""

    response = None
    try:
        llm = get_llm_provider()
        response = await llm.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=1,
            max_tokens=32768,
            thinking={"type": "enabled"},  # 启用思考模式
            reasoning_effort="medium"       # 设置推理深度为 medium
        )
        
        print(f"📋 LLM 返回的知识点分析（前300字符）: {response[:300]}...")
        
        # 解析分段标记格式
        result = parse_knowledge_points_response(response)
        
        print(f"✅ 知识点分析解析成功！")
        
        # ===== 第一步：设置学科（从参数获取） =====
        result['subject'] = subject
        
        # ===== 第二步：验证和规范化模块列表 =====
        modules_list = result.get('modules', [])
        
        if not isinstance(modules_list, list):
            modules_list = []
        
        if not modules_list:
            modules_list = ['未分类']
        
        # 验证每个模块是否在可用列表中
        validated_modules = []
        validated_module_ids = {}  # {module_name: module_id}
        
        for module_name in modules_list:
            # 容错处理：处理可能包含的额外格式
            original_name = module_name
            
            # 1. 如果包含括号（如"模块名 (描述)"），只取括号前的部分
            if '(' in module_name or '（' in module_name:
                module_name = module_name.split('(')[0].split('（')[0].strip()
            
            # 2. 如果包含冒号（如"模块名：描述"），只取冒号前的部分
            if '：' in module_name or ':' in module_name:
                module_name = module_name.split('：')[0].split(':')[0].strip()
            
            if original_name != module_name:
                print(f"⚠ 自动修正模块名: '{original_name}' -> '{module_name}'")
            
            if module_name in modules_dict:
                validated_modules.append(module_name)
                validated_module_ids[module_name] = modules_dict[module_name]
                print(f"✓ 模块匹配: {module_name}")
            else:
                print(f"⚠ 模块 '{module_name}' 不在列表中，忽略")
        
        # 如果所有模块都无效，使用"未分类"
        if not validated_modules:
            print(f"⚠ 无有效模块，使用'未分类'")
            validated_modules = ['未分类']
            if '未分类' in modules_dict:
                validated_module_ids['未分类'] = modules_dict['未分类']
        
        # ===== 第三步：验证和规范化知识点 =====
        knowledge_points = result.get('knowledgePoints', [])
        
        if not isinstance(knowledge_points, list):
            knowledge_points = []
        
        if not knowledge_points:
            knowledge_points = [{'name': '未分类', 'module': validated_modules[0], 'category': 'primary', 'importance': 'normal'}]
        
        # 处理每个知识点
        processed_kps = []
        primary_kps = []  # 主要考点列表（category=primary的）
        
        for kp in knowledge_points:
            if not isinstance(kp, dict):
                print(f"⚠ 知识点格式错误，跳过: {kp}")
                continue
            
            kp_name = kp.get('name', '')
            kp_module = kp.get('module', validated_modules[0])
            kp_category = kp.get('category', 'secondary')  # 默认次要
            kp_importance = kp.get('importance', 'normal')  # 默认普通
            
            # 容错处理：处理可能包含的额外格式
            if isinstance(kp_module, str):
                original_module = kp_module
                
                # 1. 如果包含括号（如"模块名 (描述)"），只取括号前的部分
                if '(' in kp_module or '（' in kp_module:
                    kp_module = kp_module.split('(')[0].split('（')[0].strip()
                
                # 2. 如果包含冒号（如"模块名：描述"），只取冒号前的部分
                if '：' in kp_module or ':' in kp_module:
                    kp_module = kp_module.split('：')[0].split(':')[0].strip()
                
                if original_module != kp_module:
                    print(f"⚠ 自动修正知识点模块名: '{original_module}' -> '{kp_module}'")
            
            # 确保 category 是有效值
            if kp_category not in ['primary', 'secondary', 'related']:
                kp_category = 'secondary'
            
            # 确保 importance 是有效值
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
            
            # 记录主要考点（category=primary 表示这道题的主要考点）
            if kp_category == 'primary':
                primary_kps.append({
                    'name': kp_name,
                    'module': kp_module,
                    'moduleId': module_id,
                    'category': kp_category,
                    'importance': kp_importance
                })
            
            processed_kps.append({
                'name': kp_name,
                'module': kp_module,
                'moduleId': module_id,
                'category': kp_category,
                'importance': kp_importance
            })
        
        # ===== 第四步：提取解题提示 =====
        solving_hint = result.get('solvingHint', '')
        if not solving_hint or not isinstance(solving_hint, str):
            solving_hint = ''
        solving_hint = solving_hint.strip()  # 不限制长度，让 LLM 详细说明
        
        print(f"📝 解题提示: {solving_hint[:50]}..." if solving_hint else "⚠ 未提供解题提示")
        print(f"🎯 主要考点（category=primary）: {len(primary_kps)} 个")
        for kp in primary_kps:
            print(f"   - {kp['name']} (重要性: {kp['importance']})")
        
        # 返回处理后的结果
        return {
            'subject': subject,
            'modules': validated_modules,
            'moduleIds': list(validated_module_ids.values()),
            'knowledgePoints': processed_kps,
            'primaryKnowledgePoints': primary_kps,  # 主要考点列表（category=primary的）
            'solvingHint': solving_hint  # 解题提示
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {str(e)}, 响应: {response if response else '无响应'}")
        raise ValueError(f"知识点分析失败: {str(e)}")
    except Exception as e:
        print(f"知识点分析失败: {str(e)}")
        raise



