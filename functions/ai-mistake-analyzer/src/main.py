"""
L2: ai-mistake-analyzer
AI错题深度分析 - 诊断错误原因，提供学习建议
"""
import sys
sys.path.append('../shared')

import json
from ai_client import chat_completion
from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_MISTAKE_RECORDS, COLLECTION_QUESTIONS
from utils import success_response, error_response, parse_request_body
import asyncio


ANALYSIS_PROMPT = """你是一个资深教育专家，擅长分析学生的学习问题。

学生错题信息：
题目：{question_content}
学生答案：{user_answer}
正确答案：{correct_answer}
学生选择的错因：{error_reason}

请深度分析这道错题，返回JSON格式：

{{
  "mistakeAnalysis": {{
    "errorType": "conceptual/procedural/careless",
    "rootCause": "根本原因描述",
    "missingKnowledge": ["缺失的知识点1", "缺失的知识点2"],
    "commonMistakes": "这类题目的常见错误",
    "difficulty": "题目难度分析"
  }},
  "learningPath": {{
    "immediate": ["立即需要做的事1", "立即需要做的事2"],
    "practice": ["练习建议1", "练习建议2"],
    "longTerm": "长期学习建议"
  }},
  "encouragement": "鼓励的话（温和、正向）",
  "nextSteps": "下一步建议"
}}

要求：
1. 语气温和、正向、鼓励
2. 分析要具体、有针对性
3. 建议要可操作

只返回JSON，不要其他内容。"""


async def analyze_mistake(mistake_record: dict, question: dict) -> dict:
    """Analyze a mistake using AI"""
    prompt = ANALYSIS_PROMPT.format(
        question_content=question.get('content', ''),
        user_answer=mistake_record.get('userAnswer', '未知'),
        correct_answer=question.get('answer', ''),
        error_reason=mistake_record.get('errorReason', '未知')
    )
    
    messages = [
        {"role": "system", "content": "You are an expert educator analyzing student mistakes."},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat_completion(messages, temperature=0.7, max_tokens=1500)
    
    # Parse JSON response
    import re
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError("Failed to parse AI response")


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        mistake_id = body.get('mistakeRecordId')
        
        if not mistake_id:
            return res.json(error_response("mistakeRecordId is required"))
        
        databases = get_databases()
        
        # Get mistake record
        mistake = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MISTAKE_RECORDS,
            document_id=mistake_id
        )
        
        # Get question
        question = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_QUESTIONS,
            document_id=mistake['questionId']
        )
        
        # Analyze
        analysis = asyncio.run(analyze_mistake(mistake, question))
        
        return res.json(success_response(analysis, "Analysis complete"))
        
    except Exception as e:
        import traceback
        return res.json(error_response(str(e), 500, traceback.format_exc()))

