# 错题记录器 (Mistake Recorder)

错题记录器函数提供特殊的错题创建业务逻辑。

## ⚠️ 架构说明

本项目采用事件驱动架构处理错题分析：

- **拍照错题**: Flutter 上传图片 → 创建 mistake_record → **mistake-analyzer** 自动触发分析
- **重新分析**: Flutter 更新 analysisStatus → **mistake-analyzer** 自动触发分析  
- **练习错题**: 调用本函数的 API

## 功能概述

本函数**仅**提供一个 API 接口：
- `createFromQuestion` - 从已有题目创建错题记录（练习中做错的题目）

其他错题处理由 **mistake-analyzer** (Event Trigger) 自动完成。

## 数据结构

本函数采用三级知识体系：

- **学科 (subject)**: 如数学、物理（最顶层）
- **模块 (module)**: 公有的学科分类，存储在 `knowledge_points_library`（如"微积分"、"代数"、"电磁学"）
- **知识点 (knowledge_point)**: 用户私有，存储在 `user_knowledge_points`，关联 `moduleId`（如"定积分"、"导数"）

**关键特性**：
- ✅ 模块是公有的，所有用户共享
- ✅ 知识点是私有的，每个用户独立维护
- ✅ 一个题目可以关联多个模块和多个知识点
- ✅ 题目内容和解析统一使用 Markdown + LaTeX 公式格式

## 模块结构

```
mistake-recorder/
├── src/
│   ├── main.py                      # 主入口，路由处理
│   ├── utils.py                     # 工具函数
│   ├── image_analyzer.py            # 图片分析模块（待完善）
│   ├── question_service.py          # 题目服务
│   ├── mistake_service.py           # 错题记录服务
│   └── knowledge_point_service.py   # 知识点服务
├── requirements.txt
└── README.md
```

## 设计原则

**函数负责复杂的业务逻辑处理，完成所有数据写入后只返回ID列表。**

核心思想：
1. 云函数内部完成所有复杂的业务逻辑（图片分析、模块和知识点关联、数据写入等）
2. 只返回必要的ID列表（questionId, mistakeId, moduleId, knowledgePointIds）
3. Flutter端需要详细数据时，直接用Appwrite SDK根据ID查询

这样做的好处：
- **减少数据传输** - 不返回完整对象，只返回ID
- **提高灵活性** - Flutter端可以按需查询数据
- **降低成本** - 减少函数执行时间和流量
- **简化接口** - 返回值简单明了
- **职责清晰** - 函数专注业务逻辑，查询由客户端处理

## API 接口

### createFromQuestion - 从已有题目创建错题记录

适用于练习中做错的题目。这些题目已经存在于题库中，无需图片分析。

**请求**:
```json
{
  "action": "createFromQuestion",
  "questionId": "xxx",                 // 必需：题目ID
  "errorReason": "conceptError",       // 可选：错误原因（默认：conceptError）
  "userAnswer": "A",                   // 可选：用户答案
  "note": "这道题我理解错了"             // 可选：笔记
}
```

**响应**:
```json
{
  "success": true,
  "message": "错题记录创建成功",
  "data": {
    "questionId": "question_id_here",
    "mistakeId": "mistake_id_here",
    "moduleId": "module_id_here",
    "knowledgePointIds": ["kp_id_1", "kp_id_2"],
    "confidence": 0.85
  }
}
```

Flutter端如需详细信息，可根据ID查询：
```dart
// 查询题目详情
final question = await databases.getDocument(
  databaseId: 'main',
  collectionId: 'questions',
  documentId: questionId,
);

// 查询错题详情
final mistake = await databases.getDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
);
```

### 2. createFromQuestion - 从已有题目创建错题

适用于练习中做错的题目。这个函数包含知识点关联等业务逻辑。

**请求**:
```json
{
  "action": "createFromQuestion",
  "questionId": "question_id_here",
  "errorReason": "carelessness",
  "userAnswer": "B",
  "note": "粗心算错了"
}
```

**响应**:
```json
{
  "success": true,
  "message": "错题记录创建成功",
  "data": {
    "mistakeId": "mistake_id_here",
    "questionId": "question_id_here",
    "moduleIds": ["module_id_1"],
    "knowledgePointIds": ["kp_id_1", "kp_id_2"]
  }
}
```

## Flutter 端直接操作数据库

以下操作请在 Flutter 端使用 Appwrite SDK 直接完成：

### 获取错题详情
```dart
final mistake = await databases.getDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
);
```

### 列出错题记录
```dart
final mistakes = await databases.listDocuments(
  databaseId: 'main',
  collectionId: 'mistake_records',
  queries: [
    Query.equal('userId', userId),
    Query.equal('subject', 'math'),  // 可选
    Query.orderDesc('\$createdAt'),
    Query.limit(50),
  ],
);
```

### 更新掌握状态
```dart
await databases.updateDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
  data: {
    'masteryStatus': 'mastered',
    'reviewCount': reviewCount + 1,
    'lastReviewAt': DateTime.now().toIso8601String(),
  },
);
```

### 删除错题记录
```dart
await databases.deleteDocument(
  databaseId: 'main',
  collectionId: 'mistake_records',
  documentId: mistakeId,
);
```

## 错误原因类型

- `conceptError` - 概念错误
- `carelessness` - 粗心大意
- `calculationError` - 计算错误
- `methodError` - 方法错误
- `incompleteAnswer` - 答案不完整
- `misunderstanding` - 理解错误
- `timeConstrain` - 时间不够
- `other` - 其他

## 掌握状态

- `notStarted` - 未开始复习
- `learning` - 学习中
- `reviewing` - 复习中
- `mastered` - 已掌握

系统会根据复习次数和正确次数自动判断掌握状态：
- 复习 ≥ 3次 且 正确 ≥ 3次 → `mastered`
- 复习 ≥ 2次 → `reviewing`
- 复习 ≥ 1次 → `learning`

## 工作流程

### 完整错题上传流程

```
用户上传图片
    ↓
图片分析 (LLM 视觉能力)
    ↓
提取题目信息、模块、知识点列表
    ↓
确保公有模块存在
    ↓
确保用户知识点存在（关联到模块）
    ↓
创建题目记录（关联多个模块和知识点）
    ↓
创建错题记录（关联多个模块和知识点）
    ↓
返回 ID 列表（questionId, mistakeId, moduleId, knowledgePointIds）
    ↓
📡 Appwrite 自动触发数据库事件
    ↓
⚡ stats-updater 函数被事件触发（独立运行）
    ↓
更新知识点统计和用户档案
```

**注意**：stats-updater 是独立的 Appwrite Function，通过数据库事件自动触发，不是被 mistake-recorder 调用的。

### 数据流转说明

1. **图片分析阶段**: LLM 识别出模块名称（如"微积分"）和知识点名称列表（如["定积分", "幂函数积分"]）
2. **模块处理**: 在公有模块库（`knowledge_points_library`）中查找或创建模块
3. **知识点处理**: 在用户知识点库（`user_knowledge_points`）中为当前用户创建知识点，关联到模块
4. **题目创建**: 题目同时关联模块ID数组和知识点ID数组
5. **错题创建**: 错题记录同样关联模块ID数组和知识点ID数组

## 图片分析模块

### 当前实现 (image_analyzer.py)

已实现基于 LLM 视觉能力的图片分析：

1. **LLM 视觉模型支持**
   - OpenAI GPT-4 Vision
   - Anthropic Claude Vision
   - Google Gemini Vision
   - 可通过环境变量配置不同的 LLM 提供商

2. **AI 完成的任务**
   - ✅ 识别题目类型（choice/fillBlank/shortAnswer/essay）
   - ✅ 提取题目内容（Markdown + LaTeX 格式）
   - ✅ 识别所属模块（如"微积分"、"代数"）
   - ✅ 提取知识点列表（如["定积分", "幂函数积分"]）
   - ⏳ 提取选项和答案（待完善）
   - ⏳ 生成解析（待完善）
   - ⏳ 判断难度（待完善）
   - ⏳ 识别用户错误答案（待完善）
   - ⏳ 分析错误原因（待完善）

3. **输出格式**
   - 题目内容：Markdown 格式，数学公式使用 LaTeX（行内 `$...$`，独立 `$$...$$`）
   - 结构化 JSON 输出，包含所有必需字段

## 环境变量

需要在 Appwrite Functions 中配置：

```
APPWRITE_ENDPOINT=https://api.delvetech.cn/v1
APPWRITE_PROJECT_ID=6901942c30c3962e66eb
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main
```

## 权限要求

- `databases.read` - 读取数据库
- `databases.write` - 写入数据库
- 用户需要登录（通过 JWT token 认证）

## 注意事项

1. **自动统计更新**: 创建错题记录后会自动触发 `stats-updater` 函数更新用户统计
2. **重复错题**: 如果同一用户对同一题目创建错题记录，会更新现有记录而不是创建新的
3. **三级知识体系**:
   - 模块是公有的，存储在 `knowledge_points_library`，所有用户共享
   - 知识点是私有的，存储在 `user_knowledge_points`，每个用户独立维护
   - 一个题目/错题可以关联多个模块和多个知识点
4. **数据格式**: 题目内容和解析统一使用 Markdown + LaTeX 公式格式，便于前端渲染
5. **权限验证**: 所有操作都会验证用户权限，确保用户只能操作自己的数据

## 数据示例

### LLM 分析结果示例

```json
{
  "content": "计算定积分：\n\n$$\\int_0^1 x^2 dx$$\n\n**选项：**\nA. $\\frac{1}{2}$\nB. $\\frac{1}{3}$\nC. $\\frac{1}{4}$\nD. $\\frac{2}{3}$",
  "type": "choice",
  "module": "微积分",
  "knowledgePointNames": ["定积分", "幂函数积分"],
  "confidence": 0.85
}
```

### 数据库记录示例

**模块记录** (`knowledge_points_library`):
```json
{
  "$id": "module_calculus_001",
  "subject": "math",
  "name": "微积分",
  "description": "微积分基础知识",
  "order": 1,
  "usageCount": 128,
  "isActive": true
}
```

**用户知识点记录** (`user_knowledge_points`):
```json
{
  "$id": "kp_user_001",
  "userId": "user_123",
  "moduleId": "module_calculus_001",
  "subject": "math",
  "name": "定积分",
  "description": "定积分的计算方法",
  "mistakeCount": 5,
  "masteredCount": 2,
  "lastMistakeAt": "2025-10-31T10:30:00.000Z"
}
```

**题目记录** (`questions`):
```json
{
  "$id": "question_001",
  "subject": "math",
  "moduleIds": ["module_calculus_001"],
  "knowledgePointIds": ["kp_user_001", "kp_user_002"],
  "type": "choice",
  "difficulty": 3,
  "content": "计算定积分：\n\n$$\\int_0^1 x^2 dx$$...",
  "options": ["A. $\\frac{1}{2}$", "B. $\\frac{1}{3}$", ...],
  "answer": "B",
  "source": "ocr",
  "createdBy": "user_123"
}
```

**错题记录** (`mistake_records`):
```json
{
  "$id": "mistake_001",
  "userId": "user_123",
  "questionId": "question_001",
  "moduleIds": ["module_calculus_001"],
  "knowledgePointIds": ["kp_user_001", "kp_user_002"],
  "subject": "math",
  "errorReason": "conceptError",
  "userAnswer": "A",
  "note": "忘记使用积分公式",
  "masteryStatus": "notStarted",
  "reviewCount": 0,
  "correctCount": 0
}
```

## 测试

可以使用 Appwrite Console 的 Functions 测试功能，或使用 curl：

```bash
curl -X POST https://your-appwrite-endpoint/v1/functions/mistake-recorder/executions \
  -H "Content-Type: application/json" \
  -H "X-Appwrite-Project: 6901942c30c3962e66eb" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "action": "uploadMistake",
    "imageUrl": "https://example.com/image.jpg",
    "subject": "math"
  }'
```

