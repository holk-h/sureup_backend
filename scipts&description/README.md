# 稳了！后端数据库

## 目录结构

```
backend/
├── appwrite.config.json      # Appwrite配置文件
├── init_database.py          # 数据库初始化脚本
├── requirements.txt          # Python依赖
└── functions/                # 云函数
    └── ...
```

## 快速开始

### 1. 设置Python环境

推荐使用虚拟环境隔离项目依赖：

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件或导出环境变量：

```bash
export APPWRITE_ENDPOINT="https://cloud.appwrite.io/v1"
export APPWRITE_PROJECT_ID="your-project-id"
export APPWRITE_API_KEY="your-api-key"
```

**获取API Key：**
1. 访问 [Appwrite Console](https://cloud.appwrite.io)
2. 进入你的项目
3. 前往 Settings → API Keys
4. 创建新的API Key，选择所有权限（用于初始化）

### 3. 初始化数据库

```bash
# 激活虚拟环境（如果还未激活）
source .venv/bin/activate

# 运行初始化脚本
python init_database.py
```

脚本将自动创建：
- ✅ 数据库（main）
- ✅ 10个集合（v2.0设计）
- ✅ 所有字段和索引
- ✅ 2个存储桶（mistake-images, question-images）

## 数据库结构

详细的数据库设计文档请查看：[`/doc/design/05_database_schema.md`](../doc/design/05_database_schema.md)

### Collections概览

| Collection | 说明 | 核心字段 |
|-----------|------|---------|
| **profiles** | 用户档案 | userId, name, grade, totalMistakes |
| **user_knowledge_points** | 用户知识点树 🌳 | userId, subject, name, parentId, mistakeCount |
| **knowledge_points_library** | 全局知识点库 | subject, name, aliases, usageCount |
| **questions** | 题目库 | subject, content, source, qualityScore |
| **mistake_records** | 错题记录 | userId, questionId, userKnowledgePointId, masteryStatus |
| **practice_sessions** | 练习会话 | userId, type, totalQuestions, status |
| **practice_answers** | 答题记录 📝 | sessionId, questionId, isCorrect, timeSpent |
| **question_feedbacks** | 题目反馈 💬 | questionId, feedbackType, status |
| **weekly_reports** | 周报 | userId, weekStart, topMistakePoints |
| **daily_tasks** | 每日任务 | userId, taskDate, questionIds, isCompleted |

### Storage Buckets

| Bucket | 说明 | 大小限制 |
|--------|------|---------|
| **mistake-images** | 错题拍照原图 | 10MB |
| **question-images** | 题目图片 | 5MB |

## 权限配置

初始化脚本会设置基础权限，但建议在 Appwrite Console 中进一步配置：

### Document Security（文档级权限）

对于以下集合，需要配置用户只能访问自己的数据：

1. **profiles**：
   - Read: `user:[userId]`
   - Update: `user:[userId]`
   - Delete: `user:[userId]`

2. **mistake_records**：
   - Create: `user:[userId]`
   - Read: `user:[userId]`
   - Update: `user:[userId]`
   - Delete: `user:[userId]`

3. **practice_sessions**：
   - Create: `user:[userId]`
   - Read: `user:[userId]`
   - Update: `user:[userId]`

4. **weekly_reports**：
   - Read: `user:[userId]`

5. **daily_tasks**：
   - Create: `user:[userId]`
   - Read: `user:[userId]`
   - Update: `user:[userId]`

### Collection Level（集合级权限）

- **knowledge_points** & **questions**：所有用户只读
- 创建操作通过云函数执行

## 预置数据

### 1. 知识点数据

建议预置常见知识点，参考：

```python
# 数学一级知识点示例
knowledge_points = [
    {"subject": "math", "name": "函数", "level": 1},
    {"subject": "math", "name": "几何", "level": 1},
    {"subject": "math", "name": "代数", "level": 1},
]

# 数学二级知识点示例
knowledge_points_level2 = [
    {"subject": "math", "name": "二次函数", "parentId": "<函数ID>", "level": 2},
    {"subject": "math", "name": "一次函数", "parentId": "<函数ID>", "level": 2},
]
```

可以创建 `seed_data.py` 脚本批量导入。

## 维护脚本

### 清理测试数据

```bash
# TODO: 创建清理脚本
python scripts/clean_test_data.py
```

### 备份数据

```bash
# TODO: 创建备份脚本
python scripts/backup_database.py
```

### 数据迁移

```bash
# TODO: 创建迁移脚本
python scripts/migrate.py
```

## 开发建议

### 1. 使用云函数操作数据

不要直接在前端使用Admin API Key，而是通过云函数：

```python
# functions/create-mistake/main.py
from appwrite.client import Client
from appwrite.services.databases import Databases

def main(req, res):
    client = Client()
    databases = Databases(client)
    
    # 创建错题记录
    document = databases.create_document(
        database_id='main',
        collection_id='mistake_records',
        document_id='unique()',
        data={...},
        permissions=[...]
    )
    
    return res.json(document)
```

### 2. 数据验证

在云函数中进行业务逻辑验证：

```python
def validate_mistake_record(data):
    """验证错题记录数据"""
    required_fields = ['userId', 'questionId', 'subject', 'knowledgePointId', 'errorReason']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # 验证枚举值
    valid_subjects = ['math', 'physics', 'chemistry', ...]
    if data['subject'] not in valid_subjects:
        raise ValueError(f"Invalid subject: {data['subject']}")
```

### 3. 查询优化

利用已创建的索引：

```python
# ✅ 好的查询 - 使用索引
documents = databases.list_documents(
    database_id='main',
    collection_id='mistake_records',
    queries=[
        Query.equal('userId', user_id),
        Query.equal('subject', 'math'),
        Query.order_desc('$createdAt'),
        Query.limit(20)
    ]
)

# ❌ 避免全表扫描
documents = databases.list_documents(
    database_id='main',
    collection_id='mistake_records'
)
```

## 监控与日志

### 使用Appwrite Console

1. **实时监控**：Dashboard → Realtime
2. **日志查看**：Functions → Logs
3. **使用统计**：Settings → Usage

### 性能指标

关注以下指标：
- 请求响应时间
- 数据库查询次数
- 存储使用量
- 带宽使用

## 故障排查

### 常见问题

1. **权限错误（403）**
   - 检查Document Security配置
   - 确认用户有对应的read/write权限

2. **索引错误**
   - 索引创建是异步的，需要等待完成
   - 在Console中查看索引状态

3. **文档大小限制**
   - 单个文档最大1MB
   - 大量数据使用数组字段或关联文档

## 相关链接

- [Appwrite官方文档](https://appwrite.io/docs)
- [Appwrite Python SDK](https://github.com/appwrite/sdk-for-python)
- [数据库设计文档](../doc/design/05_database_schema.md)
- [云函数开发指南](./functions/README.md)

## License

MIT

