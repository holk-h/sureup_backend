"""
L1: knowledge-point-manager
知识点管理 - 创建、查找、更新
"""
import sys
sys.path.append('../shared')

from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_USER_KNOWLEDGE_POINTS, COLLECTION_KNOWLEDGE_POINTS_LIBRARY
from models import UserKnowledgePoint
from utils import success_response, error_response, parse_request_body
from appwrite.id import ID
from appwrite.query import Query


async def find_or_create_knowledge_point(
    user_id: str,
    subject: str,
    name: str,
    parent_id: str = None,
    level: int = 1
) -> dict:
    """Find existing or create new user knowledge point"""
    databases = get_databases()
    
    # Try to find existing
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        queries=[
            Query.equal('userId', user_id),
            Query.equal('subject', subject),
            Query.equal('name', name),
            Query.limit(1)
        ]
    )
    
    if docs['total'] > 0:
        return docs['documents'][0]
    
    # Create new
    kp = UserKnowledgePoint(
        user_id=user_id,
        subject=subject,
        name=name,
        parent_id=parent_id,
        level=level,
        created_from='ai'
    )
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        document_id=ID.unique(),
        data=kp.to_dict()
    )
    return doc


async def update_knowledge_point_stats(
    kp_id: str,
    mistake_delta: int = 0,
    mastered_delta: int = 0
) -> dict:
    """Update knowledge point statistics"""
    databases = get_databases()
    
    # Get current stats
    doc = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        document_id=kp_id
    )
    
    # Update
    updated = databases.update_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        document_id=kp_id,
        data={
            'mistakeCount': doc.get('mistakeCount', 0) + mistake_delta,
            'masteredCount': doc.get('masteredCount', 0) + mastered_delta
        }
    )
    return updated


async def get_user_knowledge_points(user_id: str, subject: str = None) -> list:
    """Get user's knowledge points"""
    databases = get_databases()
    
    queries = [Query.equal('userId', user_id)]
    if subject:
        queries.append(Query.equal('subject', subject))
    
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
        queries=queries
    )
    return docs['documents']


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        action = body.get('action', 'findOrCreate')
        
        if action == 'findOrCreate':
            result = find_or_create_knowledge_point(
                user_id=body['userId'],
                subject=body['subject'],
                name=body['name'],
                parent_id=body.get('parentId'),
                level=body.get('level', 1)
            )
            return res.json(success_response(result))
            
        elif action == 'updateStats':
            result = update_knowledge_point_stats(
                kp_id=body['knowledgePointId'],
                mistake_delta=body.get('mistakeDelta', 0),
                mastered_delta=body.get('masteredDelta', 0)
            )
            return res.json(success_response(result, "Stats updated"))
            
        elif action == 'list':
            result = get_user_knowledge_points(
                user_id=body['userId'],
                subject=body.get('subject')
            )
            return res.json(success_response(result))
            
        else:
            return res.json(error_response(f"Unknown action: {action}"))
            
    except Exception as e:
        return res.json(error_response(str(e), 500))

