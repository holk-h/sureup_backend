"""
L3: daily-task-scheduler
每日任务调度器 - 定时生成每日复习任务
"""
import sys
sys.path.append('../shared')

from datetime import datetime, timedelta
from appwrite_client import get_databases, get_users
from constants import DATABASE_ID, COLLECTION_MISTAKE_RECORDS, COLLECTION_DAILY_TASKS, COLLECTION_PROFILES
from utils import success_response, error_response
from appwrite.query import Query
from appwrite.id import ID
import asyncio


async def analyze_review_needs(user_id: str) -> list:
    """Analyze which mistakes need review"""
    databases = get_databases()
    
    # Get mistakes that need review
    # 1. Not mastered
    # 2. Last reviewed more than 2 days ago OR never reviewed
    
    two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
    
    mistakes = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKE_RECORDS,
        queries=[
            Query.equal('userId', user_id),
            Query.not_equal('masteryStatus', 'mastered'),
            Query.limit(20),
            Query.order_desc('$createdAt')
        ]
    )
    
    # Filter by last review time
    need_review = []
    for mistake in mistakes['documents']:
        last_review = mistake.get('lastReviewAt')
        if not last_review or last_review < two_days_ago:
            need_review.append(mistake)
            if len(need_review) >= 5:  # Max 5 mistakes per day
                break
    
    return need_review


async def generate_daily_task_for_user(user_id: str) -> dict:
    """Generate daily task for a single user"""
    databases = get_databases()
    
    # Check if task already exists for today
    today = datetime.now().date().isoformat()
    existing = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_DAILY_TASKS,
        queries=[
            Query.equal('userId', user_id),
            Query.equal('taskDate', today),
            Query.limit(1)
        ]
    )
    
    if existing['total'] > 0:
        return {'skipped': True, 'reason': 'Task already exists for today'}
    
    # Analyze what needs review
    mistakes = await analyze_review_needs(user_id)
    
    if not mistakes:
        return {'skipped': True, 'reason': 'No mistakes need review'}
    
    # For MVP, we'll use the original questions
    # In production, we'd call ai-question-generator to create variants
    question_ids = [m.get('questionId') for m in mistakes if m.get('questionId')]
    
    if not question_ids:
        return {'skipped': True, 'reason': 'No questions found'}
    
    # Create daily task
    task = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_DAILY_TASKS,
        document_id=ID.unique(),
        data={
            'userId': user_id,
            'taskDate': today,
            'questionIds': question_ids,
            'taskType': 'daily_review',
            'isCompleted': False,
            'mistakeRecordIds': [m['$id'] for m in mistakes]
        }
    )
    
    return {'created': True, 'task': task, 'questionCount': len(question_ids)}


async def get_active_users() -> list:
    """Get list of active users"""
    databases = get_databases()
    
    # Get users who have created mistakes in the last 7 days
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    # For MVP, get all profiles
    profiles = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_PROFILES,
        queries=[
            Query.limit(100)  # Limit for MVP
        ]
    )
    
    return profiles['documents']


def main(context):
    """Main entry point for Appwrite Function (Scheduled)"""
    try:
        res = context.res
        
        # Get active users
        users = asyncio.run(get_active_users())
        
        results = {
            'total_users': len(users),
            'tasks_created': 0,
            'tasks_skipped': 0,
            'errors': []
        }
        
        # Generate tasks for each user
        for user in users:
            try:
                user_id = user.get('userId') or user.get('$id')
                result = asyncio.run(generate_daily_task_for_user(user_id))
                
                if result.get('created'):
                    results['tasks_created'] += 1
                else:
                    results['tasks_skipped'] += 1
                    
            except Exception as e:
                results['errors'].append({
                    'userId': user.get('userId', 'unknown'),
                    'error': str(e)
                })
        
        return res.json(success_response(results, "Daily tasks generation complete"))
        
    except Exception as e:
        import traceback
        return res.json(error_response(str(e), 500, traceback.format_exc()))

