"""
L1-Trigger: mistake-analyzer (Task Queue 版本)
错题分析器 - 将任务入队到 Worker 系统，不执行实际分析

Event Trigger: 
- databases.*.collections.mistake_records.documents.*.create
- databases.*.collections.mistake_records.documents.*.update

新设计：一条错题记录 = 一道题 = 一张或多张图片（支持跨页题目）

新的工作流程:
1. Flutter 端上传图片到 bucket，为每道题创建一个 mistake_record (analysisStatus: "pending")
   - 单图题：originalImageIds: ["image_id_1"]
   - 多图题：originalImageIds: ["image_id_1", "image_id_2", "image_id_3"]
2. 本 function 被自动触发（create 事件）
3. 验证任务并入队到 Worker 系统
4. 立即返回（不等待处理）
5. Worker 异步执行实际的分析任务（支持多图）
6. Worker 更新 analysisStatus 为 "completed" 或 "failed"
7. Flutter 端通过 Realtime API 订阅更新，实时显示分析结果

优势:
- 支持 1000+ 并发任务
- 不受 Appwrite Function 单 worker 限制
- 长时间 LLM 调用不会阻塞
- 更好的错误处理和重试机制
- 支持单图和多图题目（跨页题目）
"""
import os
import json
import requests


# Configuration
WORKER_API_URL = os.environ.get('WORKER_API_URL', 'http://localhost:8000')
WORKER_API_TIMEOUT = int(os.environ.get('WORKER_API_TIMEOUT', '10'))  # 增加到 10 秒


def enqueue_analysis_task(record_data: dict) -> dict:
    """
    将分析任务入队到 Worker 系统
    
    Args:
        record_data: 错题记录文档数据
        
    Returns:
        入队结果字典 {'success': bool, 'task_id': str, 'error': str}
    """
    record_id = record_data.get('$id')
    
    try:
        # 构建任务数据
        task_payload = {
            'task_type': 'mistake_analyzer',
            'task_data': {
                'record_data': record_data
            },
            'priority': 5  # 默认优先级（1-10，数字越小优先级越高）
        }
        
        # 调用 Worker API 入队
        response = requests.post(
            f"{WORKER_API_URL}/tasks/enqueue",
            json=task_payload,
            timeout=WORKER_API_TIMEOUT
        )
        
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 任务已入队: record_id={record_id}, task_id={result.get('task_id')}")
        
        return {
            'success': True,
            'task_id': result.get('task_id'),
            'message': '任务已入队，等待处理',
            'error': None
        }
        
    except requests.exceptions.Timeout:
        error_msg = f"Worker API 超时（{WORKER_API_TIMEOUT}秒）"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'task_id': None,
            'message': None,
            'error': error_msg
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Worker API 请求失败: {str(e)}"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'task_id': None,
            'message': None,
            'error': error_msg
        }
        
    except Exception as e:
        error_msg = f"未知错误: {str(e)}"
        print(f"❌ 入队失败: {error_msg}")
        return {
            'success': False,
            'task_id': None,
            'message': None,
            'error': error_msg
        }


def main(context):
    """Main entry point for Appwrite Event Trigger"""
    try:
        req = context.req
        
        # 解析 event 数据
        event_body = req.body
        if isinstance(event_body, str):
            event_data = json.loads(event_body)
        else:
            event_data = event_body
        
        context.log(f"收到事件: {json.dumps(event_data, ensure_ascii=False)[:500]}")
        
        record_data = event_data
        
        # 检查是否需要分析（只处理 pending 状态）
        analysis_status = record_data.get('analysisStatus', 'pending')
        
        if analysis_status != 'pending':
            context.log(f"⏭️  跳过分析: 状态是 {analysis_status}")
            return context.res.empty()
        
        # 验证必要字段
        record_id = record_data.get('$id')
        original_image_ids = record_data.get('originalImageIds', [])
        
        if not record_id:
            context.error("错题记录缺少ID")
            return context.res.empty()
            
        if not original_image_ids or len(original_image_ids) == 0:
            context.error(f"错题记录 {record_id} 缺少图片ID")
            return context.res.empty()
        
        # 记录图片数量
        image_count = len(original_image_ids)
        is_multi_photo = image_count > 1
        context.log(f"📸 准备分析: record_id={record_id}, 图片数={image_count}, 多图题={is_multi_photo}")
        
        # 将任务入队到 Worker 系统
        result = enqueue_analysis_task(record_data)
        
        if result['success']:
            context.log(f"✅ 任务入队成功: record_id={record_id}, task_id={result.get('task_id')}, 图片数={image_count}")
        else:
            context.error(f"❌ 任务入队失败: record_id={record_id}, 图片数={image_count}, error={result.get('error')}")
        
        # 无论成功或失败，都立即返回（不阻塞）
        # Worker 系统会异步处理任务并更新数据库
        return context.res.empty()
        
    except Exception as e:
        context.error(f"❌ Function 处理失败: {str(e)}")
        return context.res.empty()
