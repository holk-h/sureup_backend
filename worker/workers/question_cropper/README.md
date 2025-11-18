# 题目裁剪 Worker

## 功能说明

从单张图片中裁剪指定题目，使用 LLM 检测题目边界框（bbox），然后裁剪并上传到存储桶。

## 工作流程

1. Flutter 端调用 Function 创建裁剪任务记录（`question_cropping_tasks` 表）
2. Function 将任务入队到 Worker 系统
3. Worker 异步执行裁剪任务：
   - 下载原图
   - 使用 LLM 检测题目 bbox
   - 裁剪图片
   - 上传裁剪后的图片
   - 更新任务状态为 `completed` 或 `failed`
4. Flutter 端通过 Realtime API 订阅任务更新，实时显示结果

## 数据库表结构

### question_cropping_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| $id | string | 任务ID（自动生成） |
| userId | string | 用户ID |
| imageFileId | string | 原图文件ID |
| questionNumber | string | 题号（如 "12题"、"第一题"） |
| status | string | 任务状态：pending/processing/completed/failed |
| croppedImageId | string | 裁剪后的图片ID（完成时） |
| error | string | 错误信息（失败时） |
| createdAt | datetime | 创建时间 |
| updatedAt | datetime | 更新时间 |

## 任务状态

- `pending`: 任务已创建，等待处理
- `processing`: 正在处理中
- `completed`: 处理完成
- `failed`: 处理失败

