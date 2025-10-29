# Functions 快速开始

## 1. 环境准备

### 安装Appwrite CLI

```bash
npm install -g appwrite-cli
```

### 登录Appwrite

```bash
appwrite login
```

### 配置项目

```bash
cd backend/functions
appwrite init project
```

## 2. 配置环境变量

每个函数需要在Appwrite Console中配置环境变量：

### 所有函数通用

```bash
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=<your-project-id>
APPWRITE_API_KEY=<your-api-key>
APPWRITE_DATABASE_ID=main
```

### AI功能函数（L2层）额外需要

```bash
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o-mini
```

## 3. 部署函数

### 部署单个函数

```bash
# L1层函数
appwrite deploy function --functionId=question-manager
appwrite deploy function --functionId=knowledge-point-manager
appwrite deploy function --functionId=mistake-recorder
appwrite deploy function --functionId=stats-updater

# L2层函数
appwrite deploy function --functionId=ai-knowledge-analyzer
appwrite deploy function --functionId=ai-question-generator
appwrite deploy function --functionId=ai-mistake-analyzer
appwrite deploy function --functionId=ai-session-summarizer

# L3层函数
appwrite deploy function --functionId=daily-task-scheduler
```

### 或使用批量部署

```bash
appwrite deploy
```

## 4. 测试函数

### 通过Console测试

1. 打开Appwrite Console
2. 进入Functions页面
3. 选择要测试的函数
4. 点击"Execute"
5. 输入测试数据

### 通过API测试

```bash
curl -X POST https://cloud.appwrite.io/v1/functions/[FUNCTION_ID]/executions \
  -H "X-Appwrite-Project: [PROJECT_ID]" \
  -H "X-Appwrite-Key: [API_KEY]" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create",
    "data": {
      "subject": "math",
      "content": "test question"
    }
  }'
```

## 5. 配置触发器

### stats-updater（数据库事件触发）

在Appwrite Console中配置：

- Event: `databases.*.collections.mistake_records.documents.*.create`
- Event: `databases.*.collections.practice_answers.documents.*.create`
- Event: `databases.*.collections.mistake_records.documents.*.update`

### daily-task-scheduler（定时触发）

在Appwrite Console中配置：

- Schedule: `0 2 * * *` (每天凌晨2点)
- 或使用cron表达式

## 6. 监控和调试

### 查看日志

```bash
appwrite functions get-execution \
  --functionId=[FUNCTION_ID] \
  --executionId=[EXECUTION_ID]
```

### 在Console中查看

1. Functions → 选择函数
2. Executions 标签页
3. 查看每次执行的详情和日志

## 7. 开发建议

### 本地开发

1. 每个函数的`src/main.py`中添加：

```python
if __name__ == "__main__":
    # 本地测试代码
    class MockContext:
        class Req:
            body = '{"action": "test"}'
        req = Req()
        class Res:
            def json(self, data):
                print(data)
                return data
        res = Res()
    
    main(MockContext())
```

2. 运行测试：

```bash
cd functions/question-manager
python src/main.py
```

### Shared代码更新

如果修改了`shared/`目录下的代码，需要重新部署所有依赖它的函数。

## 8. 调用顺序（MVP流程）

### 用户录入错题

```
1. ai-knowledge-analyzer (分析知识点)
   ↓
2. question-manager (创建题目)
   ↓
3. knowledge-point-manager (创建/查找知识点)
   ↓
4. mistake-recorder (创建错题记录)
   ↓
5. stats-updater (自动触发，更新统计)
```

### 用户练习

```
1. ai-question-generator (生成练习题)
   ↓
2. 用户答题 (前端)
   ↓
3. ai-session-summarizer (生成总结)
   ↓
4. stats-updater (自动触发)
```

### 每日任务

```
定时触发 (凌晨2点)
   ↓
daily-task-scheduler
   ↓
(可选) ai-question-generator
   ↓
创建 daily_tasks 记录
```

## 9. 故障排查

### 常见问题

**Q: Function执行超时**
- A: 检查AI API响应时间，考虑增加timeout设置

**Q: 权限错误**
- A: 检查API Key权限，确保有database和functions权限

**Q: AI返回格式错误**
- A: 检查prompt，确保AI返回纯JSON格式

**Q: 找不到shared模块**
- A: 确保`sys.path.append('../shared')`在代码开头

## 10. 性能优化建议

- AI调用使用流式响应（后续优化）
- 批量处理数据库操作
- 使用Appwrite缓存
- 合理设置timeout和retry

---

**遇到问题？** 查看函数日志或联系开发团队

