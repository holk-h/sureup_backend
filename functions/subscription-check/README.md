# 订阅状态检查定时任务

## 功能

每天自动检查所有订阅状态，更新过期订阅。

## 运行时间

- Cron 表达式：`0 2 * * *`
- 每天凌晨 2:00（UTC 时区）运行

## 工作流程

1. 扫描所有 `status = 'active'` 的订阅记录
2. 检查 `expiryDate` 是否已过期
3. 如果过期：
   - 更新 `subscriptions` 表：`status = 'expired'`
   - 检查用户是否有其他活跃订阅
   - 如果没有：更新 `profiles` 表：`subscriptionStatus = 'expired'`
4. 输出统计信息

## 环境变量

- `APPWRITE_ENDPOINT`: Appwrite API 端点
- `APPWRITE_PROJECT_ID`: 项目 ID
- `APPWRITE_API_KEY`: API Key
- `APPWRITE_DATABASE_ID`: 数据库 ID（默认: main）

## 日志输出

```
[订阅检查] 开始检查订阅状态
用户 xxx 订阅已过期
[订阅检查] 完成: 检查 50 个订阅, 发现 5 个过期, 更新 5 个用户档案
```

## 注意事项

- 定时任务超时设置为 300 秒（5 分钟）
- 分批处理，每次 100 条记录
- 考虑到用户可能有多个订阅，只在所有订阅都过期时才更新用户状态

