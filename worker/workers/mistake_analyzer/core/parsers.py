"""
解析器模块
负责解析 LLM 返回的分段标记格式响应
"""
import re
import json
from typing import Dict


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


def _clean_code_blocks(response: str) -> str:
    """清理代码块标记的通用函数"""
    response = response.strip()
    if response.startswith('```'):
        lines = response.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        response = '\n'.join(lines)
    return response


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
    response = _clean_code_blocks(response)
    sections = {}
    
    # 提取 TYPE
    type_match = re.search(r'##TYPE##\s*\n\s*(\w+)', response, re.IGNORECASE)
    if type_match:
        sections['type'] = type_match.group(1).strip()
    
    # 提取 SUBJECT
    subject_match = re.search(r'##SUBJECT##\s*\n\s*(\w+)', response, re.IGNORECASE)
    if subject_match:
        sections['subject'] = subject_match.group(1).strip()
    
    # 提取 CONTENT（到下一个标记为止，##OPTIONS## 或 ##PIC## 或 ##END## 可选）
    content_match = re.search(r'##CONTENT##\s*\n(.*?)(?=##OPTIONS##|##PIC##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if content_match:
        sections['content'] = content_match.group(1).strip()
    
    # 提取 OPTIONS（如果存在，##PIC## 或 ##END## 可选）
    options_match = re.search(r'##OPTIONS##\s*\n(.*?)(?=##PIC##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if options_match:
        options_text = options_match.group(1).strip()
        sections['options'] = [line.strip() for line in options_text.split('\n') if line.strip()] if options_text else []
    else:
        sections['options'] = []

    # 提取 PIC（如果存在，##END## 可选）
    pic_match = re.search(r'##PIC##\s*\n(.*?)(?=##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if pic_match:
        pic_text = pic_match.group(1).strip()
        if pic_text:
            # 解析 bbox 列表: [index] <bbox>x1 y1 x2 y2</bbox>
            bboxes = []
            for line in pic_text.split('\n'):
                line = line.strip()
                if not line: continue
                
                # 尝试匹配带索引的
                idx_bbox_match = re.search(r'\[(\d+)\]\s*<bbox>\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*</bbox>', line)
                if idx_bbox_match:
                    bboxes.append({
                        'index': int(idx_bbox_match.group(1)) - 1, # 转为 0-based
                        'bbox': [
                            int(idx_bbox_match.group(2)), 
                            int(idx_bbox_match.group(3)), 
                            int(idx_bbox_match.group(4)), 
                            int(idx_bbox_match.group(5))
                        ]
                    })
                    continue
                
                # 尝试匹配不带索引的 (默认第0张图)
                bbox_match = re.search(r'<bbox>\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*</bbox>', line)
                if bbox_match:
                    bboxes.append({
                        'index': 0,
                        'bbox': [
                            int(bbox_match.group(1)), 
                            int(bbox_match.group(2)), 
                            int(bbox_match.group(3)), 
                            int(bbox_match.group(4))
                        ]
                    })

            if bboxes:
                sections['bboxes'] = bboxes
    
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
    response = _clean_code_blocks(response)
    sections = {}
    
    # 提取 MODULES
    modules_match = re.search(r'##MODULES##\s*\n(.*?)(?=##KNOWLEDGE_POINTS##|##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if modules_match:
        modules_text = modules_match.group(1).strip()
        sections['modules'] = [line.strip() for line in modules_text.split('\n') if line.strip()] if modules_text else []
    else:
        sections['modules'] = []
    
    # 提取 KNOWLEDGE_POINTS
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
    
    # 提取 SOLVING_HINT
    hint_match = re.search(r'##SOLVING_HINT##\s*\n(.*?)(?=##END##|$)', response, re.DOTALL | re.IGNORECASE)
    if hint_match:
        sections['solvingHint'] = hint_match.group(1).strip()
        print(f"✓ 成功提取解题提示，长度: {len(sections['solvingHint'])} 字符")
    else:
        sections['solvingHint'] = ''
        if '##SOLVING_HINT##' in response.upper():
            print(f"⚠️ 发现 ##SOLVING_HINT## 标记但无法匹配，响应末尾100字符: ...{response[-100:]}")
        else:
            print(f"⚠️ 响应中不包含 ##SOLVING_HINT## 标记")
    
    # 验证必需字段，设置默认值
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
    策略：保留合法的 JSON 转义序列，将其他单反斜杠转换为双反斜杠
    
    Args:
        json_str: 待修复的 JSON 字符串
        
    Returns:
        修复后的 JSON 字符串
    """
    result = []
    i = 0
    in_string = False
    escape_next = False
    
    while i < len(json_str):
        char = json_str[i]
        
        if char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
            i += 1
            continue
        
        if in_string:
            if escape_next:
                # 合法的 JSON 转义序列保持不变
                if char in 'ntrfb"\\/':
                    result.append(char)
                else:
                    # 不是合法的转义序列，在反斜杠前再加一个反斜杠
                    result.append('\\')
                    result.append(char)
                escape_next = False
            elif char == '\\':
                result.append(char)
                escape_next = True
            else:
                result.append(char)
        else:
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
    # 尝试1：直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e1:
        print(f"⚠️ {debug_name} 解析失败（第1次）: {str(e1)}")
        print(f"   错误位置附近的内容: ...{json_str[max(0, e1.pos-30):e1.pos+30]}...")
    
    # 尝试2：使用 strict=False
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
    
    # 尝试4：激进的修复
    try:
        aggressive_fix = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_str)
        print(f"🔧 尝试激进修复（所有单反斜杠加倍）...")
        return json.loads(aggressive_fix)
    except json.JSONDecodeError as e4:
        print(f"⚠️ {debug_name} 解析失败（第4次，激进修复）: {str(e4)}")
    
    # 所有尝试都失败
    print(f"❌ {debug_name} 解析彻底失败！")
    print(f"📄 完整 JSON 内容：\n{json_str}\n")
    raise ValueError(f"{debug_name} 解析失败：尝试了4种方法都无法解析。最后一次错误：{str(e4)}")

