"""
Worker 基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
import asyncio
from loguru import logger


class BaseWorker(ABC):
    """Worker 基类"""
    
    def __init__(self):
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def process(self, task_data: Dict[str, Any]) -> Any:
        """
        处理任务的核心逻辑
        
        Args:
            task_data: 任务数据
            
        Returns:
            处理结果
            
        Raises:
            Exception: 处理失败时抛出异常
        """
        pass
    
    async def execute(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务（带错误处理）
        
        Args:
            task_id: 任务ID
            task_data: 任务数据
            
        Returns:
            执行结果字典 {'success': bool, 'result': Any, 'error': str}
        """
        try:
            logger.info(f"[{self.name}] 开始处理任务: {task_id}")
            result = await self.process(task_data)
            logger.info(f"[{self.name}] 任务完成: {task_id}")
            return {
                'success': True,
                'result': result,
                'error': None
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{self.name}] 任务失败: {task_id}, 错误: {error_msg}")
            return {
                'success': False,
                'result': None,
                'error': error_msg
            }

