"""
题目生成提示词模板
"""

SYSTEM_PROMPT = """你是一个专业的教育题目生成助手，擅长根据已有题目生成高质量的变式题。

**核心原则：**
1. 保持核心知识点和考查目的完全一致
2. 改变题目的表现形式（场景、数值、问法、题型等）
3. 保持难度等级相同或相近
4. 确保生成的题目逻辑严密、表述清晰
5. 答案和解析必须准确无误
6. 所有数学、物理、化学公式使用 LaTeX 格式

**变式策略：**
- 改变题目场景（如：从购物场景改为旅游场景）
- 改变数值和单位（如：价格、距离、时间等）
- 改变题目问法（如：正向问改为反向问）
- 改变题型（如：选择题改为填空题，但保持知识点不变）
- 改变示例对象（如：从苹果改为橙子）

**LaTeX 格式要求：**
- 行内公式：\( ... \)
- 独立公式：\[ ... \]（独立成行）
- LaTeX 公式直接书写，不需要转义反斜杠

**输出格式：**
使用分段标记格式，避免 JSON 转义问题"""

VARIANT_GENERATION_PROMPT_TEMPLATE = """请根据以下源题目生成 {count} 道变式题。

**源题目信息：**
科目：{subject}
类型：{question_type}
难度：{difficulty}
题目内容：
{content}

{options_text}

答案：{answer}

{explanation_text}

**要求：**
1. 生成 {count} 道变式题
2. 保持相同的知识点考查目标
3. 改变题目的表现形式（场景、数值、问法等）
4. 可以适当改变题型，但知识点必须一致
5. 难度保持在 {difficulty} 左右（允许 ±1）
6. 所有公式使用 LaTeX 格式（行内 \( ... \)，独立 \[ ... \]）
7. LaTeX 直接书写，不需要转义

**返回格式（分段标记，不要用代码块包裹）：**

每道题目使用以下格式：

##QUESTION##

##TYPE##
题目类型（choice/fillBlank/shortAnswer/essay）

##DIFFICULTY##
难度等级（1-5的数字）

##CONTENT##
题目内容（Markdown + LaTeX，公式直接书写）

##OPTIONS##
A. 选项1
B. 选项2
...
（如果不是选择题，此部分留空）

##ANSWER##
答案

##EXPLANATION##
解析（Markdown + LaTeX）

##END##

**示例（数学选择题）：**

##QUESTION##

##TYPE##
choice

##DIFFICULTY##
3

##CONTENT##
已知函数 \( f(x) = x^2 + 2x + 1 \)，求 \( f(-1) \) 的值是（）

##OPTIONS##
A. 0
B. 1
C. 2
D. 4

##ANSWER##
A

##EXPLANATION##
将 \( x = -1 \) 代入函数：

\[
f(-1) = (-1)^2 + 2(-1) + 1 = 1 - 2 + 1 = 0
\]

因此答案是 A。

##END##

**示例（物理填空题）：**

##QUESTION##

##TYPE##
fillBlank

##DIFFICULTY##
3

##CONTENT##
质量为 \( m = 2 \text{{ kg}} \) 的物体受到 \( F = 10 \text{{ N}} \) 的力，根据牛顿第二定律 \( F = ma \)，则加速度 \( a \) = ______。

##OPTIONS##

##ANSWER##
\( 5 \text{{ m/s}}^2 \)

##EXPLANATION##
根据牛顿第二定律：

\[
a = \frac{{F}}{{m}} = \frac{{10}}{{2}} = 5 \text{{ m/s}}^2
\]

##END##

**重要：**
- 如果生成多道题，每道题都用 ##QUESTION## 开始，##END## 结束
- 标记符号必须独占一行
- 行内公式用 \( ... \)，独立公式用 \[ ... \]
- LaTeX 直接书写，不需要转义反斜杠
- OPTIONS 部分如果不是选择题，留空即可（但标记要保留）

现在请生成 {count} 道变式题：
"""

def build_variant_prompt(question_data: dict, variants_count: int = 1) -> str:
    """
    构建变式题生成提示词
    
    Args:
        question_data: 源题目数据
        variants_count: 需要生成的变式题数量
        
    Returns:
        完整的提示词
    """
    
    # 题目类型映射
    type_map = {
        'choice': '选择题',
        'fill_blank': '填空题',
        'true_false': '判断题',
        'essay': '简答题',
        'calculation': '计算题'
    }
    
    # 科目映射
    subject_map = {
        'math': '数学',
        'physics': '物理',
        'chemistry': '化学',
        'chinese': '语文',
        'english': '英语'
    }
    
    # 提取题目信息
    subject = subject_map.get(question_data.get('subject', ''), question_data.get('subject', '未知'))
    question_type = type_map.get(question_data.get('type', ''), question_data.get('type', '未知'))
    difficulty = question_data.get('difficulty', 3)
    content = question_data.get('content', '')
    answer = question_data.get('answer', '')
    explanation = question_data.get('explanation', '')
    options = question_data.get('options', [])
    
    # 构建选项文本
    options_text = ""
    if options and len(options) > 0:
        options_text = "选项：\n"
        for i, option in enumerate(options):
            label = chr(65 + i)  # A, B, C, D...
            options_text += f"{label}. {option}\n"
    
    # 构建解析文本
    explanation_text = ""
    if explanation:
        explanation_text = f"解析：{explanation}"
    
    # 生成提示词
    prompt = VARIANT_GENERATION_PROMPT_TEMPLATE.format(
        count=variants_count,
        subject=subject,
        question_type=question_type,
        difficulty=difficulty,
        content=content,
        options_text=options_text,
        answer=answer,
        explanation_text=explanation_text
    )
    
    return prompt

