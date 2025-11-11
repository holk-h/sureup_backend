"""
订阅状态检查定时任务

功能：
1. 每天凌晨 2 点运行（schedule: "0 2 * * *"）
2. 扫描所有活跃订阅
3. 检查过期状态
4. 更新用户档案的订阅状态

环境变量：
- APPWRITE_ENDPOINT: Appwrite API 端点
- APPWRITE_PROJECT_ID: 项目 ID
- APPWRITE_API_KEY: API Key
- APPWRITE_DATABASE_ID: 数据库 ID
"""

import os
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def check_expired_subscriptions(databases: Databases) -> dict:
    """
    检查并更新过期的订阅
    
    Returns:
        统计信息字典
    """
    now = datetime.now(timezone.utc).isoformat()
    checked_count = 0
    expired_count = 0
    updated_profiles = 0
    
    try:
        # 获取所有活跃订阅
        offset = 0
        limit = 100
        
        while True:
            subscriptions = databases.list_documents(
                database_id=DATABASE_ID,
                collection_id='subscriptions',
                queries=[
                    Query.equal('status', 'active'),
                    Query.limit(limit),
                    Query.offset(offset)
                ]
            )
            
            if not subscriptions['documents']:
                break
            
            for subscription in subscriptions['documents']:
                checked_count += 1
                user_id = subscription['userId']
                expiry_date = subscription['expiryDate']
                
                # 解析过期时间
                expiry_datetime = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                
                # 检查是否过期
                if expiry_datetime <= datetime.now(timezone.utc):
                    # 订阅已过期
                    expired_count += 1
                    
                    # 更新订阅状态为 expired
                    databases.update_document(
                        database_id=DATABASE_ID,
                        collection_id='subscriptions',
                        document_id=subscription['$id'],
                        data={'status': 'expired'}
                    )
                    
                    # 更新用户档案
                    profiles = databases.list_documents(
                        database_id=DATABASE_ID,
                        collection_id='profiles',
                        queries=[
                            Query.equal('userId', user_id),
                            Query.limit(1)
                        ]
                    )
                    
                    if profiles['documents']:
                        profile = profiles['documents'][0]
                        # 检查用户是否还有其他活跃订阅
                        other_active = databases.list_documents(
                            database_id=DATABASE_ID,
                            collection_id='subscriptions',
                            queries=[
                                Query.equal('userId', user_id),
                                Query.equal('status', 'active'),
                                Query.greater_than('expiryDate', now),
                                Query.limit(1)
                            ]
                        )
                        
                        if other_active['total'] == 0:
                            # 没有其他活跃订阅，更新为 free
                            databases.update_document(
                                database_id=DATABASE_ID,
                                collection_id='profiles',
                                document_id=profile['$id'],
                                data={
                                    'subscriptionStatus': 'expired',
                                    'subscriptionExpiryDate': expiry_date
                                }
                            )
                            updated_profiles += 1
                            print(f"用户 {user_id} 订阅已过期")
            
            # 下一页
            offset += limit
            
            # 如果返回的文档少于 limit，说明已经是最后一页
            if len(subscriptions['documents']) < limit:
                break
        
        return {
            'checked_count': checked_count,
            'expired_count': expired_count,
            'updated_profiles': updated_profiles
        }
        
    except Exception as e:
        print(f"检查订阅失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'checked_count': checked_count,
            'expired_count': expired_count,
            'updated_profiles': updated_profiles,
            'error': str(e)
        }


def main(context):
    """
    主函数：定时任务入口
    """
    try:
        context.log("[订阅检查] 开始检查订阅状态")
        
        # 初始化数据库
        databases = get_databases()
        
        # 检查过期订阅
        result = check_expired_subscriptions(databases)
        
        context.log(f"[订阅检查] 完成: 检查 {result['checked_count']} 个订阅, "
                    f"发现 {result['expired_count']} 个过期, "
                    f"更新 {result['updated_profiles']} 个用户档案")
        
        return context.res.json({
            'success': True,
            'message': '订阅状态检查完成',
            'stats': result
        })
        
    except Exception as e:
        context.error(f"[订阅检查] 失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return context.res.json({
            'success': False,
            'error': str(e)
        })

