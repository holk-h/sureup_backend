# 积累错题分析 Worker - 快速开始

## 功能概述

这个 Worker 负责分析用户积累的错题，生成学习建议。支持通过 Appwrite Realtime API 进行流式输出。

## 快速测试

### 1. 确保 Worker 正在运行

```bash
cd backend/worker
python run.py
```

### 2. 手动触发任务（测试）

```bash
curl -X POST http://localhost:8000/tasks/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "accumulated_mistakes_analyzer",
    "task_data": {
      "analysis_id": "test_analysis_123",
      "user_id": "test_user_456",
      "mistake_count": 15,
      "days_since_last_review": 3
    },
    "priority": 3
  }'
```

### 3. 查看任务状态

```bash
# 从上一步的响应中获取 task_id
curl http://localhost:8000/tasks/{task_id}
```

### 4. 查看队列统计

```bash
curl http://localhost:8000/queue/stats
```

## 完整流程测试

### 前置条件

1. **数据库已配置**：`accumulated_analyses` 集合已创建
2. **LLM 已配置**：火山引擎 API Key 和 Endpoint ID 已设置
3. **Worker 正在运行**：后台 Worker 服务已启动

### 测试步骤

#### 步骤 1: 创建测试分析记录

使用 Appwrite Console 或 SDK 创建一条测试记录：

```python
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID

client = Client()
client.set_endpoint('https://cloud.appwrite.io/v1')
client.set_project('your_project_id')
client.set_key('your_api_key')

databases = Databases(client)

analysis = databases.create_document(
    database_id='main',
    collection_id='accumulated_analyses',
    document_id=ID.unique(),
    data={
        'userId': 'test_user_456',
        'status': 'pending',
        'mistakeCount': 15,
        'daysSinceLastReview': 3,
        'analysisContent': '',
        'summary': {},
        'mistakeIds': []
    }
)

print(f"分析记录已创建: {analysis['$id']}")
```

#### 步骤 2: 触发 Worker 任务

```bash
curl -X POST http://localhost:8000/tasks/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "accumulated_mistakes_analyzer",
    "task_data": {
      "analysis_id": "创建的分析记录ID",
      "user_id": "test_user_456",
      "mistake_count": 15,
      "days_since_last_review": 3
    },
    "priority": 3
  }'
```

#### 步骤 3: 监控执行

查看 Worker 日志：

```bash
tail -f backend/worker/logs/worker_*.log
```

你应该看到类似的输出：

```
[Worker-0] 开始处理: task_xxx (类型: accumulated_mistakes_analyzer)
开始分析用户 test_user_456 的积累错题，分析ID: analysis_xxx
获取 2025-01-01T00:00:00.000Z 之后的错题
找到 15 道积累错题
开始生成分析内容，使用 LLM
LLM 生成完成，内容长度: 856
更新分析内容，进度: 1/5
更新分析内容，进度: 2/5
...
分析完成: analysis_xxx
✅ [Worker-0] 任务完成: task_xxx
```

#### 步骤 4: 查看结果

在 Appwrite Console 中查看 `accumulated_analyses` 集合的记录，应该看到：

- `status`: `completed`
- `analysisContent`: 生成的分析内容（Markdown 格式）
- `summary`: 分析摘要
- `completedAt`: 完成时间

## 环境变量说明

确保以下环境变量已配置：

```bash
# Appwrite
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main

# LLM (火山引擎)
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=your_endpoint_id
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
VOLC_TEMPERATURE=0.7
VOLC_MAX_TOKENS=2000
```

## 常见问题

### Q: Worker 提示"未注册的任务类型"

**A**: 检查 `backend/worker/app.py` 中是否正确注册了 Worker：

```python
def register_workers():
    task_registry.register('accumulated_mistakes_analyzer', AccumulatedMistakesAnalyzerWorker)
```

### Q: LLM 调用失败

**A**: 检查以下内容：
1. API Key 是否正确
2. Endpoint ID 是否正确
3. 网络是否可以访问火山引擎 API
4. 账户余额是否充足

### Q: 找不到错题记录

**A**: 确保：
1. 用户有错题记录在 `mistake_records` 集合
2. 数据库查询权限正确配置
3. 用户 ID 正确

### Q: Realtime 更新未收到

**A**: 检查：
1. 集合权限配置（需要允许 `any` 更新）
2. 前端是否正确订阅
3. 网络连接是否稳定

## 性能调优

### 调整并发数

在 `backend/worker/config.py` 或环境变量中：

```bash
WORKER_CONCURRENCY=8  # 默认 4
```

### 调整 LLM 参数

```bash
VOLC_TEMPERATURE=0.7   # 创造性 (0-1)
VOLC_MAX_TOKENS=2000   # 最大生成长度
```

### 调整流式输出延迟

在 `worker.py` 的 `_stream_content_to_database` 方法中：

```python
await asyncio.sleep(0.3)  # 调整延迟时间
```

## 监控和日志

### 查看 Worker 状态

```bash
curl http://localhost:8000/
```

### 查看队列统计

```bash
curl http://localhost:8000/queue/stats
```

输出示例：

```json
{
  "pending_count": 2,
  "processing_count": 1,
  "completed_count": 45,
  "failed_count": 3
}
```

### 查看日志

```bash
# 实时查看
tail -f backend/worker/logs/worker_*.log

# 过滤特定任务
grep "accumulated_mistakes_analyzer" backend/worker/logs/worker_*.log
```

## 下一步

1. 阅读 [ACCUMULATED_ANALYSIS_SETUP.md](../../ACCUMULATED_ANALYSIS_SETUP.md) 了解完整设置
2. 在前端测试流式输出效果
3. 根据实际使用情况调整 Prompt 和参数
4. 配置生产环境的消息队列（Redis）

