"""
Worker 配置管理
"""
import os
from typing import Optional


class Config:
    """Worker 配置类"""
    
    # Appwrite 配置
    APPWRITE_ENDPOINT: str = os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1')
    APPWRITE_PROJECT_ID: str = os.environ.get('APPWRITE_PROJECT_ID', '')
    APPWRITE_API_KEY: str = os.environ.get('APPWRITE_API_KEY', '')
    APPWRITE_DATABASE_ID: str = os.environ.get('APPWRITE_DATABASE_ID', 'main')
    
    # 火山引擎 LLM 配置（兼容豆包配置）
    # 优先使用 DOUBAO_ 前缀（向后兼容），也支持 VOLC_ 前缀
    VOLC_API_KEY: str = os.environ.get('VOLC_API_KEY') or os.environ.get('DOUBAO_API_KEY', '')
    VOLC_ENDPOINT_ID: str = os.environ.get('VOLC_ENDPOINT_ID') or os.environ.get('DOUBAO_MODEL', '')
    VOLC_ENDPOINT: str = os.environ.get('VOLC_ENDPOINT') or os.environ.get('DOUBAO_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3')
    
    # 火山引擎高级参数
    VOLC_TEMPERATURE: float = float(os.environ.get('VOLC_TEMPERATURE', '0.7'))
    VOLC_TOP_P: float = float(os.environ.get('VOLC_TOP_P', '0.9'))
    VOLC_MAX_TOKENS: int = int(os.environ.get('VOLC_MAX_TOKENS', '4096'))
    VOLC_THINKING_ENABLED: bool = os.environ.get('VOLC_THINKING_ENABLED', 'false').lower() == 'true'
    VOLC_STREAM: bool = os.environ.get('VOLC_STREAM', 'false').lower() == 'true'
    VOLC_TIMEOUT: int = int(os.environ.get('VOLC_TIMEOUT', '120'))
    VOLC_MAX_RETRIES: int = int(os.environ.get('VOLC_MAX_RETRIES', '3'))
    
    # Worker 配置
    WORKER_CONCURRENCY: int = int(os.environ.get('WORKER_CONCURRENCY', '100'))  # 并发数
    WORKER_TIMEOUT: int = int(os.environ.get('WORKER_TIMEOUT', '300'))  # 任务超时（秒）
    
    # 队列配置
    QUEUE_TYPE: str = os.environ.get('QUEUE_TYPE', 'memory')  # memory 或 redis
    REDIS_URL: Optional[str] = os.environ.get('REDIS_URL', None)  # redis://localhost:6379
    
    # FastAPI 配置
    API_HOST: str = os.environ.get('API_HOST', '0.0.0.0')
    API_PORT: int = int(os.environ.get('API_PORT', '8000'))
    API_WORKERS: int = int(os.environ.get('API_WORKERS', '1'))
    
    # 日志配置
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'INFO')
    
    def validate(self):
        """验证必需的配置项"""
        required_vars = {
            'APPWRITE_PROJECT_ID': self.APPWRITE_PROJECT_ID,
            'APPWRITE_API_KEY': self.APPWRITE_API_KEY,
        }
        
        missing = [key for key, value in required_vars.items() if not value]
        
        if missing:
            raise ValueError(
                f"缺少必需的环境变量: {', '.join(missing)}\n"
                f"请检查 .env 文件是否正确配置"
            )
        
        # 火山引擎 LLM 配置验证
        if not self.VOLC_API_KEY:
            raise ValueError("需要配置 VOLC_API_KEY 或 DOUBAO_API_KEY")
        if not self.VOLC_ENDPOINT_ID:
            raise ValueError("需要配置 VOLC_ENDPOINT_ID 或 DOUBAO_MODEL")


# 全局配置实例
config = Config()

# 启动时验证配置
try:
    config.validate()
    print(f"✅ 配置验证通过")
    print(f"   - Appwrite Project: {config.APPWRITE_PROJECT_ID}")
    print(f"   - 火山引擎 Endpoint ID: {config.VOLC_ENDPOINT_ID}")
    print(f"   - 火山引擎 API 地址: {config.VOLC_ENDPOINT}")
    print(f"   - Worker Concurrency: {config.WORKER_CONCURRENCY}")
    if config.VOLC_THINKING_ENABLED:
        print(f"   - 思考模式: 已启用")
except ValueError as e:
    print(f"❌ 配置验证失败: {e}")
    import sys
    sys.exit(1)

