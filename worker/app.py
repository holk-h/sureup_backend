"""
Worker 主应用
FastAPI + 异步任务队列，支持高并发任务处理
"""
# 重要：最先加载环境变量
from dotenv import load_dotenv
load_dotenv()

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, Any
from loguru import logger

from config import config
from task_queue.memory_queue import MemoryQueue
from task_queue.base import TaskQueue
from tasks import TaskBase, TaskResponse, TaskStatus, QueueStats, task_registry
from workers.mistake_analyzer import MistakeAnalyzerWorker
from workers.daily_task_generator import DailyTaskGeneratorWorker
from workers.accumulated_mistakes_analyzer import AccumulatedMistakesAnalyzerWorker


# ========== 全局变量 ==========
task_queue: TaskQueue = None
worker_tasks: list = []


# ========== 初始化和清理 ==========

async def init_queue():
    """初始化任务队列"""
    global task_queue
    
    if config.QUEUE_TYPE == 'memory':
        logger.info("使用内存队列")
        task_queue = MemoryQueue()
    elif config.QUEUE_TYPE == 'redis':
        logger.warning("Redis 队列尚未实现，使用内存队列")
        task_queue = MemoryQueue()
    else:
        logger.warning(f"未知的队列类型: {config.QUEUE_TYPE}，使用内存队列")
        task_queue = MemoryQueue()


def register_workers():
    """注册所有 worker"""
    task_registry.register('mistake_analyzer', MistakeAnalyzerWorker)
    task_registry.register('daily_task_generator', DailyTaskGeneratorWorker)
    task_registry.register('accumulated_mistakes_analyzer', AccumulatedMistakesAnalyzerWorker)
    logger.info(f"已注册任务类型: {task_registry.list_task_types()}")


async def start_worker_pool():
    """启动 worker 池"""
    global worker_tasks
    
    logger.info(f"启动 {config.WORKER_CONCURRENCY} 个并发 worker...")
    
    for i in range(config.WORKER_CONCURRENCY):
        task = asyncio.create_task(worker_loop(worker_id=i))
        worker_tasks.append(task)
    
    logger.info("Worker 池已启动")


async def worker_loop(worker_id: int):
    """
    Worker 循环 - 持续从队列中取任务并处理
    
    Args:
        worker_id: Worker ID
    """
    worker_name = f"Worker-{worker_id}"
    logger.info(f"{worker_name} 启动")
    
    while True:
        try:
            # 从队列取任务（超时 1 秒）
            task = await task_queue.dequeue(timeout=1.0)
            
            if not task:
                # 没有任务，继续等待
                await asyncio.sleep(0.1)
                continue
            
            task_id = task['task_id']
            task_type = task['task_type']
            task_data = task['task_data']
            
            logger.info(f"[{worker_name}] 开始处理: {task_id} (类型: {task_type})")
            
            try:
                # 获取对应的 worker 类
                worker_class = task_registry.get_worker_class(task_type)
                worker = worker_class()
                
                # 执行任务（带超时）
                result = await asyncio.wait_for(
                    worker.execute(task_id, task_data),
                    timeout=config.WORKER_TIMEOUT
                )
                
                # 标记任务完成或失败
                if result['success']:
                    await task_queue.mark_completed(task_id, result.get('result'))
                    logger.info(f"✅ [{worker_name}] 任务完成: {task_id}")
                else:
                    await task_queue.mark_failed(task_id, result.get('error', '未知错误'))
                    logger.error(f"❌ [{worker_name}] 任务失败: {task_id}, 错误: {result.get('error')}")
                
            except asyncio.TimeoutError:
                error_msg = f"任务超时（{config.WORKER_TIMEOUT}秒）"
                await task_queue.mark_failed(task_id, error_msg)
                logger.error(f"⏱️ [{worker_name}] 任务超时: {task_id}")
                
            except KeyError as e:
                error_msg = f"未注册的任务类型: {task_type}"
                await task_queue.mark_failed(task_id, error_msg)
                logger.error(f"❌ [{worker_name}] {error_msg}")
                
            except Exception as e:
                error_msg = f"Worker 异常: {str(e)}"
                await task_queue.mark_failed(task_id, error_msg)
                logger.exception(f"💥 [{worker_name}] 发生异常: {task_id}")
        
        except Exception as e:
            # Worker 循环本身的异常，记录但不退出
            logger.exception(f"💥 [{worker_name}] 循环异常: {str(e)}")
            await asyncio.sleep(1.0)


async def stop_worker_pool():
    """停止 worker 池"""
    global worker_tasks
    
    logger.info("停止 worker 池...")
    
    for task in worker_tasks:
        task.cancel()
    
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    worker_tasks.clear()
    
    logger.info("Worker 池已停止")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("初始化 Worker 系统...")
    
    await init_queue()
    register_workers()
    await start_worker_pool()
    
    logger.info("Worker 系统已启动")
    
    yield
    
    # 关闭时清理
    logger.info("关闭 Worker 系统...")
    await stop_worker_pool()
    logger.info("Worker 系统已关闭")


# ========== FastAPI 应用 ==========

app = FastAPI(
    title="SureUp Worker API",
    description="异步任务处理系统 - 支持高并发长时间任务",
    version="1.0.0",
    lifespan=lifespan
)


# ========== API 路由 ==========

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "running",
        "message": "SureUp Worker API",
        "version": "1.0.0"
    }


@app.post("/tasks/enqueue", response_model=TaskResponse)
async def enqueue_task(task: TaskBase):
    """
    将任务加入队列
    
    Args:
        task: 任务数据
        
    Returns:
        任务ID和状态
    """
    try:
        task_id = await task_queue.enqueue(
            task_type=task.task_type,
            task_data=task.task_data,
            priority=task.priority
        )
        
        logger.info(f"任务已入队: {task_id} (类型: {task.task_type})")
        
        return TaskResponse(
            task_id=task_id,
            status="pending",
            message="任务已入队"
        )
    except Exception as e:
        logger.error(f"入队失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    获取任务状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        任务状态信息
    """
    try:
        status = await task_queue.get_task_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return TaskStatus(**status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/stats", response_model=QueueStats)
async def get_queue_stats():
    """
    获取队列统计信息
    
    Returns:
        队列统计数据
    """
    try:
        stats = await task_queue.get_queue_stats()
        return QueueStats(**stats)
    except Exception as e:
        logger.error(f"获取队列统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workers/types")
async def list_worker_types():
    """
    列出所有已注册的 worker 类型
    
    Returns:
        Worker 类型列表
    """
    return {
        "worker_types": task_registry.list_task_types(),
        "concurrency": config.WORKER_CONCURRENCY
    }


# ========== 错误处理 ==========

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.exception(f"未处理的异常: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "内部服务器错误",
            "detail": str(exc)
        }
    )


# ========== 主入口 ==========

if __name__ == "__main__":
    import uvicorn
    
    # 配置日志
    logger.add(
        "logs/worker_{time}.log",
        rotation="100 MB",
        retention="30 days",
        level=config.LOG_LEVEL
    )
    
    logger.info("启动 Worker API 服务器...")
    logger.info(f"监听地址: {config.API_HOST}:{config.API_PORT}")
    logger.info(f"并发数: {config.WORKER_CONCURRENCY}")
    logger.info(f"队列类型: {config.QUEUE_TYPE}")
    
    uvicorn.run(
        "app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        workers=config.API_WORKERS,
        log_level=config.LOG_LEVEL.lower()
    )

