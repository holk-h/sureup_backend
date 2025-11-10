"""
L1: stats-updater
统计更新器 - 响应数据库事件自动更新统计

监听以下事件：
- mistake_records 创建/更新 - 更新知识点统计和掌握状态
- practice_answers 创建 - 更新练习统计和答题统计

注意：错题创建时的基础统计（totalMistakes等）由 mistake_analyzer 更新，
这里只处理知识点统计、掌握状态和练习相关统计，避免重复更新。
"""
import os
import json
from datetime import datetime, timedelta
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from .timezone_utils import (
    get_user_timezone_date, 
    get_user_timezone_datetime,
    get_user_timezone_iso_string,
    is_same_date_in_user_timezone
)

# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_USER_KP = 'user_knowledge_points'
COLLECTION_PROFILES = 'profiles'
COLLECTION_PRACTICE_SESSIONS = 'practice_sessions'
COLLECTION_MISTAKE_RECORDS = 'mistake_records'


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def get_user_profile_by_user_id(databases: Databases, user_id: str):
    """通过 userId 字段获取用户档案"""
    try:
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_PROFILES,
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        documents = result.get('documents', [])
        return documents[0] if documents else None
    except Exception as e:
        print(f"获取用户档案失败: {str(e)}")
        return None


def calculate_continuous_days(databases: Databases, user_id: str, profile: dict) -> int:
    """
    智能计算连续学习天数（基于用户时区）
    
    规则：
    1. 如果今天有学习活动，且昨天也有，则连续天数+1
    2. 如果今天有学习活动，但昨天没有，则重置为1
    3. 如果今天没有学习活动，保持原值
    
    判断依据：lastPracticeDate 或 lastActiveAt
    """
    user_timezone = profile.get('timezone')
    last_practice_date = profile.get('lastPracticeDate')
    current_continuous_days = profile.get('continuousDays', 0)
    
    today = get_user_timezone_date(user_timezone)
    yesterday = today - timedelta(days=1)
    
    # 如果没有练习日期记录，从0开始
    if not last_practice_date:
        return 1
    
    # 解析上次练习日期
    try:
        if isinstance(last_practice_date, str):
            last_practice_utc = datetime.fromisoformat(last_practice_date.replace('Z', '+00:00'))
        else:
            last_practice_utc = last_practice_date
        
        # 转换为用户时区的日期
        current_time = get_user_timezone_datetime(user_timezone)
        
        # 检查上次练习是昨天还是今天（在用户时区）
        if is_same_date_in_user_timezone(last_practice_utc, current_time - timedelta(days=1), user_timezone):
            # 上次练习是昨天，连续天数+1
            return current_continuous_days + 1
        elif is_same_date_in_user_timezone(last_practice_utc, current_time, user_timezone):
            # 上次练习是今天，保持不变
            return current_continuous_days
        else:
            # 上次练习不是昨天或今天，重置为1
            return 1
    except Exception as e:
        print(f"解析练习日期失败: {str(e)}")
        return 1


def on_mistake_created(databases: Databases, mistake_data: dict):
    """
    Handle mistake record creation
    
    只更新知识点统计，用户基础统计由 mistake_analyzer 更新
    
    更新：
    1. 所有关联知识点的 mistakeCount 和 lastMistakeAt
    """
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
            print(f"✓ 更新知识点统计: {kp_id}")
        except Exception as e:
            print(f"❌ 更新知识点统计失败 {kp_id}: {str(e)}")
            continue


def on_practice_answer_created(databases: Databases, answer_data: dict):
    """
    Handle practice answer creation
    
    更新：
    1. 练习会话的统计（completedQuestions, correctQuestions）
    2. 用户档案的答题统计（totalQuestions, totalCorrectAnswers）
    """
    session_id = answer_data.get('sessionId')
    user_id = answer_data.get('userId')
    is_correct = answer_data.get('isCorrect', False)
    
    # 1. Update practice session stats
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
                    'correctQuestions': session.get('correctQuestions', 0) + (1 if is_correct else 0)
                }
            )
            print(f"✓ 更新练习会话统计: {session_id}")
        except Exception as e:
            print(f"❌ 更新练习会话统计失败: {str(e)}")
    
    # 2. Update user profile answer stats
    if user_id:
        try:
            profile = get_user_profile_by_user_id(databases, user_id)
            if profile:
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_PROFILES,
                    document_id=profile['$id'],
                    data={
                        'totalQuestions': profile.get('totalQuestions', 0) + 1,
                        'totalCorrectAnswers': profile.get('totalCorrectAnswers', 0) + (1 if is_correct else 0),
                        'statsUpdatedAt': datetime.utcnow().isoformat() + 'Z'
                    }
                )
                print(f"✓ 更新用户答题统计: {user_id}")
        except Exception as e:
            print(f"❌ 更新用户答题统计失败: {str(e)}")


def on_practice_session_completed(databases: Databases, session_data: dict):
    """
    Handle practice session completion
    
    当 session status 变为 'completed' 时更新：
    1. 用户档案的练习统计
    2. 连续学习天数
    """
    user_id = session_data.get('userId')
    if not user_id:
        return
    
    try:
        profile = get_user_profile_by_user_id(databases, user_id)
        if not profile:
            print(f"❌ 未找到用户档案: {user_id}")
            return
        
        user_timezone = profile.get('timezone')
        current_time = get_user_timezone_datetime(user_timezone)
        today = get_user_timezone_date(user_timezone)
        
        # 准备更新数据
        update_data = {}
        
        # 1. 检查是否需要重置每日数据（基于用户时区）
        last_reset_date = profile.get('lastResetDate')
        need_reset = False
        
        if last_reset_date:
            try:
                last_reset_utc = datetime.fromisoformat(last_reset_date.replace('Z', '+00:00'))
                if not is_same_date_in_user_timezone(last_reset_utc, current_time, user_timezone):
                    need_reset = True
            except:
                need_reset = True
        else:
            need_reset = True
        
        if need_reset:
            update_data['todayPracticeSessions'] = 0
            update_data['lastResetDate'] = get_user_timezone_iso_string(user_timezone)
            print(f"✓ 重置每日练习统计")
        
        # 2. 递增练习次数
        update_data['todayPracticeSessions'] = update_data.get('todayPracticeSessions', profile.get('todayPracticeSessions', 0)) + 1
        update_data['weekPracticeSessions'] = profile.get('weekPracticeSessions', 0) + 1
        update_data['totalPracticeSessions'] = profile.get('totalPracticeSessions', 0) + 1
        update_data['completedSessions'] = profile.get('completedSessions', 0) + 1
        
        # 3. 更新最后练习日期（基于用户时区）
        update_data['lastPracticeDate'] = get_user_timezone_iso_string(user_timezone)
        
        # 4. 计算连续学习天数
        continuous_days = calculate_continuous_days(databases, user_id, profile)
        update_data['continuousDays'] = continuous_days
        
        # 5. 更新活跃时间和统计时间（基于用户时区）
        update_data['lastActiveAt'] = get_user_timezone_iso_string(user_timezone)
        update_data['statsUpdatedAt'] = get_user_timezone_iso_string(user_timezone)
        
        # 6. 更新活跃天数（如果今天首次活动，基于用户时区）
        last_active_at = profile.get('lastActiveAt')
        if last_active_at:
            try:
                last_active_utc = datetime.fromisoformat(last_active_at.replace('Z', '+00:00'))
                if not is_same_date_in_user_timezone(last_active_utc, current_time, user_timezone):
                    update_data['activeDays'] = profile.get('activeDays', 0) + 1
            except:
                update_data['activeDays'] = profile.get('activeDays', 0) + 1
        else:
            update_data['activeDays'] = profile.get('activeDays', 0) + 1
        
        # 执行更新
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_PROFILES,
            document_id=profile['$id'],
            data=update_data
        )
        
        print(f"✓ 更新用户练习统计: {user_id}")
        print(f"   - 今日练习: {update_data['todayPracticeSessions']}")
        print(f"   - 本周练习: {update_data['weekPracticeSessions']}")
        print(f"   - 总练习次数: {update_data['totalPracticeSessions']}")
        print(f"   - 连续学习: {update_data['continuousDays']}天")
        if 'activeDays' in update_data:
            print(f"   - 活跃天数: {update_data['activeDays']}")
        
    except Exception as e:
        print(f"❌ 更新练习统计失败: {str(e)}")
        import traceback
        traceback.print_exc()


def on_mistake_mastery_updated(databases: Databases, mistake_data: dict):
    """
    Handle mistake mastery status update
    
    当错题状态变为 'mastered' 时：
    1. 更新所有关联知识点的 masteredCount
    2. 更新用户档案的 masteredMistakes
    """
    # 只处理变为 mastered 的情况
    if mistake_data.get('masteryStatus') != 'mastered':
        return
    
    kp_ids = mistake_data.get('knowledgePointIds', [])
    current_time = datetime.utcnow().isoformat() + 'Z'
    
    # 1. Update knowledge points mastered count
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
            print(f"✓ 更新知识点掌握统计: {kp_id}")
        except Exception as e:
            print(f"❌ 更新知识点掌握统计失败 {kp_id}: {str(e)}")
            continue
    
    # 2. Update user profile masteredMistakes
    user_id = mistake_data.get('userId')
    if user_id:
        try:
            profile = get_user_profile_by_user_id(databases, user_id)
            if profile:
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_PROFILES,
                    document_id=profile['$id'],
                    data={
                        'masteredMistakes': profile.get('masteredMistakes', 0) + 1,
                        'lastActiveAt': current_time,
                        'statsUpdatedAt': current_time
                    }
                )
                print(f"✓ 更新用户掌握统计: {user_id}")
        except Exception as e:
            print(f"❌ 更新用户掌握统计失败: {str(e)}")


def main(context):
    """
    Main entry point for Appwrite Function (Database Event Trigger)
    
    监听的事件：
    - databases.*.collections.mistake_records.documents.*.create
    - databases.*.collections.mistake_records.documents.*.update
    - databases.*.collections.practice_answers.documents.*.create
    
    职责分工：
    - mistake_analyzer: 更新错题基础统计（totalMistakes, todayMistakes, weekMistakes, weeklyMistakesData, activeDays）
    - stats-updater (本函数): 更新知识点统计、练习统计、掌握统计、连续天数
    """
    try:
        req = context.req
        res = context.res
        
        # Initialize databases
        databases = get_databases()
        
        # Parse event data
        event = req.headers.get('x-appwrite-event', '')
        
        # 解析 payload
        try:
            if isinstance(req.body, str):
                payload = json.loads(req.body) if req.body else {}
            else:
                payload = req.body if hasattr(req, 'body') else {}
        except json.JSONDecodeError:
            payload = {}
        
        context.log(f"收到事件: {event}")
        
        # Handle different events
        if 'mistake_records' in event:
            if 'create' in event:
                context.log("处理错题创建事件 - 更新知识点统计")
                on_mistake_created(databases, payload)
            elif 'update' in event:
                # 检查是否是掌握状态更新
                if payload.get('masteryStatus') == 'mastered':
                    context.log("处理错题掌握事件")
                    on_mistake_mastery_updated(databases, payload)
                else:
                    context.log("跳过：非掌握状态更新")
        
        elif 'practice_answers' in event and 'create' in event:
            context.log("处理答题记录创建事件")
            on_practice_answer_created(databases, payload)
        
        elif 'practice_sessions' in event and 'update' in event:
            # 检查是否是 session 完成
            if payload.get('status') == 'completed':
                context.log("处理练习会话完成事件")
                on_practice_session_completed(databases, payload)
            else:
                context.log("跳过：非完成状态")
        
        else:
            context.log(f"未处理的事件类型: {event}")
        
        return res.json({
            'success': True,
            'message': '统计更新成功',
            'event': event
        })
        
    except Exception as e:
        context.error(f"统计更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json({
            'success': False,
            'message': f'统计更新失败: {str(e)}',
            'error': str(e)
        }, 500)
