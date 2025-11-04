# 错题分析器 - 统计数据自动更新

## 功能说明

在用户记录错题时（通过拍照OCR），`mistake_analyzer` 会自动更新用户档案中的统计字段。

## 更新的统计字段

### 1. 活跃天数
- **字段**: `activeDays`
- **逻辑**: 如果今天是第一次有学习活动，则递增 +1
- **判断**: 通过 `lastActiveAt` 判断上次活跃是否是今天

### 2. 今日错题数
- **字段**: `todayMistakes`
- **逻辑**: 每次记录错题时 +1
- **重置**: 如果检测到日期变化（通过 `lastResetDate`），先重置为 0，再递增

### 3. 本周错题数
- **字段**: `weekMistakes`
- **逻辑**: 每次记录错题时 +1
- **重置**: 由定时任务在每周一凌晨重置（不在此处理）

### 4. 总错题数
- **字段**: `totalMistakes`
- **逻辑**: 每次记录错题时 +1
- **不会重置**: 累计统计

### 5. 周数据图表
- **字段**: `weeklyMistakesData` (JSON 字符串)
- **格式**: `[{"date": "2024-01-01", "count": 5}, ...]`
- **逻辑**: 
  - 更新或添加今天的错题数
  - 自动清理 7 天前的旧数据
  - 用于主页"过去一周"图表显示

### 6. 时间戳更新
- **字段**: `lastActiveAt`、`lastResetDate`、`statsUpdatedAt`
- **逻辑**: 更新为当前 UTC 时间

## 工作流程

```
用户拍照记录错题
    ↓
Flutter 上传图片 → 创建 mistake_record (analysisStatus: pending)
    ↓
触发 mistake_analyzer (数据库事件)
    ↓
1. 下载图片
2. OCR 识别（AI 视觉分析）
3. 创建题目
4. 更新知识点
5. 更新错题记录状态 → completed
    ↓
6. 【新增】更新用户档案统计 ← 本次添加的功能
    ├─ 检查并重置每日数据（如果是新的一天）
    ├─ 更新活跃天数（如果今天首次活动）
    ├─ 递增今日错题数
    ├─ 递增本周错题数
    ├─ 递增总错题数
    ├─ 更新周数据 JSON
    └─ 更新时间戳
    ↓
完成（Flutter 端通过 Realtime API 收到更新）
```

## 代码结构

### 新增文件
- `profile_stats_service.py`: 用户档案统计更新服务

### 修改文件
- `main.py`: 在 `process_mistake_analysis()` 函数中调用统计更新

### 核心函数

#### `update_profile_stats_on_mistake_created(databases, user_id)`
主函数，协调所有统计更新逻辑。

#### `check_and_reset_daily_stats(profile)`
检查是否需要重置每日统计（`todayMistakes`, `todayPracticeSessions`）。

#### `check_and_update_active_days(profile)`
检查并更新活跃天数，如果今天首次活动则 +1。

#### `update_weekly_mistakes_data(profile)`
更新过去一周的错题数据 JSON，用于图表显示。

## 错误处理

- 统计更新失败**不会影响**主流程
- 如果更新失败，会打印警告日志，但错题分析仍然继续
- 使用 `try-except` 包裹统计更新，确保主业务不受影响

```python
# 11. 更新用户档案统计数据
try:
    await asyncio.to_thread(
        update_profile_stats_on_mistake_created,
        databases=databases,
        user_id=user_id
    )
except Exception as e:
    # 统计更新失败不影响主流程
    print(f"⚠️ 更新用户统计数据失败: {str(e)}")
```

## 日志输出示例

```
✓ 重置每日统计数据
✓ 成功更新用户统计数据: 67890abcdef
   - 今日错题: 1
   - 本周错题: 5
   - 总错题数: 25
   - 活跃天数: 8

✅ 错题分析完成: 12345abcdef
   - 题目ID: question_abc123
   - 学科: 数学
   - 模块数: 1
   - 知识点数: 2
```

## 数据一致性

### 时区处理
- 所有时间戳使用 **UTC 时间**
- 日期比较统一使用 `datetime.date()` 对象
- ISO 8601 格式: `2024-01-01T12:00:00.000Z`

### 并发问题
- Appwrite 数据库操作是原子的
- 使用 `asyncio.to_thread()` 在异步环境中执行同步数据库操作
- 统计更新在错题记录更新**之后**执行，避免竞态条件

### 数据修复
如果统计数据不准确，可以通过以下方式修复：
1. 运行 `stats-updater` 函数重新计算所有统计
2. 手动通过 Appwrite Console 修改用户档案

## 性能考虑

### 数据库查询优化
- 使用 `Query.limit(1)` 限制查询结果
- 通过 `userId` 索引查询用户档案

### 异步执行
- 统计更新在独立的线程中执行（`asyncio.to_thread`）
- 不阻塞主流程的 OCR 分析

### JSON 数据大小
- `weeklyMistakesData` 只保留最近 7 天数据
- 典型大小: ~200 bytes
- 不会造成性能问题

## 测试建议

### 单元测试场景
1. ✅ 首次记录错题（初始化所有字段）
2. ✅ 同一天多次记录错题（不重置，正常递增）
3. ✅ 跨天记录错题（重置每日数据）
4. ✅ 周数据 JSON 格式正确
5. ✅ 异常情况下不影响主流程

### 集成测试
```bash
# 1. 创建测试用户
# 2. 上传错题图片
# 3. 等待分析完成
# 4. 验证用户档案统计数据是否正确更新
```

## 相关文档

- [用户档案统计字段说明](../../../../doc/profile_stats_fields.md)
- [Stats Updater 函数设计](../../functions/stats-updater/README.md)

## 版本历史

- **2024-11-03**: 初始版本
  - 添加 `profile_stats_service.py`
  - 修改 `main.py` 调用统计更新
  - 支持 8 个统计字段的自动更新

## 注意事项

⚠️ **每周数据重置**：本模块不处理每周数据重置（`weekMistakes`, `weekPracticeSessions`），这应该由 `daily-task-scheduler` 定时任务处理。

⚠️ **连续学习天数**：`continuousDays` 字段的更新逻辑较为复杂（需要判断是否中断），建议由专门的定时任务处理，不在此处理。

⚠️ **练习相关统计**：`todayPracticeSessions`, `weekPracticeSessions` 等练习相关字段，应该在练习完成时更新，不在错题记录时更新。

