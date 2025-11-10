# 题目生成 Worker

根据已有题目生成变式题的 AI Worker。

## 功能特性

- ✅ 根据源题目生成变式题
- ✅ 支持批量生成（多个源题目）
- ✅ 支持配置每题生成数量（1-10道）
- ✅ 保持知识点和难度一致
- ✅ 支持跨题型生成
- ✅ 自动解析和验证生成结果
- ✅ 实时更新任务进度

## 工作流程

```
前端创建任务 
  ↓
写入 question_generation_tasks 表
  ↓
触发 Appwrite Event
  ↓
Trigger Function 验证并转发
  ↓
Worker 实际处理
  ↓
生成变式题写入 questions 表
  ↓
更新任务状态和进度
```

## 使用方法

### 1. 前端创建任务

```dart
import 'package:appwrite/appwrite.dart';

// 创建题目生成任务
final task = await databases.createDocument(
  databaseId: 'main',
  collectionId: 'question_generation_tasks',
  documentId: ID.unique(),
  data: {
    'userId': currentUserId,
    'type': 'variant',
    'sourceQuestionIds': ['question_id_1', 'question_id_2'],
    'variantsPerQuestion': 2,  // 每题生成2道变式
    'status': 'pending',
    'totalCount': 4,  // 2个源题 × 2道变式
    'completedCount': 0,
  },
);

// 监听任务进度
final subscription = databases.subscribe([
  'databases.main.collections.question_generation_tasks.documents.${task.$id}'
]);

subscription.stream.listen((event) {
  final task = QuestionGenerationTask.fromJson(event.payload);
  print('进度: ${task.progress}%');
  
  if (task.isSuccess) {
    print('生成完成！生成了 ${task.generatedQuestionIds?.length} 道题');
  } else if (task.isFailed) {
    print('生成失败: ${task.error}');
  }
});
```

### 2. 查询生成结果

```dart
// 查询生成的题目
final generatedQuestions = await databases.listDocuments(
  databaseId: 'main',
  collectionId: 'questions',
  queries: [
    Query.equal('source', 'ai-gen'),
    Query.equal('createdBy', currentUserId),
    Query.orderDesc('\$createdAt'),
    Query.limit(10),
  ],
);
```

## 任务状态

- `pending`: 等待处理
- `processing`: 生成中
- `completed`: 已完成
- `failed`: 失败

## 数据库表结构

### question_generation_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| userId | string | 用户ID |
| type | string | 任务类型（variant） |
| status | string | 任务状态 |
| sourceQuestionIds | string[] | 源题目ID列表 |
| generatedQuestionIds | string[] | 生成的题目ID列表 |
| variantsPerQuestion | integer | 每题生成数量（1-10） |
| totalCount | integer | 总题目数 |
| completedCount | integer | 已完成数量 |
| error | string | 错误信息 |
| startedAt | datetime | 开始时间 |
| completedAt | datetime | 完成时间 |
| workerTaskId | string | Worker任务ID |

### 生成的题目

生成的题目会写入 `questions` 表，具有以下特征：

- `source`: `"ai-gen"` （标识为AI生成）
- `createdBy`: 创建任务的用户ID
- `isPublic`: `false` （默认私有）
- 继承源题目的：
  - `subject` 科目
  - `moduleIds` 模块ID列表
  - `knowledgePointIds` 知识点ID列表
  - `primaryKnowledgePointIds` 主要知识点ID列表

## 变式生成策略

LLM 会采用以下策略生成变式题：

1. **改变场景**：从购物场景改为旅游场景
2. **改变数值**：价格、距离、时间等参数
3. **改变问法**：正向问改为反向问
4. **改变题型**：选择题改为填空题（保持知识点）
5. **改变示例**：从苹果改为橙子

## 输出格式

使用**分段标记格式**而非 JSON，完美避免 LaTeX 公式的转义问题：

```
##QUESTION##

##TYPE##
choice

##DIFFICULTY##
3

##CONTENT##
已知函数 \( f(x) = x^2 + 2x + 1 \)，求 \( f(-1) \) 的值是（）

##OPTIONS##
A. 0
B. 1
C. 2
D. 4

##ANSWER##
A

##EXPLANATION##
将 \( x = -1 \) 代入函数：

\[
f(-1) = (-1)^2 + 2(-1) + 1 = 1 - 2 + 1 = 0
\]

因此答案是 A。

##END##
```

**优势：**
- LaTeX 公式直接书写，无需转义
- 标记清晰，易于解析
- 支持多行内容和复杂格式

## 配置参数

### 环境变量

```bash
# Appwrite 配置
APPWRITE_ENDPOINT=https://api.delvetech.cn/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key
APPWRITE_DATABASE_ID=main

# LLM 配置
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_MODEL=your_model_endpoint_id
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# Worker 配置
VOLC_TEMPERATURE=0.8  # 提高创造性
VOLC_MAX_TOKENS=4096
```

## 性能指标

- **平均生成时间**: 约 10-20 秒/题
- **并发支持**: 根据 Worker 并发数配置
- **成功率**: > 95%

## 错误处理

Worker 会处理以下错误：

1. **源题目不存在**: 跳过该题目，继续处理其他
2. **LLM 调用失败**: 自动重试（最多3次）
3. **生成格式错误**: 跳过无效题目，记录错误
4. **数据库写入失败**: 记录错误，不影响其他题目

## 日志

Worker 会输出详细日志：

```
[题目生成Worker] 开始处理任务
  - 任务ID: xxx
  - 用户ID: xxx
  - 源题目数: 2
  - 每题变式数: 2

[1/2] 处理源题目: question_id_1
  - 科目: 数学
  - 类型: choice
  - 难度: 3
  → 调用 LLM 生成变式题...
  ← LLM 响应完成，长度: 2048 字符
  ✓ 成功生成 2 道变式题
    [1] 已保存: new_question_id_1
    [2] 已保存: new_question_id_2

[题目生成Worker] 任务完成
  - 成功生成: 4 题
  - 失败数量: 0
```

## 测试

```python
# 测试生成变式题
import asyncio
from workers.question_generator import process_question_generation_task

async def test_generate():
    result = await process_question_generation_task({
        'task_id': 'test_task_id',
        'user_id': 'test_user_id',
        'task_type': 'variant',
        'source_question_ids': ['source_question_id'],
        'variants_per_question': 2
    })
    print(result)

asyncio.run(test_generate())
```

## 注意事项

1. 生成的题目默认为私有（`isPublic=false`）
2. 确保源题目包含完整的知识点信息
3. 生成数量建议控制在 1-5 道/题
4. LLM 可能偶尔生成不完美的题目，建议人工审核
5. 题目质量分默认为 5.0

## 未来扩展

计划支持的任务类型：

- `similar`: 相似题（同知识点不同难度）
- `practice`: 练习题（根据知识点生成）
- `exam`: 考试题（多知识点综合）

