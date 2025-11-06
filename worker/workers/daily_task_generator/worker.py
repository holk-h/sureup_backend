"""
每日任务生成 Worker 实现
"""
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from workers.base import BaseWorker
from .utils import get_databases
from .task_generator import get_active_users, generate_daily_task_for_user


class DailyTaskGeneratorWorker(BaseWorker):
    """每日任务生成 Worker"""
    
    def __init__(self):
        super().__init__()
        self.db = None
    
    def _init_services(self):
        """初始化服务（延迟初始化）"""
        if not self.db:
            self.db = get_databases()
    
    async def process(self, task_data: Dict[str, Any]) -> Any:
        """
        处理每日任务生成
        
        Args:
            task_data: 任务数据
            
        Returns:
            生成结果统计
        """
        trigger_time = task_data.get('trigger_time', datetime.now().isoformat())
        trigger_type = task_data.get('trigger_type', 'manual')
        
        logger.info(f"开始生成每日任务: trigger_time={trigger_time}, type={trigger_type}")
        
        # 初始化服务
        self._init_services()
        
        # 获取所有活跃用户
        active_users = get_active_users(self.db)
        logger.info(f"找到 {len(active_users)} 个活跃用户")
        
        if not active_users:
            return {
                'success': True,
                'message': '没有活跃用户',
                'total_users': 0,
                'success_count': 0,
                'skip_count': 0,
                'error_count': 0
            }
        
        # 统计
        success_count = 0
        skip_count = 0
        error_count = 0
        user_results = []
        
        # 为每个用户生成任务
        for user in active_users:
            user_id = user.get('userId', 'unknown')
            
            try:
                result = generate_daily_task_for_user(user, self.db)
                
                if result['generated']:
                    success_count += 1
                    logger.info(
                        f"✓ 用户 {user_id}: "
                        f"生成 {result['total_questions']} 道题"
                    )
                    user_results.append({
                        'user_id': user_id,
                        'status': 'success',
                        'questions': result['total_questions']
                    })
                else:
                    skip_count += 1
                    logger.info(f"○ 用户 {user_id}: {result['reason']}")
                    user_results.append({
                        'user_id': user_id,
                        'status': 'skipped',
                        'reason': result['reason']
                    })
                    
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                logger.error(f"✗ 用户 {user_id} 生成失败: {error_msg}")
                user_results.append({
                    'user_id': user_id,
                    'status': 'failed',
                    'error': error_msg
                })
        
        # 返回结果
        summary = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'trigger_type': trigger_type,
            'total_users': len(active_users),
            'success_count': success_count,
            'skip_count': skip_count,
            'error_count': error_count,
            'user_results': user_results[:10]  # 只返回前10个用户的详情
        }
        
        logger.info(
            f"任务生成完成: 成功={success_count}, "
            f"跳过={skip_count}, 失败={error_count}"
        )
        
        return summary

