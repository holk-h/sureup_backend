"""
时区处理工具函数
"""
from datetime import datetime, timezone
from typing import Optional
import pytz


def get_user_timezone_datetime(user_timezone: Optional[str] = None) -> datetime:
    """
    获取用户时区的当前时间
    
    Args:
        user_timezone: 用户时区字符串，如 'Asia/Shanghai'
        
    Returns:
        用户时区的当前时间
    """
    if not user_timezone:
        # 如果没有设置时区，默认使用 Asia/Shanghai (UTC+8)
        user_timezone = 'Asia/Shanghai'
    
    try:
        tz = pytz.timezone(user_timezone)
        return datetime.now(tz)
    except Exception as e:
        print(f"⚠️ 无效的时区 '{user_timezone}': {e}")
        # 回退到 Asia/Shanghai
        tz = pytz.timezone('Asia/Shanghai')
        return datetime.now(tz)


def get_user_timezone_date(user_timezone: Optional[str] = None) -> datetime:
    """
    获取用户时区的当前日期（只包含年月日）
    
    Args:
        user_timezone: 用户时区字符串，如 'Asia/Shanghai'
        
    Returns:
        用户时区的当前日期
    """
    user_datetime = get_user_timezone_datetime(user_timezone)
    return user_datetime.date()


def convert_utc_to_user_timezone(utc_datetime: datetime, user_timezone: Optional[str] = None) -> datetime:
    """
    将 UTC 时间转换为用户时区时间
    
    Args:
        utc_datetime: UTC 时间
        user_timezone: 用户时区字符串
        
    Returns:
        用户时区时间
    """
    if not user_timezone:
        user_timezone = 'Asia/Shanghai'
    
    try:
        # 确保 UTC 时间有时区信息
        if utc_datetime.tzinfo is None:
            utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)
        
        tz = pytz.timezone(user_timezone)
        return utc_datetime.astimezone(tz)
    except Exception as e:
        print(f"⚠️ 时区转换失败: {e}")
        return utc_datetime


def get_user_timezone_iso_string(user_timezone: Optional[str] = None) -> str:
    """
    获取用户时区的当前时间的 ISO 字符串（用于存储到数据库）
    
    Args:
        user_timezone: 用户时区字符串
        
    Returns:
        ISO 格式的时间字符串（带 Z 后缀表示已转换为 UTC）
    """
    user_datetime = get_user_timezone_datetime(user_timezone)
    # 转换为 UTC 时间存储
    utc_datetime = user_datetime.astimezone(timezone.utc)
    return utc_datetime.isoformat().replace('+00:00', 'Z')


def is_same_date_in_user_timezone(date1: datetime, date2: datetime, user_timezone: Optional[str] = None) -> bool:
    """
    判断两个时间在用户时区是否是同一天
    
    Args:
        date1: 第一个时间
        date2: 第二个时间
        user_timezone: 用户时区字符串
        
    Returns:
        是否是同一天
    """
    if not user_timezone:
        user_timezone = 'Asia/Shanghai'
    
    try:
        tz = pytz.timezone(user_timezone)
        
        # 转换为用户时区
        if date1.tzinfo is None:
            date1 = date1.replace(tzinfo=timezone.utc)
        if date2.tzinfo is None:
            date2 = date2.replace(tzinfo=timezone.utc)
            
        user_date1 = date1.astimezone(tz).date()
        user_date2 = date2.astimezone(tz).date()
        
        return user_date1 == user_date2
    except Exception as e:
        print(f"⚠️ 日期比较失败: {e}")
        return False
