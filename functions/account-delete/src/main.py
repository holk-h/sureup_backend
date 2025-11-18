"""
账户删除 Function

功能：
1. 删除用户的所有数据（档案、错题记录、知识点、订阅、练习会话等）
2. 删除 Appwrite 账户

环境变量：
- APPWRITE_ENDPOINT: Appwrite API 端点
- APPWRITE_PROJECT_ID: 项目 ID
- APPWRITE_API_KEY: API Key
- APPWRITE_DATABASE_ID: 数据库 ID
"""

import os
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.users import Users
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def get_users() -> Users:
    """Initialize Users service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Users(client)


def delete_user_documents(databases: Databases, user_id: str, collection_id: str, context) -> int:
    """
    删除用户在某集合中的所有文档
    
    Returns:
        删除的文档数量
    """
    deleted_count = 0
    offset = 0
    limit = 100
    
    try:
        while True:
            # 查询该用户的所有文档
            documents = databases.list_documents(
                database_id=DATABASE_ID,
                collection_id=collection_id,
                queries=[
                    Query.equal('userId', user_id),
                    Query.limit(limit),
                    Query.offset(offset)
                ]
            )
            
            if not documents.get('documents'):
                break
            
            # 批量删除文档
            for doc in documents['documents']:
                try:
                    databases.delete_document(
                        database_id=DATABASE_ID,
                        collection_id=collection_id,
                        document_id=doc['$id']
                    )
                    deleted_count += 1
                except Exception as e:
                    context.log(f"⚠️ 删除文档失败 {collection_id}/{doc['$id']}: {str(e)}")
            
            # 如果返回的文档少于 limit，说明已经是最后一页
            if len(documents['documents']) < limit:
                break
            
            offset += limit
        
        return deleted_count
    except Exception as e:
        context.log(f"⚠️ 删除集合 {collection_id} 的文档时出错: {str(e)}")
        return deleted_count


def delete_user_profile(databases: Databases, user_id: str, context) -> bool:
    """删除用户档案"""
    try:
        profiles = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if profiles['total'] > 0:
            databases.delete_document(
                database_id=DATABASE_ID,
                collection_id='profiles',
                document_id=profiles['documents'][0]['$id']
            )
            context.log(f"✅ 已删除用户档案")
            return True
        return False
    except Exception as e:
        context.log(f"⚠️ 删除用户档案失败: {str(e)}")
        return False


def delete_user_data(databases: Databases, user_id: str, context) -> dict:
    """
    删除用户的所有数据
    
    Returns:
        删除统计信息
    """
    stats = {
        'profile': 0,
        'mistake_records': 0,
        'user_knowledge_points': 0,
        'subscriptions': 0,
        'practice_sessions': 0,
        'practice_answers': 0,
        'daily_tasks': 0,
        'weekly_reports': 0,
        'review_states': 0,
        'learning_memories': 0,
        'accumulated_analyses': 0,
        'question_generation_tasks': 0,
        'question_feedbacks': 0,
    }
    
    context.log(f"[账户删除] 开始删除用户 {user_id} 的数据...")
    
    # 删除用户档案（profiles 表）
    if delete_user_profile(databases, user_id, context):
        stats['profile'] = 1
        context.log(f"[账户删除] ✅ 已删除用户档案（profiles）")
    else:
        context.log(f"[账户删除] ⚠️ 未找到用户档案或删除失败")
    
    # 删除错题记录
    stats['mistake_records'] = delete_user_documents(
        databases, user_id, 'mistake_records', context
    )
    context.log(f"[账户删除] 已删除 {stats['mistake_records']} 条错题记录")
    
    # 删除用户知识点
    stats['user_knowledge_points'] = delete_user_documents(
        databases, user_id, 'user_knowledge_points', context
    )
    context.log(f"[账户删除] 已删除 {stats['user_knowledge_points']} 个知识点")
    
    # 删除订阅记录
    stats['subscriptions'] = delete_user_documents(
        databases, user_id, 'subscriptions', context
    )
    context.log(f"[账户删除] 已删除 {stats['subscriptions']} 条订阅记录")
    
    # 删除练习会话（需要先删除关联的答题记录）
    # 先删除答题记录
    try:
        # 获取用户的所有练习会话
        sessions = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='practice_sessions',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(100)
            ]
        )
        
        # 删除每个会话的答题记录
        for session in sessions.get('documents', []):
            session_id = session['$id']
            answers = databases.list_documents(
                database_id=DATABASE_ID,
                collection_id='practice_answers',
                queries=[
                    Query.equal('sessionId', session_id),
                    Query.limit(100)
                ]
            )
            
            for answer in answers.get('documents', []):
                try:
                    databases.delete_document(
                        database_id=DATABASE_ID,
                        collection_id='practice_answers',
                        document_id=answer['$id']
                    )
                    stats['practice_answers'] += 1
                except Exception as e:
                    context.log(f"⚠️ 删除答题记录失败: {str(e)}")
    except Exception as e:
        context.log(f"⚠️ 删除答题记录时出错: {str(e)}")
    
    # 删除练习会话
    stats['practice_sessions'] = delete_user_documents(
        databases, user_id, 'practice_sessions', context
    )
    context.log(f"[账户删除] 已删除 {stats['practice_sessions']} 个练习会话")
    
    # 删除每日任务
    stats['daily_tasks'] = delete_user_documents(
        databases, user_id, 'daily_tasks', context
    )
    context.log(f"[账户删除] 已删除 {stats['daily_tasks']} 个每日任务")
    
    # 删除周报
    stats['weekly_reports'] = delete_user_documents(
        databases, user_id, 'weekly_reports', context
    )
    context.log(f"[账户删除] 已删除 {stats['weekly_reports']} 份周报")
    
    # 删除知识点复习状态
    stats['review_states'] = delete_user_documents(
        databases, user_id, 'review_states', context
    )
    context.log(f"[账户删除] 已删除 {stats['review_states']} 条复习状态记录")
    
    # 删除学习记忆
    stats['learning_memories'] = delete_user_documents(
        databases, user_id, 'learning_memories', context
    )
    context.log(f"[账户删除] 已删除 {stats['learning_memories']} 条学习记忆")
    
    # 删除积累错题分析
    stats['accumulated_analyses'] = delete_user_documents(
        databases, user_id, 'accumulated_analyses', context
    )
    context.log(f"[账户删除] 已删除 {stats['accumulated_analyses']} 条积累分析")
    
    # 删除题目生成任务
    stats['question_generation_tasks'] = delete_user_documents(
        databases, user_id, 'question_generation_tasks', context
    )
    context.log(f"[账户删除] 已删除 {stats['question_generation_tasks']} 个题目生成任务")
    
    # 删除题目反馈
    stats['question_feedbacks'] = delete_user_documents(
        databases, user_id, 'question_feedbacks', context
    )
    context.log(f"[账户删除] 已删除 {stats['question_feedbacks']} 条题目反馈")
    
    return stats


def delete_appwrite_account(users: Users, user_id: str, context) -> bool:
    """删除 Appwrite 账户"""
    try:
        users.delete(user_id)
        context.log(f"✅ 已删除 Appwrite 账户")
        return True
    except Exception as e:
        context.log(f"⚠️ 删除 Appwrite 账户失败: {str(e)}")
        return False


def main(context):
    """
    主函数：处理账户删除请求
    
    请求格式：
    {
        "userId": "用户 ID"
    }
    """
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        if isinstance(req.body, dict):
            body = req.body
        elif isinstance(req.body, str):
            import json
            body = json.loads(req.body) if req.body else {}
        else:
            body = {}
        
        user_id = body.get('userId')
        
        if not user_id:
            return res.json({
                'success': False,
                'error': '缺少 userId'
            })
        
        context.log(f"[账户删除] 收到删除请求，用户 ID: {user_id}")
        
        # 初始化服务
        databases = get_databases()
        users = get_users()
        
        # 删除用户的所有数据
        delete_stats = delete_user_data(databases, user_id, context)
        
        # 删除 Appwrite 账户
        account_deleted = delete_appwrite_account(users, user_id, context)
        
        if account_deleted:
            context.log(f"[账户删除] ✅ 账户删除完成")
            return res.json({
                'success': True,
                'message': '账户已成功删除',
                'stats': delete_stats
            })
        else:
            context.log(f"[账户删除] ⚠️ 账户删除部分完成（数据已删除，但账户删除失败）")
            return res.json({
                'success': False,
                'error': '数据已删除，但账户删除失败',
                'stats': delete_stats
            })
        
    except Exception as e:
        context.error(f"[账户删除] 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json({
            'success': False,
            'error': f"服务器错误: {str(e)}"
        })

