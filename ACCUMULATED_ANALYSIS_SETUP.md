# 积累错题分析功能设置指南

## 概述

积累错题分析功能使用以下组件：
- **Appwrite Function**: `ai-accumulated-analyzer` - 触发分析任务
- **Worker**: `accumulated_mistakes_analyzer` - 执行分析逻辑
- **Realtime API**: 实现流式输出
- **Frontend Service**: `AccumulatedAnalysisService` - 处理前端交互

## 1. 数据库配置

### 创建 accumulated_analyses 集合

在 Appwrite Console 中创建集合：

**集合信息**：
- Collection ID: `accumulated_analyses`
- Collection Name: Accumulated Analyses

**属性配置**：

| 属性名 | 类型 | 大小 | 必填 | 数组 | 说明 |
|--------|------|------|------|------|------|
| userId | string | 36 | ✓ | ✗ | 用户ID |
| status | string | 20 | ✓ | ✗ | 分析状态 (pending/processing/completed/failed) |
| mistakeCount | integer | - | ✓ | ✗ | 分析的错题数量 |
| daysSinceLastReview | integer | - | ✓ | ✗ | 距上次分析天数 |
| analysisContent | string | 10000 | ✗ | ✗ | 分析内容（Markdown） |
| summary | string | 2000 | ✗ | ✗ | 分析摘要（JSON） |
| mistakeIds | string | 100 | ✗ | ✓ | 错题ID列表 |
| startedAt | datetime | - | ✗ | ✗ | 开始时间 |
| completedAt | datetime | - | ✗ | ✗ | 完成时间 |

**索引配置**：
1. userId (ASC) - 查询用户的分析记录
2. status (ASC) - 查询特定状态的记录
3. userId + status (ASC + ASC) - 组合查询

**权限配置**：
- Create: `users` (任何已登录用户)
- Read: `user:[userId]` (只能读取自己的记录)
- Update: `any` (Worker 需要更新权限)
- Delete: `user:[userId]`

## 2. Function 配置

### 创建 ai-accumulated-analyzer Function

在 Appwrite Console 中创建 Function：

**基本信息**：
- Function ID: `ai-accumulated-analyzer`
- Name: AI Accumulated Analyzer
- Runtime: Python 3.11
- Entrypoint: `src/main.py`

**环境变量**：
```bash
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main
WORKER_API_URL=http://worker:8000
```

**触发器**：
- 手动触发（通过 SDK 调用）

**超时**：
- 15 秒（Function 只负责创建记录和触发 Worker）

### 部署 Function

```bash
cd backend/functions/ai-accumulated-analyzer
appwrite deploy function
```

## 3. Worker 配置

Worker 已在 `backend/worker/` 中配置。

### 环境变量

确保 Worker 的 `.env` 包含：

```bash
# Appwrite 配置
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main

# 火山引擎 LLM 配置
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=your_endpoint_id
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
VOLC_TEMPERATURE=0.7
VOLC_MAX_TOKENS=2000

# Worker 配置
API_HOST=0.0.0.0
API_PORT=8000
WORKER_CONCURRENCY=4
QUEUE_TYPE=memory
```

### 启动 Worker

```bash
cd backend/worker
python run.py
```

### 验证 Worker

```bash
# 检查 Worker 状态
curl http://localhost:8000/

# 查看注册的 Worker 类型
curl http://localhost:8000/workers/types
```

应该看到输出包含：
```json
{
  "worker_types": [
    "mistake_analyzer",
    "daily_task_generator",
    "accumulated_mistakes_analyzer"
  ],
  "concurrency": 4
}
```

## 4. 前端配置

### ApiConfig 更新

`frontend/lib/config/api_config.dart` 已添加：

```dart
static const String accumulatedAnalysesCollectionId = 'accumulated_analyses';
static const String functionAccumulatedAnalyzer = 'ai-accumulated-analyzer';
```

### Service 初始化

在使用前需要初始化 Service：

```dart
final analysisService = AccumulatedAnalysisService();
analysisService.initialize(client);
```

## 5. 测试流程

### 5.1 测试 Function

```bash
# 使用 Appwrite CLI
appwrite functions createExecution \
  --functionId ai-accumulated-analyzer \
  --body '{"userId": "test_user_id"}'
```

### 5.2 测试完整流程

1. 在 App 中导航到"分析"页面
2. 点击"积累错题分析"卡片
3. 点击"生成学习建议"按钮
4. 观察流式输出效果

### 5.3 调试

**查看 Worker 日志**：
```bash
cd backend/worker
tail -f logs/worker_*.log
```

**查看 Function 日志**：
在 Appwrite Console 的 Functions 页面查看执行日志。

**查看数据库记录**：
在 Appwrite Console 的 Databases 页面查看 `accumulated_analyses` 集合。

## 6. 流式输出原理

### Backend 侧

Worker 将内容分段更新到数据库：

```python
# 每次更新一段内容
databases.update_document(
    database_id='main',
    collection_id='accumulated_analyses',
    document_id=analysis_id,
    data={'analysisContent': accumulated_content}
)
```

### Frontend 侧

订阅 Realtime 更新：

```dart
// 订阅文档更新
final subscription = realtime.subscribe([
  'databases.main.collections.accumulated_analyses.documents.$analysisId'
]);

// 监听更新
subscription.stream.listen((response) {
  final content = response.payload['analysisContent'];
  setState(() => _generatedText = content);
});
```

## 7. 故障排查

### Function 调用失败

1. 检查 Function 是否部署成功
2. 检查环境变量是否正确配置
3. 查看 Function 执行日志

### Worker 未执行

1. 检查 Worker 是否正在运行
2. 检查 Worker 日志是否有错误
3. 验证 WORKER_API_URL 是否正确

### Realtime 更新未收到

1. 检查 Realtime 订阅是否成功
2. 检查集合权限配置
3. 检查网络连接

### LLM 调用失败

1. 检查火山引擎 API Key 是否有效
2. 检查 Endpoint ID 是否正确
3. 查看 Worker 日志中的错误信息

## 8. 性能优化

### 并发控制

Worker 支持并发处理多个分析任务：

```bash
# 调整并发数
WORKER_CONCURRENCY=8
```

### LLM 参数调优

```bash
# 调整温度（创造性）
VOLC_TEMPERATURE=0.7

# 调整最大 token 数
VOLC_MAX_TOKENS=2000
```

### 数据库索引

确保在高频查询字段上创建索引：
- userId + status
- $createdAt (降序)

## 9. 安全考虑

### API Key 保护

- 永远不要在前端暴露 API Key
- 使用环境变量管理密钥
- 定期轮换 API Key

### 权限控制

- 用户只能读取自己的分析记录
- Worker 使用单独的 API Key
- Function 使用受限权限的 API Key

### 速率限制

考虑实现速率限制：
- 每个用户每天最多 N 次分析
- 使用 Appwrite 的 Rate Limits 功能

## 10. 未来改进

### 可能的优化方向

1. **消息队列**：使用 Redis 或 RabbitMQ 替代内存队列
2. **缓存**：缓存最近的分析结果
3. **增量更新**：只分析新增的错题
4. **模型微调**：使用专门的教育模型
5. **多语言支持**：支持英文等其他语言

### 功能扩展

1. **历史对比**：对比多次分析结果
2. **个性化提示**：根据用户画像调整分析
3. **导出功能**：导出分析报告为 PDF
4. **分享功能**：分享分析结果给老师/家长

