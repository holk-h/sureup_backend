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
import asyncio
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
    
    # 提取 CONTENT（到下一个标记为止，##OPTIONS## 或 ##END## 可选）
    content_match = re.search(r'##CONTENT##\s*\n(.*?)(?=##OPTIONS##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if content_match:
        sections['content'] = content_match.group(1).strip()
    
    # 提取 OPTIONS（如果存在，##END## 可选）
    options_match = re.search(r'##OPTIONS##\s*\n(.*?)(?=##END##|$)', response, re.DOTALL | re.IGNORECASE)
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
    
    # 提取 MODULES（##KNOWLEDGE_POINTS## 或 ##END## 可选）
    modules_match = re.search(r'##MODULES##\s*\n(.*?)(?=##KNOWLEDGE_POINTS##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
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
    
    # 提取 KNOWLEDGE_POINTS（##SOLVING_HINT## 或 ##END## 可选）
    kp_match = re.search(r'##KNOWLEDGE_POINTS##\s*\n(.*?)(?=##SOLVING_HINT##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
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
    
    # 提取 SOLVING_HINT（##END## 可选，如果没有就匹配到结尾）
    hint_match = re.search(r'##SOLVING_HINT##\s*\n(.*?)(?=##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if hint_match:
        hint_content = hint_match.group(1).strip()
        sections['solvingHint'] = hint_content
        print(f"✓ 成功提取解题提示，长度: {len(hint_content)} 字符")
    else:
        sections['solvingHint'] = ''
        # 调试：检查是否存在 ##SOLVING_HINT## 标记
        if '##SOLVING_HINT##' in response.upper():
            print(f"⚠️ 发现 ##SOLVING_HINT## 标记但无法匹配，响应末尾100字符: ...{response[-100:]}")
        else:
            print(f"⚠️ 响应中不包含 ##SOLVING_HINT## 标记")
    
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
    
    # 清理 base64 字符串，去除可能的前缀
    clean_image_base64 = clean_base64(image_base64)
    
    if not clean_image_base64:
        raise ValueError("图片数据无效")
    
    # 分析图片：识别学科 + OCR + 知识点
    analysis_result = await analyze_with_llm_vision(
        clean_image_base64, 
        user_id, 
        databases,
        user_feedback=user_feedback,
        previous_result=previous_result
    )
    
    return analysis_result


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
        # 第一步：OCR 提取题目内容和学科识别
        step1 = await extract_question_content(
            image_base64,
            user_feedback=user_feedback,
            previous_result=previous_result
        )
        
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
    system_prompt = """你是专业的题目 OCR 识别专家，精确提取题目文字并识别学科。

**核心要求：**
1. **准确提取**：逐字逐句识别，不遗漏不添加，忽略手写痕迹
2. **公式精确**：数学、物理、化学公式必须用 LaTeX，保持原题结构
3. 行内公式：\( ... \)，独立公式：\[ ... \]（独立成行）
4. 识别完整公式：分数、根号、积分、求和、矩阵等
5. 分段标记格式，LaTeX 直接书写，不转义"""
    
    # 构建用户 prompt，如果有用户反馈则加入
    user_feedback_section = ""
    if user_feedback and previous_result:
        # 构建上次识别结果的展示
        prev_content = previous_result.get('content', '无')
        prev_type = previous_result.get('type', '无')
        prev_subject = previous_result.get('subject', '无')
        prev_options = previous_result.get('options', [])
        prev_options_text = '\n'.join(prev_options) if prev_options else '无'
        
        user_feedback_section = f"""

🚨🚨🚨 **重要：用户反馈（上次识别出现了错误）** 🚨🚨🚨

**上次你识别的结果：**
- 题目类型：{prev_type}
- 学科：{prev_subject}
- 题目内容：
{prev_content}
- 选项：
{prev_options_text}

**用户指出的错误：**
{user_feedback}

❗❗❗ **请仔细对比上次的识别结果和用户反馈，找出错误在哪里，这次务必修正！** ❗❗❗

---

"""
    elif user_feedback:
        # 如果只有反馈没有上次结果
        user_feedback_section = f"""

🚨🚨🚨 **重要：用户反馈（识别出现了错误）** 🚨🚨🚨

**用户指出的问题：**
{user_feedback}

❗❗❗ **请务必特别注意上述问题，优先修正这些错误！** ❗❗❗

---

"""
    
    # 构建多图提示
    multi_image_hint = ""
    if len(image_base64_list) > 1:
        multi_image_hint = f"""
**重要提示：这是一道跨页题目，共 {len(image_base64_list)} 张图片！**
- 图片按顺序展示了题目的不同部分（可能是题目、图表、选项分布在不同页）
- 请综合所有图片的内容，整合为一道完整的题目
- 所有页面的内容都属于同一道题，请完整提取

"""
    
    user_prompt = rf"""请识别{'这道跨页题目（共 ' + str(len(image_base64_list)) + ' 张图片）' if len(image_base64_list) > 1 else '这张题目图片'}，提取信息。

{multi_image_hint}**要提取的内容：**
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

**示例4 - 选择题（化学）：**

##TYPE##
choice

##SUBJECT##
chemistry

##CONTENT##
下列转化中，能一步实现的是（）

##OPTIONS##
A. \( \text{{Na}} \rightarrow \text{{Na}}_2\text{{O}}_2 \)
B. \( \text{{Cl}}_2 \rightarrow \text{{FeCl}}_3 \)
C. \( \text{{SO}}_3 \rightarrow \text{{Na}}_2\text{{SO}}_4 \)
D. \( \text{{Fe}}_2\text{{O}}_3 \rightarrow \text{{Fe(OH)}}_3 \)

##END##

**LaTeX 常用语法：**
- 分数：\frac{{a}}{{b}}
- 上标：x^2, x^{{n+1}}
- 下标：x_i, a_{{ij}}
- 根号：\sqrt{{x}}, \sqrt[3]{{x}}
- 积分：\int_a^b
- 求和：\sum_{{i=1}}^n
- 希腊字母：\alpha, \beta, \theta, \pi
- 运算符：\times, \div, \pm, \leq, \geq
- 矩阵：\begin{{bmatrix}} ... \end{{bmatrix}}
- **化学式**（重要！）：使用 \text{{}} 包裹化学元素和化合物
  * 单质：\text{{Na}}, \text{{Cl}}_2
  * 化合物：\text{{Na}}_2\text{{O}}_2, \text{{FeCl}}_3, \text{{Na}}_2\text{{SO}}_4
  * 带括号：\text{{Fe(OH)}}_3, \text{{Ca(NO}}_3\text{{)}}_2
  * 反应箭头：\rightarrow, \leftarrow, \rightleftharpoons

**重要：**
- 标记符号必须独占一行
- 行内公式用 \( ... \)，块级公式用 \[ ... \]
- LaTeX 公式直接书写，不需要转义反斜杠
- **化学式必须用 \text{{}} 包裹**，确保化学元素符号正确显示
- OPTIONS 部分如果是非选择题，留空即可

{user_feedback_section}"""

    response = None
    try:
        print(f"开始OCR识别，共 {len(image_base64_list)} 张图片")
        print(f"user_prompt: {user_prompt}")
        llm = get_llm_provider()
        response = await llm.chat_with_vision(
            prompt=user_prompt,
            image_base64=image_base64_list,  # 传递图片列表
            system_prompt=system_prompt,
            temperature=0.7,
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
    
    # 获取用户在该学科下的所有已有知识点（防止重复）
    from workers.mistake_analyzer.knowledge_point_service import get_user_knowledge_points_by_subject
    existing_knowledge_points = []
    if databases:
        try:
            kp_docs = await asyncio.to_thread(
                get_user_knowledge_points_by_subject,
                databases=databases,
                user_id=user_id,
                subject=subject
            )
            existing_knowledge_points = kp_docs
        except Exception as e:
            print(f"⚠️ 获取用户已有知识点失败: {str(e)}")
    
    # 构建已有知识点列表文本（按模块分组）
    knowledge_points_text = ""
    if existing_knowledge_points:
        # 按模块分组
        kp_by_module = {}
        for kp in existing_knowledge_points:
            module_id = kp.get('moduleId')
            if module_id:
                if module_id not in kp_by_module:
                    kp_by_module[module_id] = []
                kp_by_module[module_id].append(kp['name'])
        
        # 构建文本
        if kp_by_module:
            kp_text_list = []
            for mod in available_modules:
                mod_id = mod['$id']
                mod_name = mod['name']
                if mod_id in kp_by_module:
                    kps = kp_by_module[mod_id]
                    kp_text_list.append(f"**{mod_name}**：{', '.join(kps)}")
            
            if kp_text_list:
                knowledge_points_text = "\n".join(kp_text_list)
                print(f"✓ 已获取 {len(existing_knowledge_points)} 个已有知识点，供 LLM 参考以防止重复")
    
    system_prompt = """你是学科知识点分析专家，专注于精确识别题目的考点。

核心原则：
- 必须从提供的模块列表中选择
- **优先使用已有知识点**：如果用户已经有相同或相近的知识点，直接使用，避免创建重复或相似的知识点
- **知识点要精确**：使用标准学术术语，避免模糊表达
- 区分题目角色（category）和知识点重要性（importance）

分析要点：
1. **模块选择**：选择题目主要考查内容所在的模块（通常1个，综合题可能2个）
2. **知识点提取**（关键！）：
   - **首先检查已有知识点列表**：如果题目考查的内容在用户已有知识点中存在，直接使用该知识点名称
   - 只有当确实是新的知识点时，才创建新知识点
   - 必须精确、具体，如"一元二次方程判别式"而非"方程"
   - 避免过度概括（太宽泛）或过度细分（太琐碎）
   - 通常1-3个知识点，主要考点1-2个
   - **防止重复**：避免创建与已有知识点含义相同但表述略有不同的知识点
3. **category（题目角色）**：
   - primary：这道题的主要考点，直接考查的核心内容
   - secondary：次要考点，间接涉及的内容
   - related：相关但不直接考查的内容
4. **importance（知识点重要性）**：
   - high：考试高频考点，核心重点知识
   - basic：基础必会内容，其他知识的前置
   - normal：普通考点
5. **解题提示**（核心！）：
   - 分两部分：【本题思路点拨】+【方法论】
   - **本题思路点拨**：用温和、启发的语气点拨思考方向
     * **重要**：只做思维启发和方向指引，不给出具体解题步骤（避免计算错误）
     * **必须包含**："为什么会想到这个思路"的思维启发
     * 点明关键突破口、核心思想、需要注意的地方
     * 可以提示用哪些公式或方法，但不展开具体计算
   - **方法论**：通俗易懂地总结这类题的通用方法、重点、易错点
     * 用清晰的语言，适当使用比喻，但不要过于幼稚
     * 语气要鼓励、积极，让学生感到可以掌握
   - 可使用 LaTeX 公式说明概念
   - 目标：启发学生的思维方式，让学生自己去思考和尝试，而不是照搬步骤"""
    
    available_modules_hint = ""
    if modules_text:
        available_modules_hint = f"""

**可用模块列表（必须从中选择）：**
{modules_text}"""
    else:
        available_modules_hint = "\n\n**注意**：系统暂无模块数据，请使用\"未分类\"。"
    
    # 构建已有知识点提示
    existing_kp_hint = ""
    if knowledge_points_text:
        existing_kp_hint = f"""

**用户已有的知识点（优先使用这些，避免重复）：**
{knowledge_points_text}

⚠️ **重要**：提取知识点时，请先检查上面的已有知识点列表。如果题目考查的内容与已有知识点相同或相近，请直接使用已有的知识点名称，不要创建新的重复知识点。"""
    
    # 获取学科中文名称
    from workers.mistake_analyzer.utils import get_subject_chinese_name
    subject_chinese = get_subject_chinese_name(subject)
    
    user_prompt = rf"""分析这道{subject_chinese}题目，提取模块、知识点和解题提示。

**题目：**
{content}
{available_modules_hint}
{existing_kp_hint}

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
   - **知识点名**：
     * **优先使用已有知识点**：如果用户已有知识点中存在相同或相近的知识点，直接使用已有的名称
     * 只有当确实是新知识点时，才填写新的知识点名称
     * 必须精确、具体，如"一元二次方程判别式"而非"方程"
   - **category**（题目中的角色）：primary（主要考点）/ secondary（次要）/ related（相关）
   - **importance**（知识点重要性）：high（高频考点）/ basic（基础）/ normal（普通）
3. **SOLVING_HINT**：分【本题思路点拨】和【方法论】两部分，**语气要温和启发、通俗易懂**
   - **重要原则**：只做思维启发，不给具体解题步骤（避免计算错误）
   - **本题思路点拨**：
     * 必须说明"为什么会想到这个思路"（思维启发）
     * 点明关键突破口、核心思想、需要注意什么
     * 可以提示用哪些公式或方法，但不展开具体步骤
     * 用"关键在于"、"核心思想"、"突破口"等引导性表达
   - **方法论部分**：用清晰语言总结通用方法、重点、易错点，适当使用比喻但不过于口语化
   - 目标：启发思维，引导学生自己思考，而不是给出完整解答

**示例1（一元二次方程判别式）：**

##MODULES##
二次函数

##KNOWLEDGE_POINTS##
一元二次方程判别式|二次函数|primary|high

##SOLVING_HINT##
**【本题思路点拨】**

**从哪入手？** 看到题目中 \( m \)、\( n \) 是方程的根，而要求的式子又包含 \( m^2 + 2019m + 6 \) 这样的二次式，会自然想到：能不能利用"根满足方程"这个性质来简化？

**关键突破口：**
- 题目给出的是方程的根，这提示我们可以用两个性质：韦达定理 + 根满足方程
- 核心思想：观察 \( m^2 + 2019m + 6 \) 与方程 \( x^2 + 2020x + 7 = 0 \) 的系数关系，能否通过巧妙变形，把"根满足方程"这个条件用上？
- 如果能将式子改写成包含 \( m^2 + 2020m + 7 \) 的形式，就可以直接用 \( m^2 + 2020m + 7 = 0 \) 来简化

**思维方向：**
尝试对代数式进行"凑"的变换，让原方程的形式出现，然后利用根的性质将其化为 0，从而大大简化计算。对另一个因式采用同样的思路，最后整体相乘。

---

**【方法论】**

判别式 \( \Delta = b^2 - 4ac \) 是判断方程根情况的工具：
- \( \Delta > 0 \)：两个不等实根
- \( \Delta = 0 \)：两个相等实根
- \( \Delta < 0 \)：无实根

**韦达定理**让我们无需求出具体根值就能处理根的关系式：
- 两根之和：\( x_1 + x_2 = -\frac{{b}}{{a}} \)
- 两根之积：\( x_1 x_2 = \frac{{c}}{{a}} \)

**解题建议**：遇到包含方程根的复杂代数式时，有两个常用技巧：
1. 利用韦达定理建立根之间的关系
2. 利用"根满足方程"的性质进行巧妙代换

掌握这两种方法可以大大简化计算过程。

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
**【本题思路点拨】**

**思路是什么？** 力学和运动学结合题的本质是：力产生加速度，加速度决定运动。所以解题思路自然是"力→加速度→运动"这条主线。

**关键突破口：**
- **第一步思路**：画受力图，这是理解问题的基础。明确物体受到哪些力，每个力的方向如何
- **核心桥梁**：加速度是连接"力"和"运动"的关键。用牛顿第二定律 \( F_{{合}} = ma \) 求出加速度
- **选择工具**：根据题目给的条件和要求，选择合适的运动学公式：
  * 如果涉及时间，用 \( v = v_0 + at \) 或 \( s = v_0 t + \frac{{1}}{{2}}at^2 \)
  * 如果不涉及时间，用 \( v^2 - v_0^2 = 2as \)

**思维方向：**
抓住"加速度"这个桥梁，从受力分析入手，通过牛顿第二定律连接到运动学。注意力的分解和合成，特别是斜面问题。

---

**【方法论】**

力学与运动学综合题的核心解题流程：**力→加速度→运动**

**核心理念**：加速度是连接力和运动的桥梁。必须先通过受力分析求出加速度，再用运动学公式处理运动过程。

**常见易错点**：
1. 受力分析不完整或力的方向标错
2. 忘记将合力分解到运动方向上（对于斜面等问题尤其要注意）
3. 混淆公式的适用条件（这些公式仅适用于匀变速直线运动）

**解题建议**：
- 区分静摩擦力（平衡力）和滑动摩擦力（阻力）
- 遇到复杂受力情况时，建议使用正交分解法，将力分解为水平和竖直两个方向分别处理

##END##

**示例3（函数图像与性质）：**

##MODULES##
函数

##KNOWLEDGE_POINTS##
函数单调性|函数|primary|high
函数图像变换|函数|secondary|normal

##SOLVING_HINT##
**【本题思路点拨】**

**思路是什么？** 函数图像变换本质上是坐标的系统性改变。理解变换规律后，可以通过跟踪关键点的位置变化来确定新图像。

**关键突破口：**
- **核心方法**：找出基础函数的几个关键点（如极值点、零点、拐点），看这些点经过变换后移动到哪里
- **变换规律**：
  * \( y = f(x - a) \) 是平移变换（注意"\( x - a \)"表示向右平移）
  * \( y = f(-x) \) 是对称变换（关于 y 轴对称）
- **变换顺序**：多个变换同时出现时，先处理括号内对 x 的变换，再处理外部对 y 的变换

**思维方向：**
记住口诀"左加右减，上加下减"，但更重要的是理解为什么。通过几个关键点的位置跟踪，就能画出变换后的图像。

---

**【方法论】**

函数图像变换包括平移、对称和伸缩三大类，掌握规律是关键。

**平移变换**：口诀"左加右减，上加下减"
- \( y = f(x - a) \)：向右平移 \( a \) 个单位
- \( y = f(x + a) \)：向左平移 \( a \) 个单位
- \( y = f(x) + b \)：向上平移 \( b \) 个单位

**对称变换**：
- \( y = f(-x) \)：关于 y 轴对称（左右对调）
- \( y = -f(x) \)：关于 x 轴对称（上下翻转）
- \( y = f(|x|) \)：保留 \( x \geq 0 \) 部分，再关于 y 轴对称

**伸缩变换**：
- \( y = af(x) \)：纵向伸缩（\( a > 1 \) 时拉伸，\( 0 < a < 1 \) 时压缩）
- \( y = f(ax) \)：横向伸缩（\( a > 1 \) 时压缩，\( 0 < a < 1 \) 时拉伸）

**解题技巧**：找出函数图像的关键点（如极值点、零点、拐点），通过变换规律确定这些点的新位置，从而得到变换后的图像。

##END##

**示例4（化学实验题）：**

##MODULES##
化学实验
氧化还原反应

##KNOWLEDGE_POINTS##
氧化还原反应配平|氧化还原反应|primary|high
实验安全与操作|化学实验|secondary|basic

##SOLVING_HINT##
**【本题思路点拨】**

**可以想到什么？** 氧化还原反应的本质是电子转移，所以配平的关键在于保证电子守恒——失去的电子数等于得到的电子数。

**关键突破口：**
- **核心原则**：电子守恒，即"升失 = 降得"（化合价升高失去的电子数 = 化合价降低得到的电子数）
- **思路方向**：
  * 先标化合价，找出哪些元素的化合价发生了变化
  * 分清谁是氧化剂（得电子，化合价降低），谁是还原剂（失电子，化合价升高）
  * 用化合价升降法算出电子转移数，然后用最小公倍数让"升失 = 降得"
- **注意环境**：反应介质（酸性or碱性）会影响产物形式，这点要留意

**思维方向：**
抓住"电子守恒"这个核心，先配平化合价变化的物质，再用观察法配平其他物质，最后检查原子守恒和电荷守恒。

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
**【本题思路点拨】**

**思路是什么？** 看到"等差数列 × 等比数列"的形式，直接求和很困难。但如果能让对应项"错开"后相减，可以消去大部分项，从而简化问题——这就是错位相减法的核心思想。

**关键突破口：**
- **识别特征**：这是 \( \sum a_k \cdot b_k \) 型求和，其中 \( \{{a_k\}} \) 等差，\( \{{b_k\}} \) 等比
- **核心技巧**：错位相减法
  * 写出和式 \( S_n \)
  * 两边同乘等比数列的公比 \( q \)，得到 \( qS_n \)（项的位置"错开"了）
  * 两式相减：\( S_n - qS_n = (1-q)S_n \)，右边会消去大部分项
- **注意细节**：最后一项需要单独处理

**思维方向：**
"错位相减"的精妙之处在于通过"错开"让项对齐后能相互抵消，将复杂求和转化为简单的等比数列求和。

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
            temperature=0.9,
            max_tokens=32768,
            thinking={"type": "enabled"},  # 启用思考模式
            reasoning_effort="low"       # 设置推理深度为 low
        )
        
        print(f"📋 LLM 返回的知识点分析: {response}...")
        
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



