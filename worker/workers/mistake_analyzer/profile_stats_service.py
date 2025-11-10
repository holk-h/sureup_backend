"""
用户档案统计更新服务

在记录错题时更新用户的各项统计数据
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from appwrite.services.databases import Databases
from appwrite.query import Query
from .timezone_utils import (
    get_user_timezone_date, 
    get_user_timezone_datetime,
    get_user_timezone_iso_string,
    is_same_date_in_user_timezone
)


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
PROFILES_COLLECTION = 'profiles'


def get_user_profile(databases: Databases, user_id: str) -> Optional[Dict]:
    """获取用户档案"""
    try:
        # 通过 userId 字段查询
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=PROFILES_COLLECTION,
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


def check_and_reset_daily_stats(profile: Dict) -> tuple[bool, Dict]:
    """
    检查是否需要重置每日统计数据（基于用户时区）
    
    Returns:
        (需要重置, 更新数据字典)
    """
    user_timezone = profile.get('timezone')
    last_reset_date = profile.get('lastResetDate')
    today = get_user_timezone_date(user_timezone)
    
    # 如果没有重置日期，或者日期不是今天，则需要重置
    if not last_reset_date:
        return True, {
            'todayMistakes': 0,
            'todayPracticeSessions': 0,
            'lastResetDate': get_user_timezone_iso_string(user_timezone)
        }
    
    # 解析日期
    try:
        if isinstance(last_reset_date, str):
            last_reset_utc = datetime.fromisoformat(last_reset_date.replace('Z', '+00:00'))
        else:
            last_reset_utc = last_reset_date
        
        # 检查是否是同一天（在用户时区）
        current_time = get_user_timezone_datetime(user_timezone)
        if not is_same_date_in_user_timezone(last_reset_utc, current_time, user_timezone):
            return True, {
                'todayMistakes': 0,
                'todayPracticeSessions': 0,
                'lastResetDate': get_user_timezone_iso_string(user_timezone)
            }
    except Exception as e:
        print(f"解析重置日期失败: {str(e)}")
        return True, {
            'todayMistakes': 0,
            'todayPracticeSessions': 0,
            'lastResetDate': get_user_timezone_iso_string(user_timezone)
        }
    
    return False, {}


def check_and_update_active_days(profile: Dict) -> Dict:
    """
    检查并更新活跃天数（基于用户时区）
    
    如果今天是第一次活动，则 activeDays + 1
    
    Returns:
        更新数据字典
    """
    user_timezone = profile.get('timezone')
    last_active_at = profile.get('lastActiveAt')
    
    # 如果没有活跃日期，或者不是今天，则递增 activeDays
    if not last_active_at:
        return {
            'activeDays': profile.get('activeDays', 0) + 1,
            'lastActiveAt': get_user_timezone_iso_string(user_timezone)
        }
    
    # 解析日期
    try:
        if isinstance(last_active_at, str):
            last_active_utc = datetime.fromisoformat(last_active_at.replace('Z', '+00:00'))
        else:
            last_active_utc = last_active_at
        
        # 检查是否是同一天（在用户时区）
        current_time = get_user_timezone_datetime(user_timezone)
        if not is_same_date_in_user_timezone(last_active_utc, current_time, user_timezone):
            return {
                'activeDays': profile.get('activeDays', 0) + 1,
                'lastActiveAt': get_user_timezone_iso_string(user_timezone)
            }
    except Exception as e:
        print(f"解析活跃日期失败: {str(e)}")
        return {
            'activeDays': profile.get('activeDays', 0) + 1,
            'lastActiveAt': get_user_timezone_iso_string(user_timezone)
        }
    
    # 今天已经活跃过了，只更新时间戳
    return {
        'lastActiveAt': get_user_timezone_iso_string(user_timezone)
    }


def update_weekly_mistakes_data(profile: Dict) -> str:
    """
    更新过去一周的错题数据（用于图表显示，基于用户时区）
    
    Returns:
        JSON 字符串格式的周数据
    """
    user_timezone = profile.get('timezone')
    today = get_user_timezone_date(user_timezone)
    
    # 解析现有数据
    weekly_data_str = profile.get('weeklyMistakesData')
    if weekly_data_str:
        try:
            weekly_data = json.loads(weekly_data_str)
        except:
            weekly_data = []
    else:
        weekly_data = []
    
    # 查找今天的记录
    today_str = today.isoformat()
    today_entry = None
    for entry in weekly_data:
        if entry.get('date') == today_str:
            today_entry = entry
            break
    
    # 更新或添加今天的记录
    if today_entry:
        today_entry['count'] = today_entry.get('count', 0) + 1
    else:
        weekly_data.append({
            'date': today_str,
            'count': 1
        })
    
    # 只保留最近7天的数据（基于用户时区）
    seven_days_ago = today - timedelta(days=6)
    weekly_data = [
        entry for entry in weekly_data
        if datetime.fromisoformat(entry['date']).date() >= seven_days_ago
    ]
    
    # 按日期排序
    weekly_data.sort(key=lambda x: x['date'])
    
    return json.dumps(weekly_data, ensure_ascii=False)


def update_profile_stats_on_mistake_created(
    databases: Databases,
    user_id: str
) -> bool:
    """
    在创建错题时更新用户档案统计数据
    
    更新的字段：
    - activeDays: 如果今天首次活动则 +1
    - todayMistakes: +1 (如果需要重置则先重置为0)
    - weekMistakes: +1
    - totalMistakes: +1
    - weeklyMistakesData: 更新JSON数据
    - lastActiveAt: 更新为当前时间
    - lastResetDate: 如果重置则更新
    - statsUpdatedAt: 更新为当前时间
    
    Args:
        databases: Databases 服务实例
        user_id: 用户ID
        
    Returns:
        是否成功更新
    """
    try:
        # 1. 获取用户档案
        profile = get_user_profile(databases, user_id)
        if not profile:
            print(f"未找到用户档案: {user_id}")
            return False
        
        profile_id = profile['$id']
        
        # 2. 准备更新数据
        update_data = {}
        
        # 3. 检查并重置每日统计
        need_reset, reset_data = check_and_reset_daily_stats(profile)
        if need_reset:
            update_data.update(reset_data)
            print(f"✓ 重置每日统计数据")
        
        # 4. 更新活跃天数
        active_days_data = check_and_update_active_days(profile)
        update_data.update(active_days_data)
        
        # 5. 递增今日错题数
        current_today_mistakes = update_data.get('todayMistakes', profile.get('todayMistakes', 0))
        update_data['todayMistakes'] = current_today_mistakes + 1
        
        # 6. 递增本周错题数
        update_data['weekMistakes'] = profile.get('weekMistakes', 0) + 1
        
        # 7. 递增总错题数
        update_data['totalMistakes'] = profile.get('totalMistakes', 0) + 1
        
        # 8. 更新周数据（用于图表）
        weekly_data_json = update_weekly_mistakes_data(profile)
        update_data['weeklyMistakesData'] = weekly_data_json
        
        # 9. 更新统计时间戳（基于用户时区）
        user_timezone = profile.get('timezone')
        update_data['statsUpdatedAt'] = get_user_timezone_iso_string(user_timezone)
        
        # 10. 执行更新
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id=PROFILES_COLLECTION,
            document_id=profile_id,
            data=update_data
        )
        
        print(f"✓ 成功更新用户统计数据: {user_id}")
        print(f"   - 今日错题: {update_data['todayMistakes']}")
        print(f"   - 本周错题: {update_data['weekMistakes']}")
        print(f"   - 总错题数: {update_data['totalMistakes']}")
        if 'activeDays' in update_data:
            print(f"   - 活跃天数: {update_data['activeDays']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 更新用户统计数据失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def check_and_reset_weekly_stats(databases: Databases, user_id: str) -> bool:
    """
    检查并重置每周统计数据（每周一凌晨调用）
    
    重置的字段：
    - weekMistakes
    - weekPracticeSessions
    
    注意：这个函数应该由定时任务调用，而不是在记录错题时调用
    """
    try:
        profile = get_user_profile(databases, user_id)
        if not profile:
            return False
        
        # 检查是否是周一
        today = datetime.utcnow()
        if today.weekday() != 0:  # 0 = 周一
            return False
        
        # 检查上次统计更新时间
        stats_updated_at = profile.get('statsUpdatedAt')
        if stats_updated_at:
            try:
                last_update = datetime.fromisoformat(stats_updated_at.replace('Z', '+00:00'))
                # 如果今天已经重置过了，跳过
                if last_update.date() == today.date():
                    return False
            except:
                pass
        
        # 重置每周统计
        update_data = {
            'weekMistakes': 0,
            'weekPracticeSessions': 0,
            'statsUpdatedAt': datetime.utcnow().isoformat() + 'Z'
        }
        
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id=PROFILES_COLLECTION,
            document_id=profile['$id'],
            data=update_data
        )
        
        print(f"✓ 重置每周统计数据: {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ 重置每周统计数据失败: {str(e)}")
        return False

