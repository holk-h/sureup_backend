"""
错题分析 Worker 实现

这个 Worker 处理错题图片的 AI 分析任务
完全复用了原 Appwrite Function 的核心逻辑
"""
from typing import Dict, Any
import os
import asyncio
from loguru import logger

from workers.base import BaseWorker
from workers.mistake_analyzer.helpers.utils import get_databases, get_storage
from workers.mistake_analyzer.main import process_mistake_analysis


class MistakeAnalyzerWorker(BaseWorker):
    """错题分析 Worker"""
    
    def __init__(self):
        super().__init__()
        self.databases = None
        self.storage = None
    
    def _init_services(self):
        """初始化 Appwrite 服务（延迟初始化）"""
        if not self.databases:
            self.databases = get_databases()
        if not self.storage:
            self.storage = get_storage()
    
    async def process(self, task_data: Dict[str, Any]) -> Any:
        """
        处理错题分析任务
        
        Args:
            task_data: 包含 record_data 字段的任务数据
            
        Returns:
            分析结果
        """
        # 获取错题记录数据
        record_data = task_data.get('record_data')
        if not record_data:
            raise ValueError("缺少 record_data 字段")
        
        record_id = record_data.get('$id')
        analysis_status = record_data.get('analysisStatus', 'pending')
        
        logger.info(f"收到错题分析任务: record_id={record_id}, status={analysis_status}")
        
        # 检查是否需要分析（只处理 pending 状态）
        if analysis_status != 'pending':
            logger.info(f"跳过分析: 状态是 {analysis_status}")
            return {
                'skipped': True,
                'reason': f'状态不是 pending: {analysis_status}'
            }
        
        # 初始化服务
        self._init_services()
        
        # 调用原有的分析逻辑（现在是异步的）
        try:
            # 直接调用异步函数，LLM 请求会并发执行
            await process_mistake_analysis(
                record_data,
                self.databases,
                self.storage
            )
            
            return {
                'success': True,
                'record_id': record_id,
                'message': '分析完成'
            }
        except Exception as e:
            logger.error(f"错题分析失败: {str(e)}")
            raise

