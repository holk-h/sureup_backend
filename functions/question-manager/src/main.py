"""
L1: question-manager
题目管理 - CRUD操作
"""
import os
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query
from utils import success_response, error_response, parse_request_body

# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_QUESTIONS = 'questions'


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def create_question(data: dict) -> dict:
    """Create a new question"""
    databases = get_databases()
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        document_id=ID.unique(),
        data=data
    )
    return doc


def get_question(question_id: str) -> dict:
    """Get question by ID"""
    databases = get_databases()
    
    doc = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        document_id=question_id
    )
    return doc


def search_similar_questions(content: str, subject: str, limit: int = 5) -> list:
    """Search for similar questions"""
    databases = get_databases()
    
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        queries=[
            Query.equal('subject', subject),
            Query.search('content', content),
            Query.limit(limit)
        ]
    )
    return docs['documents']


def update_question_quality(question_id: str, score: float) -> dict:
    """Update question quality score"""
    databases = get_databases()
    
    doc = databases.update_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        document_id=question_id,
        data={'qualityScore': score}
    )
    return doc


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        action = body.get('action', 'create')
        
        if action == 'create':
            result = create_question(body.get('data', {}))
            return res.json(success_response(result, "Question created"))
            
        elif action == 'get':
            question_id = body.get('questionId')
            if not question_id:
                return res.json(error_response("questionId is required"))
            result = get_question(question_id)
            return res.json(success_response(result))
            
        elif action == 'search':
            content = body.get('content', '')
            subject = body.get('subject', '')
            result = search_similar_questions(content, subject)
            return res.json(success_response(result))
            
        elif action == 'updateQuality':
            question_id = body.get('questionId')
            score = body.get('score', 0)
            result = update_question_quality(question_id, score)
            return res.json(success_response(result, "Quality score updated"))
            
        else:
            return res.json(error_response(f"Unknown action: {action}"))
            
    except Exception as e:
        return res.json(error_response(str(e), 500))

