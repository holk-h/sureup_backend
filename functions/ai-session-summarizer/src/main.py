"""
L2: ai-session-summarizer
AI练习总结 - 分析练习会话并生成总结
"""
import sys
sys.path.append('../shared')

import json
from ai_client import chat_completion
from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_PRACTICE_SESSIONS, COLLECTION_PRACTICE_ANSWERS
from utils import success_response, error_response, parse_request_body
from appwrite.query import Query
import asyncio


SUMMARY_PROMPT = """你是一个鼓励型的学习教练，擅长总结学生的练习表现。

练习数据：
- 总题数：{total}
- 正确：{correct}
- 错误：{wrong}
- 正确率：{accuracy}%
- 知识点：{knowledge_point}

题目详情：
{questions_detail}

请生成：
1. overall: 总体总结（1-2句话）
2. strengths: 优点列表（2-3个）
3. weaknesses: 需要改进的地方（1-2个）
4. progress: 与之前的进步对比（如果有）
5. encouragement: 鼓励的话（1-2句话，要真诚且具体）
6. suggestions: 学习建议（2-3条）

返回JSON格式：
{{
  "overall": "...",
  "strengths": ["...", "..."],
  "weaknesses": ["..."],
  "progress": "...",
  "encouragement": "...",
  "suggestions": ["...", "..."]
}}

只返回JSON，不要其他内容。要求语气温和、鼓励、具体。"""


async def generate_session_summary(session_data: dict, answers: list) -> dict:
    """Generate AI summary for practice session"""
    total = len(answers)
    correct = sum(1 for a in answers if a.get('isCorrect'))
    wrong = total - correct
    accuracy = round(correct / total * 100) if total > 0 else 0
    
    # Build questions detail
    questions_detail = "\n".join([
        f"题{i+1}: {'✓正确' if a.get('isCorrect') else '✗错误'} (用时{a.get('timeSpent', 0)}秒)"
        for i, a in enumerate(answers)
    ])
    
    prompt = SUMMARY_PROMPT.format(
        total=total,
        correct=correct,
        wrong=wrong,
        accuracy=accuracy,
        knowledge_point=session_data.get('title', '练习'),
        questions_detail=questions_detail
    )
    
    messages = [
        {"role": "system", "content": "You are an encouraging learning coach."},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat_completion(messages, temperature=0.7)
    
    # Parse JSON
    import re
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError("Failed to parse AI response")


async def update_mistake_mastery(answers: list):
    """Update mistake records based on answers"""
    databases = get_databases()
    from constants import COLLECTION_MISTAKE_RECORDS
    
    for answer in answers:
        mistake_id = answer.get('mistakeRecordId')
        if not mistake_id:
            continue
        
        try:
            # Get current record
            mistake = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_MISTAKE_RECORDS,
                document_id=mistake_id
            )
            
            # Update stats
            review_count = mistake.get('reviewCount', 0) + 1
            correct_count = mistake.get('correctCount', 0) + (1 if answer.get('isCorrect') else 0)
            
            # Determine mastery status
            mastery_status = mistake.get('masteryStatus', 'notStarted')
            if review_count >= 3 and correct_count >= 2:
                mastery_status = 'mastered'
            elif review_count > 0:
                mastery_status = 'practicing'
            
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_MISTAKE_RECORDS,
                document_id=mistake_id,
                data={
                    'reviewCount': review_count,
                    'correctCount': correct_count,
                    'masteryStatus': mastery_status
                }
            )
        except Exception as e:
            print(f"Error updating mistake {mistake_id}: {e}")
            continue


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        session_id = body.get('sessionId')
        
        if not session_id:
            return res.json(error_response("sessionId is required"))
        
        databases = get_databases()
        
        # Get session
        session = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_PRACTICE_SESSIONS,
            document_id=session_id
        )
        
        # Get answers
        answers_docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_PRACTICE_ANSWERS,
            queries=[
                Query.equal('sessionId', session_id),
                Query.order_asc('$createdAt')
            ]
        )
        answers = answers_docs['documents']
        
        if not answers:
            return res.json(error_response("No answers found for this session"))
        
        # Generate AI summary
        summary = asyncio.run(generate_session_summary(session, answers))
        
        # Update session with AI summary
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_PRACTICE_SESSIONS,
            document_id=session_id,
            data={
                'aiSummary': json.dumps(summary),
                'status': 'completed'
            }
        )
        
        # Update mistake mastery status
        asyncio.run(update_mistake_mastery(answers))
        
        return res.json(success_response({
            'summary': summary,
            'updatedMistakes': [a.get('mistakeRecordId') for a in answers if a.get('mistakeRecordId')]
        }))
        
    except Exception as e:
        import traceback
        return res.json(error_response(str(e), 500, traceback.format_exc()))

