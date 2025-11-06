# 每日任务调度器 (Daily Task Scheduler)

## 概述

这是一个轻量级的 Appwrite Function，负责触发每日任务生成。

每天凌晨 2:00 自动执行（通过 cron schedule 配置）。

## 架构

```
Appwrite Function (触发器)
    ↓ HTTP 请求
Worker API (任务执行器)
    ↓ 生成任务
数据库 (保存任务)
```

## 配置

### 环境变量

在 Appwrite Console 中为该 Function 配置以下环境变量：

```bash
WORKER_API_URL=http://localhost:8000  # Worker API 地址
```

### Cron Schedule

已在 `appwrite.config.json` 中配置：

```json
"schedule": "0 18 * * *"  // 每天 UTC 18:00 执行 = 北京时间凌晨 2:00
```

**⚠️ 重要：时区说明**
- Appwrite 的 cron schedule 使用 **UTC 时区**
- 北京时间（UTC+8）= UTC 时间 - 8 小时
- 要在北京时间凌晨 2:00 触发 → 设置为 UTC 18:00（前一天）
- 公式：`北京时间 - 8 = UTC 时间`

## 手动触发

如果需要手动触发任务生成，可以调用该 Function：

```bash
# 使用 Appwrite CLI
appwrite functions execute --functionId daily-task-scheduler

# 或使用 HTTP 请求
curl -X POST \
  https://api.delvetech.cn/v1/functions/daily-task-scheduler/executions \
  -H "Content-Type: application/json" \
  -H "X-Appwrite-Project: YOUR_PROJECT_ID" \
  -H "X-Appwrite-Key: YOUR_API_KEY"
```

## 返回值

成功时：
```json
{
  "success": true,
  "message": "每日任务生成已触发",
  "task_id": "task-uuid-123",
  "timestamp": "2025-11-05T02:00:00"
}
```

失败时：
```json
{
  "success": false,
  "error": "错误信息"
}
```

## 注意事项

1. 确保 Worker API 服务已启动并可访问
2. 该 Function 只负责触发，实际任务生成由 Worker 执行
3. Worker 会异步处理，可能需要几分钟完成所有用户的任务生成

