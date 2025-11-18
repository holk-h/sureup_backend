"""
题目裁剪器 - 创建裁剪任务并交给 Worker 处理
根据题号检测bbox，裁剪图片并上传到bucket

工作流程:
1. Flutter 端调用本 Function，传入 imageFileId 和 questionNumber
2. 创建任务记录到 question_cropping_tasks 表
3. 将任务入队到 Worker 系统
4. 立即返回任务ID
5. Worker 异步执行裁剪任务并更新任务状态
6. Flutter 端通过 Realtime API 订阅任务更新
"""
import os
import json
import sys
import requests

# 添加当前目录到 Python 路径（必须在导入 utils 之前）
sys.path.insert(0, os.path.dirname(__file__))

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from utils import success_response, error_response, parse_request_body, get_user_id

# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
QUESTION_CROPPING_TASKS_COLLECTION = 'question_cropping_tasks'
WORKER_API_URL = os.environ.get('WORKER_API_URL', 'http://localhost:8000')
WORKER_API_TIMEOUT = int(os.environ.get('WORKER_API_TIMEOUT', '10'))


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def create_cropping_task(
    databases: Databases,
    user_id: str,
    image_file_id: str,
    question_numbers: list
) -> str:
    """
    创建裁剪任务记录（包含多个题目）
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        image_file_id: 原图文件ID
        question_numbers: 题号列表
    
    Returns:
        任务ID
    """
    task_id = ID.unique()
    total_count = len(question_numbers)
    
    databases.create_document(
        database_id=DATABASE_ID,
        collection_id=QUESTION_CROPPING_TASKS_COLLECTION,
        document_id=task_id,
        data={
            'userId': user_id,
            'imageFileId': image_file_id,
            'questionNumbers': question_numbers,
            'status': 'pending',
            'totalCount': total_count,
            'completedCount': 0,
            'croppedImageIds': [],
        }
    )
    
    return task_id


def enqueue_cropping_task(task_id: str, task_data: dict) -> dict:
    """
    将裁剪任务入队到 Worker 系统
    
    Args:
        task_id: 任务ID
        task_data: 任务数据
        
    Returns:
        入队结果字典 {'success': bool, 'error': str}
    """
    try:
        task_payload = {
            'task_type': 'question_cropper',
            'task_data': task_data,
            'priority': 5  # 默认优先级
        }
        
        response = requests.post(
            f"{WORKER_API_URL}/tasks/enqueue",
            json=task_payload,
            timeout=WORKER_API_TIMEOUT
        )
        
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 任务已入队: task_id={task_id}, worker_task_id={result.get('task_id')}")
        
        return {
            'success': True,
            'error': None
        }
        
    except requests.exceptions.Timeout:
        error_msg = f"Worker API 超时（{WORKER_API_TIMEOUT}秒）"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Worker API 请求失败: {str(e)}"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }
        
    except Exception as e:
        error_msg = f"未知错误: {str(e)}"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        image_file_id = body.get('imageFileId')
        question_numbers = body.get('questionNumbers', [])
        
        if not image_file_id:
            return res.json(error_response("缺少参数: imageFileId", 400))
        if not question_numbers or not isinstance(question_numbers, list):
            return res.json(error_response("缺少参数: questionNumbers (应为数组)", 400))
        if len(question_numbers) == 0:
            return res.json(error_response("questionNumbers 不能为空", 400))
        
        # 获取用户ID
        user_id = get_user_id(req)
        if not user_id:
            return res.json(error_response("无法获取用户ID", 401))
        
        # 初始化服务
        databases = get_databases()
        
        # 创建任务记录（包含所有题目）
        task_id = create_cropping_task(
            databases=databases,
            user_id=user_id,
            image_file_id=image_file_id,
            question_numbers=question_numbers
        )
        
        # 将任务入队到 Worker 系统
        task_data = {
            'task_id': task_id,
            'user_id': user_id,
            'image_file_id': image_file_id,
            'question_numbers': question_numbers,
        }
        
        enqueue_result = enqueue_cropping_task(task_id, task_data)
        
        if not enqueue_result['success']:
            # 入队失败，更新任务状态为 failed
            try:
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=QUESTION_CROPPING_TASKS_COLLECTION,
                    document_id=task_id,
                    data={
                        'status': 'failed',
                        'error': enqueue_result['error'],
                    }
                )
            except Exception as e:
                print(f"更新任务状态失败: {str(e)}")
            
            return res.json(error_response(
                f"任务创建失败: {enqueue_result['error']}",
                500
            ))
        
        # 返回任务ID
        return res.json(success_response({
            'taskId': task_id,
            'status': 'pending'
        }, "任务已创建，正在处理中"))
        
    except ValueError as e:
        return res.json(error_response(str(e), 400))
    except Exception as e:
        context.log(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json(error_response(f"服务器错误: {str(e)}", 500))

