"""
每日任务调度器 - Appwrite Function
轻量级触发器，负责调用 Worker API 执行任务生成

每天凌晨 2:00 自动执行
"""
import os
import json
import requests
from datetime import datetime


def main(context):
    """
    主入口函数
    触发 Worker 执行每日任务生成
    """
    try:
        # 获取 Worker API 地址
        worker_api_url = os.environ.get('WORKER_API_URL', 'http://localhost:8000')
        
        context.log(f'📅 开始触发每日任务生成: {datetime.now().isoformat()}')
        context.log(f'Worker API: {worker_api_url}')
        
        # 调用 Worker API
        response = requests.post(
            f'{worker_api_url}/tasks/enqueue',
            json={
                'task_type': 'daily_task_generator',
                'task_data': {
                    'trigger_time': datetime.now().isoformat(),
                    'trigger_type': 'scheduled'
                },
                'priority': 3  # 高优先级
            },
            timeout=10  # 10秒超时
        )
        
        response.raise_for_status()
        result = response.json()
        
        context.log(f'✅ 任务已提交到 Worker')
        context.log(f'任务ID: {result.get("task_id")}')
        context.log(f'状态: {result.get("status")}')
        
        return context.res.json({
            'success': True,
            'message': '每日任务生成已触发',
            'task_id': result.get('task_id'),
            'timestamp': datetime.now().isoformat()
        })
        
    except requests.exceptions.Timeout:
        error_msg = 'Worker API 请求超时'
        context.error(f'❌ {error_msg}')
        return context.res.json({
            'success': False,
            'error': error_msg
        }, status_code=500)
        
    except requests.exceptions.ConnectionError:
        error_msg = 'Worker API 连接失败，请检查服务是否运行'
        context.error(f'❌ {error_msg}')
        return context.res.json({
            'success': False,
            'error': error_msg
        }, status_code=500)
        
    except Exception as e:
        error_msg = str(e)
        context.error(f'❌ 触发失败: {error_msg}')
        return context.res.json({
            'success': False,
            'error': error_msg
        }, status_code=500)
