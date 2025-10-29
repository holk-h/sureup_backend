"""
L2: ai-knowledge-analyzer
AI知识点分析 - 分析题目知识点、类型、难度
"""
import sys
sys.path.append('../shared')

import json
from ai_client import chat_completion
from appwrite_client import get_databases
from constants import DATABASE_ID
from utils import success_response, error_response, parse_request_body
import asyncio


ANALYZE_PROMPT = """你是一个教育专家，擅长分析K12题目。

请分析以下题目，返回JSON格式：

题目：
{question_text}

学科：{subject}（如果未指定，请推断）

返回格式：
{{
  "subject": "学科（math/physics/chemistry等）",
  "knowledgePoint": {{
    "name": "知识点名称",
    "level": 1-3,
    "parentName": "父级知识点（可选）",
    "path": "知识点路径，用 > 分隔"
  }},
  "questionType": "choice/fill_blank/short_answer/calculation/proof",
  "difficulty": 1-5,
  "concepts": ["相关概念1", "相关概念2"]
}}

只返回JSON，不要其他内容。"""


async def analyze_question(question_text: str, subject: str = None) -> dict:
    """Analyze question using AI"""
    prompt = ANALYZE_PROMPT.format(
        question_text=question_text,
        subject=subject or "未指定"
    )
    
    messages = [
        {"role": "system", "content": "You are an expert educator analyzing K12 questions."},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat_completion(messages, temperature=0.3)
    
    # Parse JSON response
    try:
        # Try to extract JSON from response
        result = json.loads(response)
        return result
    except:
        # If direct parse fails, try to find JSON in text
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("Failed to parse AI response")


async def create_knowledge_point_if_needed(user_id: str, subject: str, kp_data: dict) -> str:
    """Create knowledge point if it doesn't exist"""
    from appwrite_client import get_client
    
    # Call knowledge-point-manager function
    client = get_client()
    functions = client.functions
    
    # This is a simplified version - in production, use proper function execution
    # For now, we'll just create it directly
    databases = get_databases()
    from constants import COLLECTION_USER_KNOWLEDGE_POINTS
    from appwrite.id import ID
    from appwrite.query import Query
    
    name = kp_data['name']
    
    # Check if exists
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        queries=[
            Query.equal('userId', user_id),
            Query.equal('name', name),
            Query.limit(1)
        ]
    )
    
    if docs['total'] > 0:
        return docs['documents'][0]['$id']
    
    # Create new
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        document_id=ID.unique(),
        data={
            'userId': user_id,
            'subject': subject,
            'name': name,
            'level': kp_data.get('level', 1),
            'mistakeCount': 0,
            'masteredCount': 0,
            'createdFrom': 'ai'
        }
    )
    
    return doc['$id']


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        
        question_text = body.get('questionText')
        if not question_text:
            return res.json(error_response("questionText is required"))
        
        subject = body.get('subject')
        user_id = body.get('userId')
        
        # Analyze question
        analysis = asyncio.run(analyze_question(question_text, subject))
        
        # Create knowledge point if userId provided
        if user_id and analysis.get('knowledgePoint'):
            kp_id = asyncio.run(create_knowledge_point_if_needed(
                user_id=user_id,
                subject=analysis['subject'],
                kp_data=analysis['knowledgePoint']
            ))
            analysis['knowledgePointId'] = kp_id
        
        return res.json(success_response(analysis, "Analysis complete"))
        
    except Exception as e:
        return res.json(error_response(str(e), 500))

