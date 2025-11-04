"""
任务队列基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import asyncio


class TaskQueue(ABC):
    """任务队列抽象基类"""
    
    @abstractmethod
    async def enqueue(self, task_type: str, task_data: Dict[str, Any], priority: int = 5) -> str:
        """
        将任务加入队列
        
        Args:
            task_type: 任务类型（如 'mistake_analyzer'）
            task_data: 任务数据
            priority: 优先级（1-10，数字越小优先级越高）
            
        Returns:
            任务ID
        """
        pass
    
    @abstractmethod
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        从队列取出任务
        
        Args:
            timeout: 超时时间（秒），None 表示一直等待
            
        Returns:
            任务字典，包含 task_id, task_type, task_data, enqueued_at 等字段
            如果超时返回 None
        """
        pass
    
    @abstractmethod
    async def mark_completed(self, task_id: str, result: Any = None) -> None:
        """
        标记任务完成
        
        Args:
            task_id: 任务ID
            result: 任务结果（可选）
        """
        pass
    
    @abstractmethod
    async def mark_failed(self, task_id: str, error: str) -> None:
        """
        标记任务失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
        """
        pass
    
    @abstractmethod
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态字典，包含 status, result, error 等字段
        """
        pass
    
    @abstractmethod
    async def get_queue_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息
        
        Returns:
            统计字典，包含 pending, processing, completed, failed 等计数
        """
        pass

