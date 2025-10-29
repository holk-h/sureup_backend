"""
L2: ai-question-generator
AI智能出题 - 生成变式题和练习题
"""
import sys
sys.path.append('../shared')

import json
from ai_client import chat_completion
from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_QUESTIONS
from utils import success_response, error_response, parse_request_body
from appwrite.id import ID
import asyncio


VARIANT_PROMPT = """你是一个K12教育专家，擅长出题。

根据以下原题，生成{count}道变式题。要求：
1. 保持知识点和难度一致
2. 改变具体数值、条件或场景
3. 解题思路相同
4. 每道题必须包含详细解析

原题：
{original_question}

学科：{subject}
知识点：{knowledge_point}
题型：{question_type}

返回JSON数组格式：
[
  {{
    "content": "题目内容",
    "options": ["选项A", "选项B", "选项C", "选项D"],  // 仅选择题需要
    "answer": "正确答案",
    "explanation": "详细解析"
  }}
]

只返回JSON数组，不要其他内容。"""


GENERATE_PROMPT = """你是一个K12教育专家，擅长出题。

请针对以下知识点生成{count}道练习题。要求：
1. 难度：{difficulty}/5
2. 题型：{question_types}
3. 每道题必须包含详细解析

学科：{subject}
知识点：{knowledge_point}

返回JSON数组格式：
[
  {{
    "content": "题目内容",
    "type": "题型",
    "options": ["选项A", "选项B", "选项C", "选项D"],  // 仅选择题需要
    "answer": "正确答案",
    "explanation": "详细解析"
  }}
]

只返回JSON数组，不要其他内容。"""


async def generate_variant_questions(
    original_question: dict,
    count: int = 3,
    difficulty_adjust: int = 0
) -> list:
    """Generate variant questions based on original"""
    prompt = VARIANT_PROMPT.format(
        count=count,
        original_question=original_question.get('content', ''),
        subject=original_question.get('subject', ''),
        knowledge_point=original_question.get('knowledgePointName', ''),
        question_type=original_question.get('type', 'choice')
    )
    
    messages = [
        {"role": "system", "content": "You are an expert educator creating practice questions."},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat_completion(messages, temperature=0.8, max_tokens=2000)
    
    # Parse JSON response
    import re
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if json_match:
        questions = json.loads(json_match.group())
        return questions
    raise ValueError("Failed to parse AI response")


async def generate_knowledge_point_questions(
    subject: str,
    knowledge_point: str,
    count: int = 5,
    difficulty: int = 3,
    question_types: list = None
) -> list:
    """Generate questions for a knowledge point"""
    if not question_types:
        question_types = ['choice', 'fill_blank']
    
    prompt = GENERATE_PROMPT.format(
        count=count,
        difficulty=difficulty,
        question_types=', '.join(question_types),
        subject=subject,
        knowledge_point=knowledge_point
    )
    
    messages = [
        {"role": "system", "content": "You are an expert educator creating practice questions."},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat_completion(messages, temperature=0.8, max_tokens=2000)
    
    # Parse JSON response
    import re
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if json_match:
        questions = json.loads(json_match.group())
        return questions
    raise ValueError("Failed to parse AI response")


async def save_questions(questions: list, subject: str, kp_id: str) -> list:
    """Save generated questions to database"""
    databases = get_databases()
    saved = []
    
    for q in questions:
        doc = databases.create_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_QUESTIONS,
            document_id=ID.unique(),
            data={
                'subject': subject,
                'knowledgePointId': kp_id,
                'type': q.get('type', 'choice'),
                'difficulty': 3,
                'content': q['content'],
                'options': q.get('options', []),
                'answer': q['answer'],
                'explanation': q['explanation'],
                'source': 'ai_generated',
                'metadata': {'generationMethod': 'ai'}
            }
        )
        saved.append(doc)
    
    return saved


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        mode = body.get('mode', 'variant')
        
        if mode == 'variant':
            # Generate variant questions
            source_question_id = body.get('sourceQuestionId')
            if not source_question_id:
                return res.json(error_response("sourceQuestionId is required"))
            
            # Get original question
            databases = get_databases()
            original = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_QUESTIONS,
                document_id=source_question_id
            )
            
            count = body.get('count', 3)
            questions = asyncio.run(generate_variant_questions(original, count))
            
            # Save to database
            saved = asyncio.run(save_questions(
                questions,
                original['subject'],
                original['knowledgePointId']
            ))
            
            return res.json(success_response({
                'questions': saved,
                'totalGenerated': len(saved)
            }))
            
        elif mode == 'knowledge_point':
            # Generate questions for knowledge point
            kp_id = body.get('knowledgePointId')
            subject = body.get('subject')
            kp_name = body.get('knowledgePointName')
            
            if not all([kp_id, subject, kp_name]):
                return res.json(error_response("Missing required fields"))
            
            count = body.get('count', 5)
            difficulty = body.get('difficulty', 3)
            
            questions = asyncio.run(generate_knowledge_point_questions(
                subject=subject,
                knowledge_point=kp_name,
                count=count,
                difficulty=difficulty
            ))
            
            # Save to database
            saved = asyncio.run(save_questions(questions, subject, kp_id))
            
            return res.json(success_response({
                'questions': saved,
                'totalGenerated': len(saved)
            }))
            
        else:
            return res.json(error_response(f"Unknown mode: {mode}"))
            
    except Exception as e:
        import traceback
        return res.json(error_response(str(e), 500, traceback.format_exc()))

