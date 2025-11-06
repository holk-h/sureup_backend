# 积累错题分析 Worker

## 功能说明

分析用户积累的错题，输出学习模式分析和个性化建议。支持通过 Appwrite Realtime API 进行流式输出。

## 数据库设计

### accumulated_analyses 集合

用于存储分析记录和流式内容。

```json
{
  "$id": "unique_id",
  "userId": "user123",
  "status": "pending|processing|completed|failed",
  "mistakeCount": 15,
  "daysSinceLastReview": 3,
  "analysisContent": "流式生成的分析内容（Markdown格式）",
  "summary": {
    "weakPoints": 5,
    "suggestedTime": 30,
    "topSubject": "数学",
    "topReason": "概念理解不清"
  },
  "mistakeIds": ["mistake1", "mistake2", ...],
  "startedAt": "2025-01-01T00:00:00.000Z",
  "completedAt": "2025-01-01T00:05:00.000Z",
  "$createdAt": "2025-01-01T00:00:00.000Z",
  "$updatedAt": "2025-01-01T00:05:00.000Z"
}
```

**字段说明**：
- `userId`: 用户ID
- `status`: 分析状态
  - `pending`: 等待分析
  - `processing`: 分析中
  - `completed`: 分析完成
  - `failed`: 分析失败
- `mistakeCount`: 分析的错题数量
- `daysSinceLastReview`: 距上次分析的天数
- `analysisContent`: 流式生成的分析内容（Markdown格式）
- `summary`: 分析摘要统计
- `mistakeIds`: 本次分析包含的错题ID列表
- `startedAt`: 分析开始时间
- `completedAt`: 分析完成时间

## 工作流程

1. **触发**：用户点击"积累错题分析"
2. **创建记录**：Frontend/Function 创建 `accumulated_analyses` 记录（status: pending）
3. **订阅更新**：Frontend 订阅该记录的 Realtime 更新
4. **Worker 处理**：
   - 获取用户积累的错题（自上次分析以来）
   - 调用 LLM 生成分析（启用流式输出）
   - 每接收到一段内容，更新数据库记录
   - Frontend 通过 Realtime 实时收到更新并展示
5. **完成**：Worker 标记状态为 completed

## 流式输出实现

### 技术架构

使用火山引擎 ARK SDK 的真实流式 API + Appwrite Realtime：

```
Frontend (Realtime 订阅)
    ↓
accumulated_analyses 记录
    ↑ (每 0.5 秒更新)
Worker (处理流式响应)
    ↑ (stream=True)
火山引擎 LLM API
```

### 实现细节

**1. Backend (Worker) - 流式接收 LLM 响应**:

```python
# 使用流式 API
stream_response = await self.llm_provider.chat(
    prompt=prompt,
    temperature=0.7,
    max_tokens=30000,
    stream=True  # 启用流式输出
)

# 处理流式响应，每 0.5 秒更新一次数据库
accumulated_content = ''
last_update_time = time.time()
update_interval = 0.5  # 限制更新频率

with stream_response:
    for chunk in stream_response:
        if chunk.choices[0].delta.content is not None:
            accumulated_content += chunk.choices[0].delta.content
            
            # 每 0.5 秒更新一次数据库
            if time.time() - last_update_time >= update_interval:
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id='accumulated_analyses',
                    document_id=analysis_id,
                    data={'analysisContent': accumulated_content}
                )
                last_update_time = time.time()
```

**2. Frontend (Flutter) - 订阅实时更新**:

```dart
// 订阅文档更新
final subscription = realtime.subscribe([
  'databases.$databaseId.collections.accumulated_analyses.documents.$analysisId'
]);

subscription.stream.listen((response) {
  if (response.events.contains('databases.*.collections.*.documents.*.update')) {
    final content = response.payload['analysisContent'];
    setState(() => _generatedText = content);
  }
});
```

### 优势

- ✅ **真实流式**：使用 LLM API 的原生 stream 功能
- ✅ **性能优化**：0.5 秒更新频率，避免过于频繁的数据库写入
- ✅ **用户体验**：前端通过 Realtime 实时看到内容逐步生成
- ✅ **连接管理**：使用 `with` 语句自动管理连接生命周期

## LLM Prompt 设计

```
你是一个资深教育专家，擅长分析学生的学习模式。

学生信息：
- 积累错题数：{mistake_count} 道
- 距上次复盘：{days} 天
- 学科分布：{subject_distribution}
- 错因分布：{reason_distribution}
- 薄弱知识点：{weak_points}

请生成一份温和、正向、鼓励的学习分析报告（Markdown格式），包含：

1. 📊 学习现状分析
   - 整体情况概述
   - 主要问题识别
   
2. 💡 针对性建议
   - 优先攻克的问题
   - 具体学习方法
   - 时间规划建议
   
3. 💪 鼓励与总结
   - 正向鼓励
   - 行动建议

要求：
- 语气温和、正向、鼓励
- 分析具体、有数据支撑
- 建议可操作、接地气
- 使用 Markdown 格式
- 适当使用 emoji
```

## 错误处理

- LLM 调用失败：重试 3 次，失败后标记状态为 failed
- 数据库更新失败：记录日志，不中断流式输出
- 超时处理：设置 120 秒超时

