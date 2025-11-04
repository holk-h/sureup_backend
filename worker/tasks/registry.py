"""
任务注册表 - 管理所有可用的 worker 类型
"""
from typing import Dict, Type
from workers.base import BaseWorker


class TaskRegistry:
    """任务注册表"""
    
    def __init__(self):
        self._workers: Dict[str, Type[BaseWorker]] = {}
    
    def register(self, task_type: str, worker_class: Type[BaseWorker]):
        """
        注册一个 worker
        
        Args:
            task_type: 任务类型标识
            worker_class: Worker 类
        """
        self._workers[task_type] = worker_class
    
    def get_worker_class(self, task_type: str) -> Type[BaseWorker]:
        """
        获取 worker 类
        
        Args:
            task_type: 任务类型标识
            
        Returns:
            Worker 类
            
        Raises:
            KeyError: 如果任务类型未注册
        """
        if task_type not in self._workers:
            raise KeyError(f"未注册的任务类型: {task_type}")
        return self._workers[task_type]
    
    def list_task_types(self):
        """列出所有已注册的任务类型"""
        return list(self._workers.keys())


# 全局注册表实例
task_registry = TaskRegistry()

