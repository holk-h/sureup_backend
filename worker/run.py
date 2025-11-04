"""
Worker 启动脚本
使用此脚本代替直接运行 app.py，确保导入路径正确
"""
import sys
import os

# 将当前目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入并运行
if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    from loguru import logger
    from config import config
    
    # 加载环境变量
    load_dotenv()
    
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
    
    # 启动 uvicorn
    uvicorn.run(
        "app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        workers=config.API_WORKERS,
        log_level=config.LOG_LEVEL.lower(),
        reload=False  # 生产环境禁用热重载
    )

