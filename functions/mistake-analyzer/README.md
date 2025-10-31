# 错题分析器 (Mistake Analyzer)

错题分析器是一个 **Event Trigger Function**，监听错题记录的创建和更新事件，自动分析错题并完善记录信息。

## 功能概述

这是一个纯内部触发的函数，不提供 API 接口，完全由数据库事件驱动。

### 监听事件

- `databases.*.collections.mistake_records.documents.*.create` - 新错题记录创建
- `databases.*.collections.mistake_records.documents.*.update` - 错题记录更新

### 处理逻辑

只处理 `analysisStatus` 为 `pending` 的记录：

1. ✅ 新创建的记录（默认 `pending` 状态）
2. ✅ 用户手动触发重新分析（Flutter 端更新状态为 `pending`）
3. ⏭️ 其他状态（`processing`、`completed`、`failed`）跳过

## 工作流程

### 场景 1: 拍照上传错题（新建）

```
1. Flutter 端:
   - 用户拍照 + 裁剪
   - 上传图片到 bucket (origin_question_image)，获得 fileId
   - 创建 mistake_record 文档:
     {
       "userId": "xxx",
       "subject": "math",
       "originalImageIds": [fileId],
       "analysisStatus": "pending"  // 默认值
     }
   - 订阅该文档的 Realtime 更新

2. Appwrite:
   - 触发 CREATE 事件
   - mistake-analyzer 被自动调用

3. mistake-analyzer:
   - 检查 analysisStatus = "pending" ✅
   - 更新状态为 "processing"
   - 下载图片
   - OCR + LLM 分析
   - 创建/匹配模块和知识点
   - 创建题目
   - 更新 mistake_record:
     {
       "questionId": "yyy",
       "moduleIds": [...],
       "knowledgePointIds": [...],
       "errorReason": "conceptError",
       "analysisStatus": "completed",
       "analyzedAt": "2024-01-01T00:00:00Z"
     }

4. Flutter 端:
   - 收到 Realtime 更新通知
   - 显示分析结果
```

### 场景 2: 重新分析（更新）

```
1. Flutter 端:
   - 用户点击"重新分析"按钮
   - 更新 mistake_record:
     {
       "analysisStatus": "pending",
       "analysisError": null
     }
   - 继续订阅 Realtime 更新

2. Appwrite:
   - 触发 UPDATE 事件
   - mistake-analyzer 被自动调用

3. mistake-analyzer:
   - 检查 analysisStatus = "pending" ✅
   - 执行相同的分析流程
   - 更新结果

4. Flutter 端:
   - 收到更新通知
   - 显示新的分析结果
```

### 场景 3: 练习中的错题

```
1. Flutter 端:
   - 用户在练习中答错题目
   - 调用 mistake-recorder 的 createFromQuestion API
   - 创建错题记录（直接关联已有题目，无需分析）

2. 不会触发 mistake-analyzer
   - 因为创建时 analysisStatus 不是 "pending"
   - 或者不包含图片，无需分析
```

## 分析结果

### 成功状态

```json
{
  "analysisStatus": "completed",
  "analyzedAt": "2024-01-01T00:00:00Z",
  "questionId": "question-doc-id",
  "moduleIds": ["module-1", "module-2"],
  "knowledgePointIds": ["kp-1", "kp-2", "kp-3"],
  "errorReason": "conceptError",
  "userAnswer": "A",
  "analysisError": null
}
```

### 失败状态

```json
{
  "analysisStatus": "failed",
  "analysisError": "OCR 识别失败: 图片模糊",
  "analyzedAt": null,
  "questionId": null
}
```

## 状态机

```
pending ──────────> processing ──────────> completed
   ↑                                            |
   |                    ↓                       |
   └──────────────── failed ←──────────────────┘
                       ↓
                  (用户重新分析)
                       ↓
                    pending
```

## 技术实现

### 核心模块

- `main.py` - 事件处理入口
- `image_analyzer.py` - 图片 OCR + LLM 分析
- `question_service.py` - 题目创建/匹配
- `knowledge_point_service.py` - 模块和知识点管理
- `mistake_service.py` - 错题记录服务
- `llm_provider.py` - LLM 接口封装

### 关键函数

#### `process_mistake_analysis(record_data, databases, storage)`

处理错题分析的核心逻辑：

1. 更新状态为 `processing`
2. 下载图片（从 storage bucket）
3. 调用 LLM 分析图片
4. 确保模块存在（公有模块库）
5. 确保知识点存在（用户私有）
6. 创建或查找题目
7. 更新错题记录
8. 更新状态为 `completed` 或 `failed`

### 错误处理

- 所有异常都会捕获
- 失败时更新 `analysisStatus` 为 `failed`
- 记录错误信息到 `analysisError` 字段（限制 1000 字符）
- 不抛出异常（Event Trigger 不需要返回错误响应）

## 配置

### 环境变量

- `APPWRITE_ENDPOINT` - Appwrite API 端点
- `APPWRITE_PROJECT_ID` - 项目 ID
- `APPWRITE_API_KEY` - API 密钥
- `APPWRITE_DATABASE_ID` - 数据库 ID（默认：main）

### Function 配置

- **Runtime**: Python 3.9
- **Specification**: 1 vCPU, 1GB RAM
- **Timeout**: 60 秒
- **Events**: 
  - `databases.*.collections.mistake_records.documents.*.create`
  - `databases.*.collections.mistake_records.documents.*.update`
- **Scopes**: 
  - `databases.read`
  - `databases.write`
  - `files.read`

## 性能优化

### 幂等性

- 检查 `analysisStatus` 确保不重复处理
- `processing` 状态防止并发问题

### 超时处理

- 60 秒超时足够完成大部分分析
- 超时会自动重试（Appwrite 机制）

### 日志

- 记录关键步骤
- 成功/失败都有清晰日志
- 便于调试和监控

## 数据结构

### mistake_records 表字段

```javascript
{
  userId: string,              // 用户ID
  subject: string,             // 学科
  originalImageIds: string[], // 图片 fileId 数组
  
  // 分析状态
  analysisStatus: string,      // pending/processing/completed/failed
  analysisError: string,       // 错误信息（如果失败）
  analyzedAt: datetime,        // 分析完成时间
  
  // 分析结果（完成后填充）
  questionId: string,          // 题目ID
  moduleIds: string[],         // 模块ID数组
  knowledgePointIds: string[], // 知识点ID数组
  errorReason: string,         // 错误原因
  userAnswer: string,          // 用户答案
  note: string,                // 笔记
  
  // 复习相关
  masteryStatus: string,       // 掌握状态
  reviewCount: integer,        // 复习次数
  correctCount: integer,       // 答对次数
  lastReviewAt: datetime,      // 最后复习时间
  masteredAt: datetime         // 掌握时间
}
```

## 与其他函数的关系

- **mistake-recorder**: 提供 `createFromQuestion` API（练习中的错题）
- **stats-updater**: 监听错题记录的创建/更新，更新用户统计
- **knowledge-point-manager**: 提供知识点管理 API

## 调试

### 查看日志

在 Appwrite Console 查看 Function 日志：
- 成功: `✅ 错题分析完成`
- 失败: `❌ 错题分析失败`
- 跳过: `⏭️ 跳过分析`

### 常见问题

1. **分析一直处于 pending 状态**
   - 检查 Function 是否启用
   - 检查事件是否正确配置
   - 查看 Function 日志

2. **分析失败**
   - 查看 `analysisError` 字段
   - 可能原因：图片下载失败、OCR 失败、LLM 调用失败

3. **重复分析**
   - 检查是否有多次更新状态为 `pending`
   - 幂等性检查应该防止重复处理

## 未来优化

- [ ] 支持批量图片分析
- [ ] 优化 OCR 准确率
- [ ] 缓存 LLM 结果
- [ ] 支持更多学科
- [ ] 分析置信度评分

