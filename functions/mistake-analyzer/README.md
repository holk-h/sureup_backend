# 错题分析器 (Mistake Analyzer) - Task Queue 版本

错题分析器是一个 **Event Trigger Function**，监听错题记录的创建和更新事件，将分析任务入队到 Worker 系统。

## 架构改进

### 旧架构的问题

- ❌ Appwrite Function 串行执行（只有 1 个 worker 容器）
- ❌ 不支持并发，多个任务会排队等待
- ❌ LLM 调用耗时长（20-40秒），阻塞后续任务
- ❌ 超时限制（60秒），处理复杂任务可能失败

### 新架构的优势

- ✅ **支持 1000+ 并发**：Worker 系统可以同时处理大量任务
- ✅ **立即返回**：Function 只负责入队，不阻塞
- ✅ **解耦设计**：分析逻辑在 Worker 中独立运行
- ✅ **更好的扩展性**：可以轻松添加更多 Worker 类型

## 工作流程

```
┌──────────────┐
│  Flutter 端  │
└──────┬───────┘
       │ 1. 上传图片 + 创建 mistake_record
       │    (analysisStatus: "pending")
       ▼
┌──────────────────────────┐
│  Appwrite Database       │
│  (mistake_records)       │
└──────┬───────────────────┘
       │ 2. 触发 CREATE 事件
       ▼
┌──────────────────────────┐
│  mistake-analyzer        │
│  (Appwrite Function)     │
│                          │
│  - 验证任务数据          │
│  - 调用 Worker API 入队  │
│  - 立即返回 ✓            │
└──────┬───────────────────┘
       │ 3. POST /tasks/enqueue
       ▼
┌──────────────────────────┐
│  Worker API (FastAPI)    │
│                          │
│  - 任务入队              │
│  - 返回 task_id          │
└──────┬───────────────────┘
       │ 4. 任务入优先级队列
       ▼
┌──────────────────────────┐
│  Worker 池 (100+ 并发)   │
│                          │
│  - 从队列取任务          │
│  - 执行分析逻辑：        │
│    * 下载图片            │
│    * LLM 视觉分析        │
│    * 创建题目            │
│    * 更新错题记录        │
└──────┬───────────────────┘
       │ 5. 更新数据库
       ▼
┌──────────────────────────┐
│  Appwrite Database       │
│  (analysisStatus:        │
│   "completed"/"failed")  │
└──────┬───────────────────┘
       │ 6. Realtime 推送
       ▼
┌──────────────┐
│  Flutter 端  │
│  显示结果    │
└──────────────┘
```

## 功能概述

这是一个轻量级的触发器函数，**不执行任何分析逻辑**，只负责任务调度。

### 监听事件

- `databases.*.collections.mistake_records.documents.*.create` - 新错题记录创建
- `databases.*.collections.mistake_records.documents.*.update` - 错题记录更新

### 处理逻辑

只处理 `analysisStatus` 为 `pending` 的记录：

1. ✅ 新创建的记录（默认 `pending` 状态）
2. ✅ 用户手动触发重新分析（Flutter 端更新状态为 `pending`）
3. ⏭️ 其他状态（`processing`、`completed`、`failed`）跳过

## 文件结构

```
backend/functions/mistake-analyzer/
├── src/
│   └── main.py           # 唯一的文件，只负责入队
├── requirements.txt      # 只需要 requests
└── README.md             # 本文档
```

**注意**：所有分析逻辑已移至 `backend/worker/workers/mistake_analyzer/`

## 配置

### 环境变量

在 Appwrite Function 配置中添加：

```bash
# Worker API 地址（必需）
WORKER_API_URL=http://your-worker-host:8000

# Worker API 超时时间（可选，默认 5 秒）
WORKER_API_TIMEOUT=5
```

### Function 配置

- **Runtime**: Python 3.9+
- **Specification**: 最小规格即可（0.25 vCPU, 256MB RAM）
- **Timeout**: 15 秒（足够入队操作）
- **Events**: 
  - `databases.*.collections.mistake_records.documents.*.create`
  - `databases.*.collections.mistake_records.documents.*.update`
- **Scopes**: 无需特殊权限（只调用外部 API）

## 依赖

```
requests>=2.31.0
```

仅需要 HTTP 客户端库，无需 Appwrite SDK、LLM 库等。

## 部署

### 1. 确保 Worker 系统已启动

```bash
# 在 backend/worker 目录
python app.py
```

### 2. 更新 Appwrite Function 环境变量

在 Appwrite Console 中配置：
- `WORKER_API_URL`: Worker API 的完整 URL

### 3. 部署 Function

```bash
# 使用 Appwrite CLI
appwrite deploy function

# 或者通过 Appwrite Console 上传代码
```

### 4. 测试

创建一个错题记录：

```dart
// Flutter 端
final record = await databases.createDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: ID.unique(),
  data: {
    'userId': userId,
    'originalImageId': imageId,
    'analysisStatus': 'pending',  // 触发分析
  },
);
```

查看日志：
- Appwrite Function 日志：应该显示 "✅ 任务入队成功"
- Worker 日志：应该显示任务处理过程

## 错误处理

### Function 层面

- Worker API 不可用：记录错误日志，但不阻塞（返回成功）
- 入队超时：记录错误，立即返回
- 任务验证失败：跳过任务

### Worker 层面

- 分析失败：更新 `analysisStatus` 为 `failed`
- 记录详细错误信息到 `analysisError` 字段
- Flutter 端可以根据错误信息提示用户

## 监控

### 查看任务状态

```bash
# 查询任务状态
curl http://worker-host:8000/tasks/{task_id}

# 查看队列统计
curl http://worker-host:8000/queue/stats
```

### 查看日志

1. **Appwrite Function 日志**：Appwrite Console > Functions > mistake-analyzer > Logs
2. **Worker 日志**：Worker 服务器的控制台或日志文件

## 与原版本的差异

| 特性 | 原版本 | 新版本 (Task Queue) |
|------|--------|---------------------|
| **执行方式** | 同步执行分析 | 异步入队 |
| **代码量** | ~260 行 | ~160 行（简化 62%） |
| **依赖** | appwrite, requests | requests |
| **并发能力** | 1 个任务 | 1000+ 任务 |
| **响应时间** | 20-40 秒 | < 1 秒 |
| **超时限制** | 60 秒 | 无限制（Worker 处理） |
| **扩展性** | 受限 | 易于扩展 |

## 与 Worker 系统的关系

- **Function**：轻量级触发器，只负责任务调度
- **Worker**：重量级处理系统，执行实际业务逻辑

详细的 Worker 系统文档请参考：`backend/worker/README.md`

## 故障排查

### 1. 任务没有被处理

**检查项**：
- Worker 系统是否运行：`curl http://worker-host:8000/`
- `WORKER_API_URL` 是否配置正确
- Appwrite Function 日志是否显示入队成功

### 2. Function 执行失败

**检查项**：
- Worker API 地址是否可访问（网络连通性）
- 超时时间是否合理
- Function 日志中的错误信息

### 3. Worker 处理慢

**解决方案**：
- 增加 Worker 并发数：`WORKER_CONCURRENCY=200`
- 检查 LLM API 响应时间
- 监控队列积压情况

## 未来改进

- [ ] 支持任务优先级动态调整
- [ ] 支持任务重试机制（在 Worker 层面）
- [ ] 支持批量任务提交
- [ ] 添加任务取消功能
- [ ] WebSocket 实时状态推送

## 相关文档

- [Worker 系统文档](../../worker/README.md)
- [原 mistake-analyzer 设计文档](https://github.com/your-repo/docs/mistake-analyzer-old.md)

## 许可证

MIT License
