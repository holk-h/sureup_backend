#!/usr/bin/env python3
"""
测试脚本：生成明天的每日任务（测试用）
"""
import os
import sys
from datetime import datetime, date, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from appwrite.client import Client
from appwrite.services.databases import Databases

from workers.daily_task_generator.task_generator import get_active_users, generate_daily_task_for_user

# 模拟明天的日期
TOMORROW_DATE = date.today() + timedelta(days=1)
TOMORROW = TOMORROW_DATE.isoformat()

# Monkey patch: 让系统认为今天是明天
# 注意：由于现在使用了时区工具，需要修改 timezone_utils 模块
import workers.daily_task_generator.timezone_utils as tz_module

# 备份原始函数
original_get_user_timezone_date = tz_module.get_user_timezone_date
original_get_user_timezone_datetime = tz_module.get_user_timezone_datetime

# 修改时区工具函数，使其返回"明天"
def mock_get_user_timezone_date(user_timezone=None):
    return TOMORROW_DATE

def mock_get_user_timezone_datetime(user_timezone=None):
    import pytz
    if not user_timezone:
        user_timezone = 'Asia/Shanghai'
    try:
        tz = pytz.timezone(user_timezone)
        # 返回明天的datetime
        now = datetime.now(tz)
        tomorrow_dt = now + timedelta(days=1)
        return tomorrow_dt
    except:
        tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz)
        tomorrow_dt = now + timedelta(days=1)
        return tomorrow_dt

# 替换时区工具函数
tz_module.get_user_timezone_date = mock_get_user_timezone_date
tz_module.get_user_timezone_datetime = mock_get_user_timezone_datetime


def get_databases() -> Databases:
    """初始化数据库服务"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def main():
    """主函数"""
    print("\n" + "="*60)
    print(f"📅 每日任务生成测试 - 明天 ({TOMORROW})")
    print("="*60 + "\n")
    
    # 初始化数据库服务
    print("🔌 连接数据库...")
    db = get_databases()
    print("✅ 连接成功\n")
    
    # 获取活跃用户
    print("👥 获取活跃用户...")
    active_users = get_active_users(db)
    print(f"✅ 找到 {len(active_users)} 个活跃用户\n")
    
    if not active_users:
        print("⚠️  没有活跃用户")
        return
    
    # 为每个用户生成任务
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for user in active_users:
        user_id = user.get('userId', 'unknown')
        user_name = user.get('name', '未知')
        
        print(f"处理用户: {user_name} ({user_id})")
        
        try:
            result = generate_daily_task_for_user(user, db)
            
            if result['generated']:
                success_count += 1
                print(f"  ✅ 成功生成 {result['total_questions']} 道题")
            else:
                skip_count += 1
                print(f"  ⏭️  跳过: {result['reason']}")
        except Exception as e:
            error_count += 1
            print(f"  ❌ 失败: {str(e)}")
        
        print()
    
    # 输出统计
    print("="*60)
    print("📊 生成统计")
    print("="*60)
    print(f"✅ 成功: {success_count}")
    print(f"⏭️  跳过: {skip_count}")
    print(f"❌ 失败: {error_count}")
    print(f"👥 总计: {len(active_users)}")
    print()


if __name__ == '__main__':
    main()

