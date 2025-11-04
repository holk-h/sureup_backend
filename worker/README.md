# SureUp Worker 系统

异步任务处理系统，支持高并发长时间任务处理。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     Appwrite Function                            │
│                  (mistake-analyzer 等)                           │
│                                                                   │
│  1. 接收事件触发                                                 │
│  2. 验证任务数据                                                 │
│  3. 调用 Worker API 入队                                         │
│  4. 立即返回 202 Accepted                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP POST /tasks/enqueue
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Worker API (FastAPI)                        │
│                                                                   │
│  • 接收任务请求                                                  │
│  • 任务入队（优先级队列）                                        │
│  • 提供任务状态查询                                              │
│  • 提供队列统计                                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                       任务队列                                    │
│                   (Memory / Redis)                               │
│                                                                   │
│  • 优先级队列                                                     │
│  • 任务状态管理                                                   │
│  • 支持并发访问                                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Worker 池 (100+ 并发)                         │
│                                                                   │
│  Worker-0  Worker-1  Worker-2  ...  Worker-N                    │
│     │         │         │              │                         │
│     └─────────┴─────────┴──────────────┘                        │
│                    │                                              │
│         1. 从队列取任务                                           │
│         2. 调用对应的 Worker 处理                                 │
│         3. 更新任务状态                                           │
│         4. 返回队列继续                                           │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  具体的 Worker 实现                              │
│                                                                   │
│  • MistakeAnalyzerWorker - 错题分析                             │
│  • 其他 Worker...                                                │
│                                                                   │
│  执行真正的业务逻辑（LLM 调用、图片分析等）                       │
└─────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
backend/worker/
├── app.py                     # FastAPI 主应用
├── config.py                  # 配置管理
├── requirements.txt           # 依赖
├── README.md                  # 本文档
├── task_queue/                # 任务队列（重命名避免与标准库冲突）
│   ├── __init__.py
│   ├── base.py                # 队列基类
│   ├── memory_queue.py        # 内存队列实现
│   └── redis_queue.py         # Redis 队列实现（未来）
├── tasks/
│   ├── __init__.py
│   ├── models.py              # 任务数据模型
│   └── registry.py            # 任务注册表
└── workers/
    ├── __init__.py
    ├── base.py                # Worker 基类
    └── mistake_analyzer/
        ├── __init__.py
        ├── worker.py          # Worker 实现
        ├── image_analyzer.py  # 图片分析
        ├── llm_provider.py    # LLM 提供商
        ├── question_service.py
        ├── knowledge_point_service.py
        ├── utils.py
        └── main.py            # 原有的处理逻辑
```

## 核心特性

### 1. 高并发处理

- 默认支持 100+ 并发 worker
- 每个 worker 独立处理任务
- 非阻塞异步架构
- 适合 LLM 调用等长时间任务

### 2. 优先级队列

- 支持 1-10 级优先级（数字越小优先级越高）
- 自动按优先级调度任务
- 先进先出（FIFO）保证公平性

### 3. 任务状态管理

任务状态流转：

```
pending → processing → completed
                    → failed
```

### 4. 可扩展架构

- 易于添加新的 Worker 类型
- 统一的任务注册机制
- 清晰的接口定义

### 5. 队列实现

当前支持：
- **内存队列**：开发和单实例部署
- **Redis 队列**（计划中）：分布式多实例部署

## 快速开始

### 1. 安装依赖

```bash
cd backend/worker
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# Appwrite 配置
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main

# LLM 配置
LLM_PROVIDER=doubao
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=doubao-pro-32k
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# Worker 配置
WORKER_CONCURRENCY=100     # 并发数
WORKER_TIMEOUT=300         # 任务超时（秒）

# 队列配置
QUEUE_TYPE=memory          # memory 或 redis

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
```

### 3. 启动 Worker 服务

**推荐方式**（使用启动脚本）：

```bash
# 方式 1: 使用 Python 启动脚本
python3 run.py

# 方式 2: 使用 Shell 脚本
bash start.sh
```

**直接使用 uvicorn**（需要设置环境变量）：

```bash
# 先加载环境变量
export $(cat .env | grep -v '^#' | xargs)

# 然后启动
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/

# 查看队列统计
curl http://localhost:8000/queue/stats

# 查看已注册的 Worker 类型
curl http://localhost:8000/workers/types
```

## API 接口

### 1. 入队任务

**POST** `/tasks/enqueue`

请求体：
```json
{
  "task_type": "mistake_analyzer",
  "task_data": {
    "record_data": {
      "$id": "record-id",
      "userId": "user-id",
      "originalImageId": "image-id",
      "analysisStatus": "pending"
    }
  },
  "priority": 5
}
```

响应：
```json
{
  "task_id": "uuid",
  "status": "pending",
  "message": "任务已入队"
}
```

### 2. 查询任务状态

**GET** `/tasks/{task_id}`

响应：
```json
{
  "task_id": "uuid",
  "task_type": "mistake_analyzer",
  "status": "completed",
  "enqueued_at": "2024-01-01T00:00:00Z",
  "started_at": "2024-01-01T00:00:01Z",
  "completed_at": "2024-01-01T00:00:30Z",
  "result": {...},
  "error": null
}
```

### 3. 队列统计

**GET** `/queue/stats`

响应：
```json
{
  "total": 100,
  "pending": 10,
  "processing": 5,
  "completed": 80,
  "failed": 5
}
```

### 4. Worker 类型列表

**GET** `/workers/types`

响应：
```json
{
  "worker_types": ["mistake_analyzer"],
  "concurrency": 100
}
```

## 添加新 Worker

### 1. 创建 Worker 类

```python
# workers/my_worker/worker.py
from typing import Dict, Any
from ..base import BaseWorker

class MyWorker(BaseWorker):
    async def process(self, task_data: Dict[str, Any]) -> Any:
        """实现你的处理逻辑"""
        # 处理任务
        result = do_something(task_data)
        return result
```

### 2. 注册 Worker

在 `app.py` 中注册：

```python
from workers.my_worker import MyWorker

def register_workers():
    task_registry.register('mistake_analyzer', MistakeAnalyzerWorker)
    task_registry.register('my_worker', MyWorker)  # 新增
```

### 3. 调用

```bash
curl -X POST http://localhost:8000/tasks/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "my_worker",
    "task_data": {...},
    "priority": 5
  }'
```

## 修改 Appwrite Function

原 Appwrite Function 需要改为只负责入队，不再执行实际逻辑。

### 修改前（mistake-analyzer/src/main.py）

```python
def main(context):
    # 执行完整的分析逻辑
    process_mistake_analysis(record_data, databases, storage)
    return context.res.empty()
```

### 修改后（mistake-analyzer/src/main_new.py）

```python
import requests

WORKER_API_URL = os.environ.get('WORKER_API_URL', 'http://localhost:8000')

def main(context):
    # 只负责入队
    task_payload = {
        'task_type': 'mistake_analyzer',
        'task_data': {'record_data': record_data},
        'priority': 5
    }
    
    response = requests.post(
        f"{WORKER_API_URL}/tasks/enqueue",
        json=task_payload,
        timeout=5
    )
    
    # 立即返回，不等待处理完成
    return context.res.empty()
```

**环境变量配置：**

在 Appwrite Function 中添加：
```
WORKER_API_URL=http://your-worker-host:8000
```

## 部署建议

### 开发环境

- 使用内存队列
- 单个 Worker 实例
- 并发数：10-50

### 生产环境

- 使用 Redis 队列（未来）
- 多个 Worker 实例
- 并发数：100-1000
- 配置负载均衡
- 配置监控和日志

### Docker 部署（示例）

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

```bash
docker build -t sureup-worker .
docker run -d -p 8000:8000 --env-file .env sureup-worker
```

## 监控和日志

### 日志位置

- 控制台输出：实时日志
- 文件日志：`logs/worker_{time}.log`
- 日志轮转：100MB
- 保留期：30 天

### 监控指标

- 队列长度（pending）
- 处理中任务数（processing）
- 完成任务数（completed）
- 失败任务数（failed）
- Worker 并发数
- 任务平均处理时间

## 故障排查

### 1. Worker 无法启动

检查：
- 环境变量是否正确
- 端口是否被占用
- 依赖是否安装完整

### 2. 任务处理失败

检查：
- Worker 类型是否注册
- 任务数据格式是否正确
- Appwrite API Key 权限
- LLM API Key 是否有效

### 3. 任务处理超时

调整：
- `WORKER_TIMEOUT` 环境变量
- 增加 worker 并发数
- 检查 LLM 响应时间

### 4. 内存占用过高

- 减少并发数
- 切换到 Redis 队列
- 增加任务完成后的清理

## 性能测试

### 压力测试

```bash
# 使用 Apache Bench
ab -n 1000 -c 10 -T 'application/json' \
  -p task.json \
  http://localhost:8000/tasks/enqueue
```

### 预期性能

- 入队速度：> 1000 req/s
- 并发处理：100-1000 任务
- 单个错题分析：20-40 秒（取决于 LLM）

## 未来改进

- [ ] Redis 队列实现
- [ ] 任务重试机制
- [ ] 任务优先级动态调整
- [ ] 分布式 Worker 支持
- [ ] Prometheus 监控集成
- [ ] 任务执行历史持久化
- [ ] WebSocket 实时状态推送
- [ ] Worker 自动扩缩容

## 许可证

MIT License

