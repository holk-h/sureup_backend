"""
基于内存的任务队列实现
适用于单实例开发和测试环境
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional, Any
from collections import defaultdict
import heapq

from .base import TaskQueue


class MemoryQueue(TaskQueue):
    """内存任务队列"""
    
    def __init__(self):
        self._queue = []  # 优先级队列（使用 heapq）
        self._tasks = {}  # 任务存储 {task_id: task_info}
        self._stats = defaultdict(int)  # 统计信息
        self._lock = asyncio.Lock()  # 锁保护共享数据
        self._not_empty = asyncio.Condition(self._lock)  # 条件变量，用于等待任务
        
    async def enqueue(self, task_type: str, task_data: Dict[str, Any], priority: int = 5) -> str:
        """将任务加入队列"""
        async with self._lock:
            task_id = str(uuid.uuid4())
            
            task_info = {
                'task_id': task_id,
                'task_type': task_type,
                'task_data': task_data,
                'priority': priority,
                'status': 'pending',
                'enqueued_at': datetime.utcnow().isoformat() + 'Z',
                'started_at': None,
                'completed_at': None,
                'result': None,
                'error': None
            }
            
            # 加入优先级队列（priority 越小越优先）
            heapq.heappush(self._queue, (priority, task_id))
            self._tasks[task_id] = task_info
            self._stats['pending'] += 1
            self._stats['total'] += 1
            
            # 通知等待的消费者
            self._not_empty.notify()
            
            return task_id
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """从队列取出任务"""
        async with self._not_empty:
            # 等待队列非空
            if not self._queue:
                if timeout is not None:
                    try:
                        await asyncio.wait_for(self._not_empty.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        return None
                else:
                    await self._not_empty.wait()
            
            if not self._queue:
                return None
            
            # 取出优先级最高的任务
            _, task_id = heapq.heappop(self._queue)
            task_info = self._tasks.get(task_id)
            
            if not task_info:
                return None
            
            # 更新任务状态
            task_info['status'] = 'processing'
            task_info['started_at'] = datetime.utcnow().isoformat() + 'Z'
            
            self._stats['pending'] -= 1
            self._stats['processing'] += 1
            
            return {
                'task_id': task_info['task_id'],
                'task_type': task_info['task_type'],
                'task_data': task_info['task_data'],
                'enqueued_at': task_info['enqueued_at']
            }
    
    async def mark_completed(self, task_id: str, result: Any = None) -> None:
        """标记任务完成"""
        async with self._lock:
            task_info = self._tasks.get(task_id)
            if task_info and task_info['status'] == 'processing':
                task_info['status'] = 'completed'
                task_info['completed_at'] = datetime.utcnow().isoformat() + 'Z'
                task_info['result'] = result
                
                self._stats['processing'] -= 1
                self._stats['completed'] += 1
    
    async def mark_failed(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        async with self._lock:
            task_info = self._tasks.get(task_id)
            if task_info and task_info['status'] == 'processing':
                task_info['status'] = 'failed'
                task_info['completed_at'] = datetime.utcnow().isoformat() + 'Z'
                task_info['error'] = error
                
                self._stats['processing'] -= 1
                self._stats['failed'] += 1
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        async with self._lock:
            task_info = self._tasks.get(task_id)
            if not task_info:
                return None
            
            return {
                'task_id': task_info['task_id'],
                'task_type': task_info['task_type'],
                'status': task_info['status'],
                'enqueued_at': task_info['enqueued_at'],
                'started_at': task_info['started_at'],
                'completed_at': task_info['completed_at'],
                'result': task_info['result'],
                'error': task_info['error']
            }
    
    async def get_queue_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        async with self._lock:
            return dict(self._stats)

