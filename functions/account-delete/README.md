# 账户删除 Function

## 功能

删除用户账户及其所有相关数据。

## 删除的数据

1. **用户档案** (`profiles`)
2. **错题记录** (`mistake_records`)
3. **用户知识点** (`user_knowledge_points`)
4. **订阅记录** (`subscriptions`)
5. **练习会话** (`practice_sessions`)
6. **答题记录** (`practice_answers`)
7. **每日任务** (`daily_tasks`)
8. **周报** (`weekly_reports`)
9. **Appwrite 账户** (通过 Users API)

## 环境变量

- `APPWRITE_ENDPOINT`: Appwrite API 端点
- `APPWRITE_PROJECT_ID`: 项目 ID
- `APPWRITE_API_KEY`: API Key（需要用户管理权限）
- `APPWRITE_DATABASE_ID`: 数据库 ID（默认：`main`）

## 请求格式

```json
{
  "userId": "用户 ID"
}
```

## 响应格式

成功：
```json
{
  "success": true,
  "message": "账户已成功删除",
  "stats": {
    "profile": 1,
    "mistake_records": 10,
    "user_knowledge_points": 5,
    "subscriptions": 1,
    "practice_sessions": 3,
    "practice_answers": 15,
    "daily_tasks": 7,
    "weekly_reports": 2
  }
}
```

失败：
```json
{
  "success": false,
  "error": "错误信息"
}
```

## 注意事项

1. **不可逆操作**：删除账户是不可逆的，所有数据将被永久删除
2. **权限要求**：Function 需要具有删除用户数据的权限
3. **批量删除**：对于大量数据，采用分批删除策略（每批100条）
4. **错误处理**：即使部分数据删除失败，也会继续删除其他数据

