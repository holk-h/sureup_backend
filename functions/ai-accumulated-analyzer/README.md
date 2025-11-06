# AI 积累错题分析 Function

## 功能说明

触发积累错题分析任务。

## 请求格式

```json
{
  "userId": "user123"
}
```

## 响应格式

```json
{
  "success": true,
  "data": {
    "analysisId": "analysis123",
    "status": "pending",
    "mistakeCount": 15,
    "daysSinceLastReview": 3,
    "message": "分析任务已创建，请订阅更新"
  }
}
```

## 工作流程

1. 接收用户请求
2. 检查是否有进行中的分析任务
3. 计算积累错题数（查询 `accumulatedAnalyzedAt IS NULL` 的错题）
4. 计算距上次复盘天数
5. 创建分析记录（status: pending）
6. 触发 Worker 任务
7. 返回分析记录 ID

## 未分析错题的识别

系统通过 `mistake_records` 表中的 `accumulatedAnalyzedAt` 字段来追踪哪些错题已被纳入积累分析：

- `accumulatedAnalyzedAt IS NULL`：未被分析的新错题
- `accumulatedAnalyzedAt NOT NULL`：已被分析过的错题

当 Worker 完成分析后，会自动更新所有分析过的错题的 `accumulatedAnalyzedAt` 字段为当前时间。

## AI 分析内容

Worker 会向 LLM 提供完整的学习数据（充分利用长上下文能力），并使用**流式输出**：

### 流式输出特性

- 🚀 **实时生成**：使用火山引擎 ARK SDK 的原生流式 API（`stream=True`）
- ⏱️ **限频更新**：每 0.5 秒更新一次数据库，平衡性能和体验
- 📡 **实时推送**：前端通过 Appwrite Realtime 订阅，实时看到内容生成
- 🔄 **自动管理**：使用 `with` 语句管理连接生命周期

### 输入信息

1. **统计数据**：
   - 错题总数
   - 完整的学科分布（所有学科）
   - 完整的错因分布（所有错因类型）

2. **所有错题的详细信息**（不限制数量）：
   - 学科
   - 错因
   - 用户完整备注（不截断）
   - 是否标记为重要

### 输出内容

基于完整的数据，LLM 将**流式生成深度学习指导报告**：

#### 📊 学习现状洞察
- **主要学习盲区**：薄弱学科/知识点及根本原因
- **突出的问题模式**：错因规律分析
- **学习优势与潜力**：正向反馈和可发挥优势

#### 🎯 学习突破指南
- **核心攻坚点**：最应攻克的2-3个核心问题
- **具体学习方法**：
  - 针对错题涉及的重点知识点：概念梳理、解题思路、易错提醒、练习建议
  - 针对主要错因：根源分析、改进方法、实战技巧
- **学习效率提升**：高效学习方法、知识体系建立、避免重复犯错

#### 💎 知识点点拨与技巧
- **重点知识点解析**（基于错题）：本质理解、知识联系、记忆技巧、题型识别
- **学科通用技巧**：答题技巧、检验方法、时间分配、提分关键点

#### 💪 成长寄语
温暖有力的鼓励和方向指引

### 内容特点

- 🎓 **专业深度**：不仅分析问题，更教授知识点和解题技巧
- ✨ **具体可操作**：详细的学习指导，不泛泛而谈
- ❤️ **有温度**：像导师一样既专业又温暖
- 🎯 **真正实用**：学生看完能知道怎么学、怎么做题
- 📊 **数据驱动**：基于所有错题和统计信息
- 🚀 **不限长度**：越详细越好，确保实质收获（max_tokens: 30000）
- 💡 **点拨技巧**：提供知识点本质理解和答题技巧

## 环境变量

```bash
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main

# Worker API 配置
WORKER_API_URL=http://worker:8000
```

## 部署

```bash
# 在 backend/functions 目录下
appwrite deploy function ai-accumulated-analyzer
```

## 测试

```bash
curl -X POST https://your-domain/v1/functions/ai-accumulated-analyzer/executions \
  -H "Content-Type: application/json" \
  -H "X-Appwrite-Project: your_project_id" \
  -H "X-Appwrite-Key: your_api_key" \
  -d '{"userId": "user123"}'
```

