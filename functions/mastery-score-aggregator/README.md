# 掌握度聚合器 (Mastery Score Aggregator)

## 功能说明

这是一个 Appwrite Trigger Function，监听 `review_states` 表的更新事件，自动计算和同步知识点、模块和学科级别的掌握度。

## 触发时机

- **事件**: 
  - `databases.*.collections.review_states.documents.*.create`
  - `databases.*.collections.review_states.documents.*.update`
- **场景**: 
  - 用户首次开始复习某个知识点（创建 review_state 记录）
  - 用户完成每日任务后，前端更新 `review_states` 表的 `masteryScore` 字段

## 工作流程

```
用户完成每日任务
  ↓
前端更新 review_states.masteryScore
  ↓
触发此 Function
  ↓
1. 更新 user_knowledge_points.masteryScore (同步单个知识点)
  ↓
2. 查询该用户该学科的所有知识点
  ↓
3. 聚合计算学科平均掌握度
  ↓
4. 更新 profiles.subjectMasteryScores (JSON格式)
```

## 数据结构

### user_knowledge_points.masteryScore
- 类型: `integer (0-100)`
- 来源: 从 `review_states.masteryScore` 同步
- 用途: 单个知识点的掌握度

### profiles.subjectMasteryScores
- 类型: `string` (JSON格式)
- 格式: `{"数学": 75, "物理": 60, "化学": 80}`
- 用途: 学科级别的平均掌握度

## 计算逻辑

### 学科掌握度计算
```python
学科平均掌握度 = sum(该学科所有知识点的 masteryScore) / count(有 review_states 的知识点)
```

**注意**：
- 只统计有 `review_states` 记录的知识点
- 如果知识点还没开始复习（没有 review_states），不计入平均值

## 部署

```bash
# 部署到 Appwrite
appwrite deploy function

# 查看日志
appwrite logs --function mastery-score-aggregator
```

## 环境变量

Function 自动获取以下环境变量：
- `APPWRITE_FUNCTION_API_ENDPOINT`: Appwrite API 地址
- `APPWRITE_FUNCTION_PROJECT_ID`: 项目 ID
- `APPWRITE_API_KEY`: API 密钥（从 scopes 继承）

## 性能优化

如果用户的知识点数量很多（100+），可以考虑：
1. 使用缓存避免频繁计算
2. 异步处理，不阻塞主流程
3. 批量查询优化

## 测试

手动触发测试：
```python
# 模拟更新 review_states
# Function 会自动触发
```

