"""
L1: mistake-recorder
错题记录器 - 创建和更新错题记录
"""
import sys
sys.path.append('../shared')

from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_MISTAKE_RECORDS
from models import MistakeRecord
from utils import success_response, error_response, parse_request_body
from appwrite.id import ID
from appwrite.query import Query


async def create_mistake_record(
    user_id: str,
    question_id: str,
    knowledge_point_id: str,
    subject: str,
    error_reason: str,
    user_answer: str = None,
    note: str = None,
    image_urls: list = None
) -> dict:
    """Create a new mistake record"""
    databases = get_databases()
    
    record = MistakeRecord(
        user_id=user_id,
        question_id=question_id,
        user_knowledge_point_id=knowledge_point_id,
        subject=subject,
        error_reason=error_reason,
        user_answer=user_answer,
        note=note,
        original_image_urls=image_urls or []
    )
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKE_RECORDS,
        document_id=ID.unique(),
        data=record.to_dict()
    )
    return doc


async def update_mistake_mastery(
    mistake_id: str,
    mastery_status: str = None,
    review_count_delta: int = 0,
    correct_count_delta: int = 0
) -> dict:
    """Update mistake record mastery status"""
    databases = get_databases()
    
    # Get current record
    doc = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKE_RECORDS,
        document_id=mistake_id
    )
    
    # Prepare update data
    update_data = {
        'reviewCount': doc.get('reviewCount', 0) + review_count_delta,
        'correctCount': doc.get('correctCount', 0) + correct_count_delta
    }
    
    if mastery_status:
        update_data['masteryStatus'] = mastery_status
    
    # Update
    updated = databases.update_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKE_RECORDS,
        document_id=mistake_id,
        data=update_data
    )
    return updated


async def get_user_mistakes(
    user_id: str,
    subject: str = None,
    mastery_status: str = None,
    limit: int = 50
) -> list:
    """Get user's mistake records"""
    databases = get_databases()
    
    queries = [
        Query.equal('userId', user_id),
        Query.limit(limit),
        Query.order_desc('$createdAt')
    ]
    
    if subject:
        queries.append(Query.equal('subject', subject))
    if mastery_status:
        queries.append(Query.equal('masteryStatus', mastery_status))
    
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKE_RECORDS,
        queries=queries
    )
    return docs['documents']


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        body = parse_request_body(req)
        action = body.get('action', 'create')
        
        if action == 'create':
            result = create_mistake_record(
                user_id=body['userId'],
                question_id=body['questionId'],
                knowledge_point_id=body['knowledgePointId'],
                subject=body['subject'],
                error_reason=body['errorReason'],
                user_answer=body.get('userAnswer'),
                note=body.get('note'),
                image_urls=body.get('imageUrls')
            )
            return res.json(success_response(result, "Mistake record created"))
            
        elif action == 'updateMastery':
            result = update_mistake_mastery(
                mistake_id=body['mistakeId'],
                mastery_status=body.get('masteryStatus'),
                review_count_delta=body.get('reviewCountDelta', 0),
                correct_count_delta=body.get('correctCountDelta', 0)
            )
            return res.json(success_response(result, "Mastery updated"))
            
        elif action == 'list':
            result = get_user_mistakes(
                user_id=body['userId'],
                subject=body.get('subject'),
                mastery_status=body.get('masteryStatus'),
                limit=body.get('limit', 50)
            )
            return res.json(success_response(result))
            
        else:
            return res.json(error_response(f"Unknown action: {action}"))
            
    except Exception as e:
        return res.json(error_response(str(e), 500))

