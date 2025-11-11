"""
题目生成触发器 (L1-Trigger)

功能：
1. 监听 question_generation_tasks 表的 create 事件
2. 验证任务数据
3. 调用 Worker API 转发任务
4. 更新任务状态为 processing

环境变量：
- APPWRITE_ENDPOINT: Appwrite API 端点
- APPWRITE_PROJECT_ID: 项目 ID
- APPWRITE_API_KEY: API Key
- APPWRITE_DATABASE_ID: 数据库 ID
- WORKER_API_URL: Worker API 地址
"""

import os
import json
import httpx
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.exception import AppwriteException
from appwrite.query import Query
from datetime import datetime, timezone


def main(context):
    """
    主函数：处理 question_generation_tasks 的创建事件
    
    Args:
        context: Appwrite Function 上下文
        
    Returns:
        响应对象
    """
    
    # 初始化 Appwrite 客户端
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ.get('APPWRITE_PROJECT_ID'))
    client.set_key(os.environ.get('APPWRITE_API_KEY'))
    
    databases = Databases(client)
    database_id = os.environ.get('APPWRITE_DATABASE_ID', 'main')
    worker_url = os.environ.get('WORKER_API_URL', 'http://localhost:8000')
    
    try:
        # 解析事件数据
        if not context.req.body:
            context.res.status_code = 400
            return context.res.json({
                'success': False,
                'error': '无事件数据'
            })
        
        # context.req.body 在事件触发器中可能已经是字典对象
        if isinstance(context.req.body, dict):
            event_data = context.req.body
        elif isinstance(context.req.body, str):
        event_data = json.loads(context.req.body)
        else:
            event_data = {}
            
        context.log(f"[题目生成触发器] 收到事件: {json.dumps(event_data, ensure_ascii=False)}")
        
        # 获取任务文档 ID
        task_id = event_data.get('$id')
        if not task_id:
            context.res.status_code = 400
            return context.res.json({
                'success': False,
                'error': '缺少任务 ID'
            })
        
        # 获取任务详情
        task = databases.get_document(
            database_id=database_id,
            collection_id='question_generation_tasks',
            document_id=task_id
        )
        
        context.log(f"[题目生成触发器] 任务详情: ID={task_id}, 用户={task['userId']}, 类型={task['type']}")
        
        # 🔒 权限检查：变式题生成仅限会员
        user_id = task.get('userId')
        if not user_id:
            raise ValueError('缺少 userId')
        
        # 获取用户档案
        profiles = databases.list_documents(
            database_id=database_id,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if not profiles['documents']:
            raise ValueError('用户档案不存在')
        
        profile = profiles['documents'][0]
        subscription_status = profile.get('subscriptionStatus', 'free')
        
        # 检查是否为活跃会员
        is_premium = False
        if subscription_status == 'active':
            expiry_date = profile.get('subscriptionExpiryDate')
            if expiry_date:
                expiry_datetime = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                if expiry_datetime > datetime.now(timezone.utc):
                    is_premium = True
        
        # 免费用户不能生成变式题
        if not is_premium:
            error_msg = '变式题生成功能仅限会员使用，请升级会员解锁'
            context.log(f"[题目生成触发器] 权限不足: {error_msg}")
            
            # 更新任务状态为 failed
            databases.update_document(
                database_id=database_id,
                collection_id='question_generation_tasks',
                document_id=task_id,
                data={
                    'status': 'failed',
                    'error': error_msg,
                    'completedAt': datetime.utcnow().isoformat() + 'Z'
                }
            )
            
            context.res.status_code = 403
            return context.res.json({
                'success': False,
                'error': error_msg,
                'needsUpgrade': True
            })
        
        context.log(f"[题目生成触发器] 会员验证通过")
        
        # 验证任务数据
        task_type = task.get('type', 'variant')
        source_question_ids = task.get('sourceQuestionIds', [])
        variants_per_question = task.get('variantsPerQuestion', 1)
        
        if not source_question_ids or len(source_question_ids) == 0:
            raise ValueError('sourceQuestionIds 不能为空')
        
        if variants_per_question < 1 or variants_per_question > 10:
            raise ValueError('variantsPerQuestion 必须在 1-10 之间')
        
        # 计算总数
        total_count = len(source_question_ids) * variants_per_question
        
        context.log(f"[题目生成触发器] 验证通过: {len(source_question_ids)} 个源题目, 每题生成 {variants_per_question} 个变式, 共 {total_count} 题")
        
        # 更新任务状态为 processing
        databases.update_document(
            database_id=database_id,
            collection_id='question_generation_tasks',
            document_id=task_id,
            data={
                'status': 'processing',
                'startedAt': datetime.utcnow().isoformat() + 'Z',
                'totalCount': total_count
            }
        )
        
        context.log(f"[题目生成触发器] 任务状态已更新为 processing")
        
        # 调用 Worker API
        try:
            worker_payload = {
                'task_id': task_id,
                'user_id': user_id,
                'task_type': task_type,
                'source_question_ids': source_question_ids,
                'variants_per_question': variants_per_question
            }
            
            context.log(f"[题目生成触发器] 正在调用 Worker API: {worker_url}/tasks/question_generation")
            
            with httpx.Client(timeout=10.0) as http_client:
                response = http_client.post(
                    f"{worker_url}/tasks/question_generation",
                    json=worker_payload
                )
                response.raise_for_status()
                
            worker_result = response.json()
            context.log(f"[题目生成触发器] Worker 响应: {json.dumps(worker_result, ensure_ascii=False)}")
            
            # 更新 workerTaskId（如果 Worker 返回了）
            if 'worker_task_id' in worker_result:
                databases.update_document(
                    database_id=database_id,
                    collection_id='question_generation_tasks',
                    document_id=task_id,
                    data={'workerTaskId': worker_result['worker_task_id']}
                )
            
            return context.res.json({
                'success': True,
                'task_id': task_id,
                'message': f'任务已转发给 Worker，共 {total_count} 道题目待生成'
            })
            
        except httpx.HTTPError as e:
            error_msg = f"Worker API 调用失败: {str(e)}"
            context.error(error_msg)
            
            # 更新任务状态为 failed
            databases.update_document(
                database_id=database_id,
                collection_id='question_generation_tasks',
                document_id=task_id,
                data={
                    'status': 'failed',
                    'error': error_msg,
                    'completedAt': datetime.utcnow().isoformat() + 'Z'
                }
            )
            
            context.res.status_code = 500
            return context.res.json({
                'success': False,
                'error': error_msg
            })
        
    except AppwriteException as e:
        error_msg = f"Appwrite 错误: {str(e)}"
        context.error(error_msg)
        context.res.status_code = 500
        return context.res.json({
            'success': False,
            'error': error_msg
        })
        
    except ValueError as e:
        error_msg = f"数据验证失败: {str(e)}"
        context.error(error_msg)
        
        # 尝试更新任务状态为 failed
        try:
            databases.update_document(
                database_id=database_id,
                collection_id='question_generation_tasks',
                document_id=task_id,
                data={
                    'status': 'failed',
                    'error': error_msg,
                    'completedAt': datetime.utcnow().isoformat() + 'Z'
                }
            )
        except:
            pass
        
        context.res.status_code = 400
        return context.res.json({
            'success': False,
            'error': error_msg
        })
        
    except Exception as e:
        error_msg = f"未知错误: {str(e)}"
        context.error(error_msg)
        context.res.status_code = 500
        return context.res.json({
            'success': False,
            'error': error_msg
        })

