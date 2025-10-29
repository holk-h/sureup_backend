# 稳了！Functions 模块

## 架构设计

### 完全独立的Functions

每个Function都是完全独立的，包含自己需要的所有代码：
- ✅ 无外部依赖
- ✅ 独立部署
- ✅ 易于维护
- ✅ 避免耦合

### 三层架构

- **L1 (原子层)**: 基础CRUD操作
- **L2 (功能层)**: AI功能和业务逻辑  
- **L3 (编排层)**: 复杂工作流和定时任务

## 目录结构

```
functions/
├── question-manager/          # L1: 题目管理
│   ├── src/
│   │   ├── main.py           # 主函数
│   │   └── utils.py          # 工具函数（独立）
│   └── requirements.txt
│
├── knowledge-point-manager/   # L1: 知识点管理
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── mistake-recorder/          # L1: 错题记录
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── stats-updater/            # L1: 统计更新
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── ai-knowledge-analyzer/    # L2: AI知识点分析
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── ai-question-generator/    # L2: AI智能出题
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── ai-mistake-analyzer/      # L2: AI错题分析
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
├── ai-session-summarizer/    # L2: AI练习总结
│   ├── src/
│   │   ├── main.py
│   │   └── utils.py
│   └── requirements.txt
│
└── daily-task-scheduler/     # L3: 每日任务调度
    ├── src/
    │   ├── main.py
    │   └── utils.py
    └── requirements.txt
```

## 环境变量配置

每个function需要在Appwrite Console中配置：

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

## MVP阶段功能清单

### ✅ L1层（4个）
- [x] question-manager - 题目CRUD
- [x] knowledge-point-manager - 知识点CRUD  
- [x] mistake-recorder - 错题记录
- [x] stats-updater - 统计自动更新

### ✅ L2层（4个）
- [x] ai-knowledge-analyzer - AI分析知识点
- [x] ai-question-generator - AI智能出题
- [x] ai-mistake-analyzer - AI错题深度分析
- [x] ai-session-summarizer - AI练习总结

### ✅ L3层（1个）
- [x] daily-task-scheduler - 每日任务生成

### 📅 预留（后续）
- [ ] weekly-report-scheduler - 周报生成
- [ ] ai-weekly-reporter - AI周报分析
- [ ] smart-review-orchestrator - 智能复习编排
- [ ] ocr-recognizer - OCR图片识别

## 部署方式

### 1. 使用Appwrite Console

1. 登录Appwrite Console
2. Functions → Create Function
3. 选择Runtime: Python 3.12
4. 上传代码或连接Git
5. 配置环境变量
6. 配置触发器（如需要）
7. 部署

### 2. 使用Appwrite CLI

```bash
# 初始化
appwrite init function

# 部署单个
appwrite deploy function --functionId=question-manager

# 查看日志
appwrite functions list-executions --functionId=question-manager
```

## 调用示例

### 1. question-manager

```bash
curl -X POST https://cloud.appwrite.io/v1/functions/[FUNCTION_ID]/executions \
  -H "X-Appwrite-Project: [PROJECT_ID]" \
  -H "X-Appwrite-Key: [API_KEY]" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create",
    "data": {
      "subject": "math",
      "knowledgePointId": "kp_123",
      "type": "choice",
      "difficulty": 3,
      "content": "题目内容",
      "answer": "A",
      "explanation": "解析"
    }
  }'
```

### 2. ai-knowledge-analyzer

```bash
curl -X POST https://cloud.appwrite.io/v1/functions/[FUNCTION_ID]/executions \
  -H "X-Appwrite-Project: [PROJECT_ID]" \
  -H "X-Appwrite-Key: [API_KEY]" \
  -H "Content-Type: application/json" \
  -d '{
    "questionText": "函数y=x²-2x+1的递减区间是？",
    "subject": "math",
    "userId": "user_123"
  }'
```

### 3. ai-question-generator

```bash
curl -X POST https://cloud.appwrite.io/v1/functions/[FUNCTION_ID]/executions \
  -H "X-Appwrite-Project: [PROJECT_ID]" \
  -H "X-Appwrite-Key: [API_KEY]" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "variant",
    "sourceQuestionId": "q_123",
    "count": 3
  }'
```

## 业务流程

### 录入错题
```
1. ai-knowledge-analyzer (分析知识点)
   → 返回: knowledgePointId
2. question-manager (创建题目)
   → 返回: questionId
3. mistake-recorder (创建错题记录)
   → 触发: stats-updater
```

### 智能练习
```
1. ai-question-generator (生成练习题)
2. 用户答题
3. ai-session-summarizer (生成总结)
   → 触发: stats-updater
```

### 每日任务
```
定时触发 (凌晨2:00)
   ↓
daily-task-scheduler
   ↓
创建 daily_tasks 记录
```

## 代码规范

### 统一的响应格式

```python
# 成功
{
  "success": True,
  "message": "Success message",
  "data": {...}
}

# 失败
{
  "success": False,
  "message": "Error message",
  "code": 400,
  "details": "..."  # 可选
}
```

### 统一的入口函数

```python
def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        
        # 处理业务逻辑
        result = process(body)
        
        # 返回响应
        return res.json(success_response(result))
        
    except Exception as e:
        return res.json(error_response(str(e), 500))
```

## 监控和调试

### 查看执行日志
- Appwrite Console → Functions → Executions
- 每次执行的详细日志、耗时、状态

### 性能监控
- 执行时间
- 成功率
- AI Token消耗

## 注意事项

1. **独立性**: 每个Function完全独立，不依赖其他Function的代码
2. **幂等性**: Function应该是幂等的，相同输入产生相同输出
3. **超时**: Appwrite Function默认15秒超时，AI调用注意控制时间
4. **日志**: 使用print()输出日志，会在Console中显示
5. **异常处理**: 所有异常都应该被捕获并返回友好的错误信息

---

**版本**: MVP v1.0  
**更新时间**: 2025-10-29  
**架构**: 独立Functions，无共享依赖
