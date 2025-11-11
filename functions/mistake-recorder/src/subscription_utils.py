"""
订阅权限检查工具
"""
from datetime import datetime, timezone
from appwrite.services.databases import Databases


def check_daily_mistake_limit(databases: Databases, user_id: str, database_id: str = 'main'):
    """
    检查用户每日错题录入限制
    
    免费用户：每天最多 3 个错题
    会员用户：无限制
    
    返回: (是否允许, 错误消息, 用户档案)
    """
    try:
        # 获取用户档案
        from appwrite.query import Query
        profiles = databases.list_documents(
            database_id=database_id,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if not profiles['documents']:
            return False, "用户档案不存在", None
        
        profile = profiles['documents'][0]
        
        # 检查订阅状态
        subscription_status = profile.get('subscriptionStatus', 'free')
        
        # 会员用户无限制
        if subscription_status == 'active':
            # 检查是否过期
            expiry_date = profile.get('subscriptionExpiryDate')
            if expiry_date:
                expiry_datetime = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                if expiry_datetime > datetime.now(timezone.utc):
                    return True, None, profile
        
        # 免费用户：检查每日限制
        today = datetime.now(timezone.utc).date()
        reset_date = profile.get('dailyLimitsResetDate')
        today_mistakes = profile.get('todayMistakeRecords', 0)
        
        # 检查是否需要重置计数
        if reset_date:
            reset_datetime = datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
            reset_date_only = reset_datetime.date()
            
            if reset_date_only < today:
                # 需要重置
                today_mistakes = 0
                # 更新数据库
                databases.update_document(
                    database_id=database_id,
                    collection_id='profiles',
                    document_id=profile['$id'],
                    data={
                        'todayMistakeRecords': 0,
                        'dailyLimitsResetDate': datetime.now(timezone.utc).isoformat()
                    }
                )
                profile['todayMistakeRecords'] = 0
        else:
            # 首次使用，设置重置日期
            databases.update_document(
                database_id=database_id,
                collection_id='profiles',
                document_id=profile['$id'],
                data={
                    'dailyLimitsResetDate': datetime.now(timezone.utc).isoformat()
                }
            )
        
        # 检查是否超限（免费用户每天最多 3 个）
        FREE_USER_DAILY_LIMIT = 3
        if today_mistakes >= FREE_USER_DAILY_LIMIT:
            return False, f"今日免费额度已用完（{FREE_USER_DAILY_LIMIT}/{FREE_USER_DAILY_LIMIT}），升级会员享无限制", profile
        
        return True, None, profile
        
    except Exception as e:
        return False, f"权限检查失败: {str(e)}", None


def increment_daily_mistake_count(databases: Databases, profile_id: str, database_id: str = 'main'):
    """
    增加今日错题计数
    """
    try:
        profile = databases.get_document(
            database_id=database_id,
            collection_id='profiles',
            document_id=profile_id
        )
        
        current_count = profile.get('todayMistakeRecords', 0)
        databases.update_document(
            database_id=database_id,
            collection_id='profiles',
            document_id=profile_id,
            data={
                'todayMistakeRecords': current_count + 1
            }
        )
        return True
    except Exception as e:
        print(f"更新每日计数失败: {str(e)}")
        return False

