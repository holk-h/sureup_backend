"""
L1: stats-updater
统计更新器 - 响应数据库事件自动更新统计

监听以下事件：
- mistake_records 创建/更新 - 更新知识点统计和用户统计
- practice_answers 创建 - 更新练习会话统计
"""
import os
from datetime import datetime
from appwrite.client import Client
from appwrite.services.databases import Databases

# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_USER_KP = 'user_knowledge_points'
COLLECTION_PROFILES = 'profiles'
COLLECTION_PRACTICE_SESSIONS = 'practice_sessions'


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def on_mistake_created(mistake_data: dict):
    """
    Handle mistake record creation
    
    更新：
    1. 所有关联知识点的 mistakeCount
    2. 用户档案的 totalMistakes
    """
    databases = get_databases()
    
    # Update knowledge points stats (支持多个知识点)
    kp_ids = mistake_data.get('knowledgePointIds', [])
    current_time = datetime.utcnow().isoformat() + 'Z'
    
    for kp_id in kp_ids:
        try:
            kp = databases.get_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_USER_KP,
                document_id=kp_id
            )
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_USER_KP,
                document_id=kp_id,
                data={
                    'mistakeCount': kp.get('mistakeCount', 0) + 1,
                    'lastMistakeAt': current_time
                }
            )
        except Exception as e:
            print(f"更新知识点统计失败 {kp_id}: {str(e)}")
            continue
    
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
                data={
                    'totalMistakes': profile.get('totalMistakes', 0) + 1,
                    'lastActiveAt': current_time
                }
            )
        except Exception as e:
            print(f"更新用户档案失败: {str(e)}")
            pass  # Profile might not exist yet


def on_practice_answer_created(answer_data: dict):
    """
    Handle practice answer creation
    
    更新练习会话的统计：
    - completedQuestions: 完成的题目数
    - correctQuestions: 正确的题目数
    """
    databases = get_databases()
    
    # Update practice session stats
    session_id = answer_data.get('sessionId')
    if session_id:
        try:
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
        except Exception as e:
            print(f"更新练习会话统计失败: {str(e)}")
            pass


def on_mistake_mastery_updated(mistake_data: dict):
    """
    Handle mistake mastery status update
    
    当错题状态变为 'mastered' 时：
    1. 更新所有关联知识点的 masteredCount
    2. 更新用户档案的 masteredMistakes
    """
    databases = get_databases()
    
    # If mastered, update knowledge points (支持多个知识点)
    if mistake_data.get('masteryStatus') == 'mastered':
        kp_ids = mistake_data.get('knowledgePointIds', [])
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        for kp_id in kp_ids:
            try:
                kp = databases.get_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_USER_KP,
                    document_id=kp_id
                )
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_USER_KP,
                    document_id=kp_id,
                    data={'masteredCount': kp.get('masteredCount', 0) + 1}
                )
            except Exception as e:
                print(f"更新知识点掌握统计失败 {kp_id}: {str(e)}")
                continue
        
        # Update user profile masteredMistakes
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
                    data={
                        'masteredMistakes': profile.get('masteredMistakes', 0) + 1,
                        'lastActiveAt': current_time
                    }
                )
            except Exception as e:
                print(f"更新用户档案掌握统计失败: {str(e)}")
                pass


def main(context):
    """
    Main entry point for Appwrite Function (Database Event Trigger)
    
    监听的事件：
    - databases.*.collections.mistake_records.documents.*.create
    - databases.*.collections.mistake_records.documents.*.update
    - databases.*.collections.practice_answers.documents.*.create
    """
    try:
        req = context.req
        res = context.res
        
        # Parse event data
        event = req.headers.get('x-appwrite-event', '')
        payload = req.body if hasattr(req, 'body') else {}
        
        context.log(f"收到事件: {event}")
        
        # Handle different events
        if 'mistake_records' in event:
            if 'create' in event:
                context.log("处理错题创建事件")
                on_mistake_created(payload)
            elif 'update' in event:
                context.log("处理错题更新事件")
                on_mistake_mastery_updated(payload)
                
        elif 'practice_answers' in event and 'create' in event:
            context.log("处理答题记录创建事件")
            on_practice_answer_created(payload)
        else:
            context.log(f"未处理的事件类型: {event}")
        
        return res.json({
            'success': True,
            'message': '统计更新成功',
            'event': event
        })
        
    except Exception as e:
        context.log(f"统计更新失败: {str(e)}")
        return res.json({
            'success': False,
            'message': f'统计更新失败: {str(e)}',
            'error': str(e)
        }, 500)

