# 错题处理新工作流程

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flutter 前端                              │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ├─ 场景1: 拍照错题
                               ├─ 场景2: 练习错题
                               └─ 场景3: 重新分析
                               │
                ┌──────────────┴──────────────┐
                │                              │
                ▼                              ▼
    ┌──────────────────────┐      ┌──────────────────────┐
    │   Appwrite Storage   │      │   Appwrite Database  │
    │  (origin_question_   │      │   (mistake_records)  │
    │       _image)        │      │                      │
    └──────────────────────┘      └──────────────────────┘
                                              │
                                              │ Event Trigger
                                              │ (create/update)
                                              ▼
                                  ┌──────────────────────┐
                                  │  mistake-analyzer    │
                                  │   (Event Function)   │
                                  └──────────────────────┘
                                              │
                                              ▼
                                  分析完成 → 更新 mistake_record
                                              │
                                              ▼
                                    Realtime → Flutter 显示结果
```

## 场景 1: 拍照错题（新建）

### Flutter 端流程

```dart
// 1. 拍照 + 裁剪
final File croppedImage = await cropImage(photoFile);

// 2. 上传到 bucket
final file = await storage.createFile(
  bucketId: 'origin_question_image',
  fileId: ID.unique(),
  file: InputFile.fromPath(path: croppedImage.path),
);

// 3. 创建错题记录（分析状态为 pending）
final mistakeRecord = await databases.createDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: ID.unique(),
  data: {
    'userId': currentUserId,
    'subject': 'math',
    'originalImageUrls': [file.$id],
    'analysisStatus': 'pending',  // 默认值，会触发分析
  },
);

// 4. 订阅 Realtime 更新
final subscription = realtime.subscribe([
  'databases.main.collections.mistake_records.documents.${mistakeRecord.$id}'
]);

subscription.stream.listen((response) {
  if (response.events.contains('databases.*.collections.*.documents.*.update')) {
    final updatedData = response.payload;
    final status = updatedData['analysisStatus'];
    
    if (status == 'completed') {
      // 显示分析结果
      showAnalysisResult(updatedData);
    } else if (status == 'failed') {
      // 显示错误，提供重新分析选项
      showError(updatedData['analysisError']);
    }
  }
});
```

### Backend 自动流程

```
1. mistake_record 创建
   ↓
2. Appwrite 触发 CREATE 事件
   ↓
3. mistake-analyzer 被调用
   ├─ 检查 analysisStatus == 'pending' ✅
   ├─ 更新状态为 'processing'
   ├─ 下载图片 (storage.getFileDownload)
   ├─ OCR + LLM 分析
   ├─ 创建/匹配模块和知识点
   ├─ 创建题目
   └─ 更新 mistake_record
       {
         "questionId": "...",
         "moduleIds": [...],
         "knowledgePointIds": [...],
         "errorReason": "conceptError",
         "analysisStatus": "completed",
         "analyzedAt": "2024-01-01T00:00:00Z"
       }
   ↓
4. Realtime 推送更新到 Flutter
   ↓
5. Flutter 显示结果
```

## 场景 2: 练习错题

练习中做错的题目，题目已存在，无需图片分析。

### Flutter 端流程

```dart
// 练习结束后，创建错题记录
final response = await functions.createExecution(
  functionId: 'mistake-recorder',
  body: json.encode({
    'action': 'createFromQuestion',
    'questionId': question.$id,
    'errorReason': 'carelessness',
    'userAnswer': userAnswer,
    'note': '粗心了',
  }),
);

final data = json.decode(response.responseBody);
final mistakeId = data['data']['mistakeId'];

// 直接查询显示，无需等待分析
final mistake = await databases.getDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
);
```

### Backend 流程

```
mistake-recorder.createFromQuestion()
  ├─ 获取题目信息
  ├─ 获取题目的模块和知识点
  ├─ 为用户创建对应的知识点（如不存在）
  └─ 创建错题记录（不需要分析）
      {
        "questionId": "...",
        "moduleIds": [...],
        "knowledgePointIds": [...],
        "errorReason": "...",
        // 注意：无 analysisStatus 字段，不会触发分析
      }
```

## 场景 3: 重新分析

分析失败或用户想重新分析时。

### Flutter 端流程

```dart
// 点击"重新分析"按钮
await databases.updateDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
  data: {
    'analysisStatus': 'pending',
    'analysisError': null,
  },
);

// 继续监听 Realtime（如果还在监听）
// 或重新订阅
```

### Backend 自动流程

```
1. mistake_record 更新 (analysisStatus -> 'pending')
   ↓
2. Appwrite 触发 UPDATE 事件
   ↓
3. mistake-analyzer 被调用
   ├─ 检查 analysisStatus == 'pending' ✅
   └─ 执行与场景1相同的分析流程
   ↓
4. Realtime 推送更新到 Flutter
```

## 状态流转

```
pending ──────────────────────> processing
   ↑                                 │
   │                                 ├──> completed
   │                                 │
   │                                 └──> failed
   │                                       │
   └───────────────────────────────────────┘
              (用户点击重新分析)
```

## 关键字段说明

### mistake_records 表

```javascript
{
  // 基本信息
  userId: string,              // 用户ID
  subject: string,             // 学科 (math/physics/...)
  originalImageUrls: string[], // 图片 fileId 数组（拍照错题）
  
  // 分析状态（仅拍照错题需要）
  analysisStatus: string,      // pending/processing/completed/failed
  analysisError: string,       // 错误信息
  analyzedAt: datetime,        // 分析完成时间
  
  // 分析结果
  questionId: string,          // 题目ID
  moduleIds: string[],         // 模块ID数组
  knowledgePointIds: string[], // 知识点ID数组
  errorReason: string,         // 错误原因
  userAnswer: string,          // 用户答案
  note: string,                // 笔记
  
  // 复习进度
  masteryStatus: string,       // notStarted/learning/reviewing/mastered
  reviewCount: integer,        // 复习次数
  correctCount: integer,       // 答对次数
  lastReviewAt: datetime,      // 最后复习时间
  masteredAt: datetime,        // 掌握时间
}
```

## Functions 职责划分

| Function | 类型 | 职责 | 触发方式 |
|----------|------|------|---------|
| **mistake-analyzer** | Event Trigger | 分析错题图片，完善记录 | create/update 事件 |
| **mistake-recorder** | API | 从已有题目创建错题 | Flutter 调用 API |
| **stats-updater** | Event Trigger | 更新用户统计 | mistake_records 变化 |

## 优势

### 1. 用户体验好
- ✅ 上传后立即返回，不用等待分析
- ✅ 通过 Realtime 实时显示进度
- ✅ 分析失败可重试

### 2. 架构清晰
- ✅ Event-driven，职责分离
- ✅ 无需轮询，节省资源
- ✅ 易于调试和监控

### 3. 可扩展
- ✅ 可以增加更多 Event Trigger
- ✅ 可以增加分析任务队列
- ✅ 可以支持批量分析

## 注意事项

### 1. 幂等性
- mistake-analyzer 检查状态，防止重复处理
- 同一记录不会被分析多次（除非用户手动触发）

### 2. 超时处理
- mistake-analyzer 超时时间 60秒
- 如果超时，Appwrite 会自动重试

### 3. 错误处理
- 所有错误都记录在 analysisError 字段
- Flutter 端可以根据错误类型给出提示

### 4. 安全性
- Row-level security 确保用户只能访问自己的数据
- Event trigger 使用 API Key，有完整权限

## 调试建议

### 查看 Function 日志
在 Appwrite Console -> Functions -> mistake-analyzer -> Logs

### 查看 Realtime 消息
```dart
subscription.stream.listen((response) {
  print('Event: ${response.events}');
  print('Payload: ${response.payload}');
});
```

### 常见问题排查

1. **分析一直 pending**
   - 检查 Function 是否启用
   - 查看 Function 日志

2. **没有收到 Realtime 更新**
   - 检查订阅的 channel 是否正确
   - 确认 Realtime 已启用

3. **分析失败**
   - 查看 `analysisError` 字段
   - 可能原因：图片下载失败、OCR 失败、LLM 超时

