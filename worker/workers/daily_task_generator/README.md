# 每日任务生成 Worker

## 概述

负责为所有活跃用户生成每日复习任务的 Worker 模块。

## 功能

1. **扫描活跃用户**：获取最近 7 天内有活动的用户
2. **选择知识点**：为每个用户选择需要复习的知识点
3. **计算优先级**：根据重要度、紧急度、遗忘风险等指标排序
4. **生成任务项**：为每个知识点配置原题和变式题
5. **保存任务**：将生成的任务保存到数据库
6. **更新复习计划**：更新知识点的下次复习日期

## 模块结构

```
workers/daily_task_generator/
├── __init__.py                  # 模块导出
├── worker.py                    # Worker 主类
├── task_generator.py            # 任务生成核心逻辑
├── priority_calculator.py       # 优先级计算
├── question_selector.py         # 题目选择
└── utils.py                     # 工具函数
```

## 核心算法

### 1. 优先级计算

```python
优先级 = 紧急度×0.30 + 用户标记×0.25 + 知识点重要度×0.25 + 遗忘风险×0.20
```

**权重说明**：
- **紧急度(30%)**：逾期/今日到期/新错题，最紧迫，必须优先处理
- **用户标记(25%)**：用户主动标记重要，尊重用户的主观判断
- **知识点重要度(25%)**：客观重要程度，基于题目 importance 字段
- **遗忘风险(20%)**：基于艾宾浩斯遗忘曲线，前期快速增长，后期趋于平缓

**遗忘风险算法**（艾宾浩斯曲线）：
```python
遗忘风险 = 100 × (1 - e^(-2.5 × days_passed / current_interval))
```
- 刚复习完（0天）：风险 ≈ 0%
- 过半间隔（T/2天）：风险 ≈ 71%
- 到达间隔（T天）：风险 ≈ 92%
- 超过间隔（1.5T天）：风险 ≈ 98%

符合遗忘规律：前期遗忘最快，需要及时复习

### 2. 题量配置

| 难度 | 最小题数 | 最大题数 |
|------|----------|----------|
| easy | 3 | 6 |
| normal | 6 | 14 |
| hard | 10 | 20 |

### 3. 题目配置策略

| 知识点状态 | 原题数量 | 变式题数量 | 说明 |
|-----------|----------|-----------|------|
| newLearning | 1-2题 | 0题 | 只看原题，理解思路 |
| reviewing | 0-1题 | 2-3题 | 回顾 + 变式训练 |
| mastered | 0题 | 1-2题 | 综合题抽查 |

### 4. 题目去重策略（重要！）

**问题**：一道题可能关联多个知识点，如果简单去重会导致某些知识点没有题目。

**解决方案**：
1. 为每个知识点独立选题（不排除重复）
2. 按题目 ID 分组，合并重复的题目
3. 一道题对应多个知识点时，创建一个任务项关联所有知识点
4. 前端按知识点分组展示，保持以知识点为中心的用户体验

**数据结构**：
```json
{
  "id": "task-item-uuid",
  "questionId": "question-id",
  "source": "original",  // 或 "variant"
  "knowledgePoints": [
    {
      "knowledgePointId": "kp1",
      "knowledgePointName": "二次函数",
      "status": "reviewing"
    },
    {
      "knowledgePointId": "kp2", 
      "knowledgePointName": "一元二次方程",
      "status": "newLearning"
    }
  ],
  "isCompleted": false,
  "isCorrect": null,
  "mistakeRecordId": "mistake-id"  // 如果是原题
}
```

## 使用方法

### 通过 Worker API 调用

```python
import requests

response = requests.post(
    'http://localhost:8000/tasks/enqueue',
    json={
        'task_type': 'daily_task_generator',
        'task_data': {
            'trigger_time': '2025-11-05T02:00:00',
            'trigger_type': 'scheduled'
        },
        'priority': 3
    }
)

task_id = response.json()['task_id']
print(f"任务已提交: {task_id}")
```

### 查询任务状态

```python
status_response = requests.get(
    f'http://localhost:8000/tasks/{task_id}'
)

status = status_response.json()
print(f"任务状态: {status['status']}")
print(f"处理结果: {status.get('result')}")
```

## 返回结果

成功时返回：

```json
{
  "success": true,
  "timestamp": "2025-11-05T02:05:23",
  "trigger_type": "scheduled",
  "total_users": 150,
  "success_count": 120,
  "skip_count": 25,
  "error_count": 5,
  "user_results": [
    {
      "user_id": "user-123",
      "status": "success",
      "questions": 8
    },
    ...
  ]
}
```

## 性能优化

1. **批量查询**：使用 Query.limit() 限制单次查询数量
2. **异步处理**：Worker 池并发处理多个用户
3. **错误隔离**：单个用户失败不影响其他用户
4. **超时控制**：单个任务超时自动跳过

## 注意事项

1. **数据库字段**：确保 `profiles` 表有 `dailyTaskDifficulty` 字段（默认 'normal'）
2. **活跃用户定义**：最近 7 天内 `lastActiveAt` 有更新的用户
3. **覆盖策略**：如果当天已有任务，会删除旧任务重新生成
4. **知识点状态**：依赖 `review_states` 表的 `nextReviewDate` 字段

## 依赖

- `appwrite>=4.0.0`：数据库访问
- `loguru`：日志记录

## 测试

```bash
# 进入 worker 目录
cd backend/worker

# 运行测试（需要先实现测试用例）
python -m pytest workers/daily_task_generator/tests/
```

## 监控

查看日志文件：

```bash
tail -f logs/worker_*.log | grep daily_task_generator
```

关键日志：
- `开始生成每日任务`: 任务开始
- `找到 N 个活跃用户`: 用户扫描完成
- `✓ 用户 xxx: 生成 N 道题`: 单个用户成功
- `任务生成完成`: 所有用户处理完成

