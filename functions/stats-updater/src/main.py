"""
L1: stats-updater
统计更新器 - 响应数据库事件自动更新统计
"""
import sys
sys.path.append('../shared')

from appwrite_client import get_databases
from constants import DATABASE_ID, COLLECTION_USER_KNOWLEDGE_POINTS, COLLECTION_PROFILES
from utils import success_response, error_response


async def on_mistake_created(mistake_data: dict):
    """Handle mistake record creation"""
    databases = get_databases()
    
    # Update knowledge point stats
    kp_id = mistake_data.get('userKnowledgePointId')
    if kp_id:
        kp = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
            document_id=kp_id
        )
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
            document_id=kp_id,
            data={'mistakeCount': kp.get('mistakeCount', 0) + 1}
        )
    
    # Update user profile stats
    user_id = mistake_data.get('userId')
    if user_id:
        try:
            profile = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_PROFILES,
                document_id=user_id
            )
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_PROFILES,
                document_id=user_id,
                data={'totalMistakes': profile.get('totalMistakes', 0) + 1}
            )
        except:
            pass  # Profile might not exist yet


async def on_practice_answer_created(answer_data: dict):
    """Handle practice answer creation"""
    databases = get_databases()
    
    # Update practice session stats
    session_id = answer_data.get('sessionId')
    if session_id:
        try:
            from constants import COLLECTION_PRACTICE_SESSIONS
            session = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_PRACTICE_SESSIONS,
                document_id=session_id
            )
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_PRACTICE_SESSIONS,
                document_id=session_id,
                data={
                    'completedQuestions': session.get('completedQuestions', 0) + 1,
                    'correctQuestions': session.get('correctQuestions', 0) + (1 if answer_data.get('isCorrect') else 0)
                }
            )
        except:
            pass


async def on_mistake_mastery_updated(mistake_data: dict):
    """Handle mistake mastery status update"""
    databases = get_databases()
    
    # If mastered, update knowledge point
    if mistake_data.get('masteryStatus') == 'mastered':
        kp_id = mistake_data.get('userKnowledgePointId')
        if kp_id:
            kp = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
                document_id=kp_id
            )
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_USER_KNOWLEDGE_POINTS,
                document_id=kp_id,
                data={'masteredCount': kp.get('masteredCount', 0) + 1}
            )


def main(context):
    """Main entry point for Appwrite Function (Database Event Trigger)"""
    try:
        req = context.req
        res = context.res
        
        # Parse event data
        event = req.headers.get('x-appwrite-event', '')
        payload = req.body if hasattr(req, 'body') else {}
        
        if 'mistake_records' in event:
            if 'create' in event:
                on_mistake_created(payload)
            elif 'update' in event:
                on_mistake_mastery_updated(payload)
                
        elif 'practice_answers' in event and 'create' in event:
            on_practice_answer_created(payload)
        
        return res.json(success_response(None, "Stats updated"))
        
    except Exception as e:
        return res.json(error_response(str(e), 500))

