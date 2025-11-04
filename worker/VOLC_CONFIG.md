# 火山引擎 LLM 配置指南

本文档说明如何配置火山引擎 LLM 服务。

## 好消息：您的现有配置已完全兼容！

您当前的 `.env` 配置已经是正确的火山引擎 ARK API 格式，**无需修改**即可使用。

```bash
# 当前配置（完全兼容）
DOUBAO_API_KEY=56bd9007-1417-450b-9ec7-2e3b58b5c818
DOUBAO_MODEL=doubao-seed-1-6-251015
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
```

系统会自动识别 `DOUBAO_*` 配置并使用火山引擎 SDK。

## 可选：添加高级参数

如果您想使用高级功能（如思考模式），可以在 `.env` 文件中添加以下参数：

### 1. 思考模式（推理模式）

思考模式会让模型进行更深入的推理，适合复杂数学题分析：

```bash
# 启用思考模式（适合复杂数学题）
VOLC_THINKING_ENABLED=true
```

### 2. 温度和采样参数

调整模型的创造性和确定性：

```bash
# 温度（0-1），越低越确定，越高越随机
VOLC_TEMPERATURE=0.6          # 推荐：数学题用 0.5-0.7

# Top-P 采样（0-1）
VOLC_TOP_P=0.9                # 推荐：保持默认 0.9
```

### 3. Token 限制

控制生成内容的长度：

```bash
# 最大生成 token 数
VOLC_MAX_TOKENS=4096          # 推荐：2048-4096
```

### 4. 网络和重试

优化网络连接和错误处理：

```bash
# 请求超时时间（秒）
VOLC_TIMEOUT=120              # 默认 120 秒，可根据网络情况调整

# 最大重试次数
VOLC_MAX_RETRIES=3            # 默认 3 次
```

## 完整的配置示例

您的 `.env` 文件可以是这样的（添加了高级参数）：

```bash
# ============================================
# Appwrite 配置
# ============================================
APPWRITE_ENDPOINT=https://api.delvetech.cn/v1
APPWRITE_PROJECT_ID=6901942c30c3962e66eb
APPWRITE_API_KEY=standard_991a96110f28ca1664d2a7e757b2cb35c4e296fa3aee2c9d9852aa252723af6d1f6c86f457e781260df35e4cb00e9f138775e75b87a99fc73f6f5e5a0604ec153e04657ef54960d59d8624582fdf29914413dadf0b96158c1412a5bfa7c5a5228cf262ac4d9d3231206808072411cc3b22dd86c0464423831a63885a43b89acd
APPWRITE_DATABASE_ID=main

# ============================================
# 火山引擎 LLM 配置
# ============================================
# 基础配置（必需，您已配置）
DOUBAO_API_KEY=56bd9007-1417-450b-9ec7-2e3b58b5c818
DOUBAO_MODEL=doubao-seed-1-6-251015
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# 高级参数（可选，根据需要添加）
VOLC_TEMPERATURE=0.6                         # 温度：0.5-0.7 适合数学题
VOLC_TOP_P=0.9                               # Top-P：保持默认
VOLC_MAX_TOKENS=4096                         # 最大 token 数
VOLC_THINKING_ENABLED=false                  # 思考模式：复杂题目可设为 true
VOLC_TIMEOUT=120                             # 超时时间（秒）
VOLC_MAX_RETRIES=3                           # 最大重试次数

# ============================================
# Worker 配置
# ============================================
WORKER_CONCURRENCY=100
WORKER_TIMEOUT=300
QUEUE_TYPE=memory

# ============================================
# FastAPI 服务器配置
# ============================================
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1

# ============================================
# 日志配置
# ============================================
LOG_LEVEL=INFO

# ============================================
# 其他配置
# ============================================
ORIGIN_IMAGE_BUCKET=origin_question_image
```

## 参数详解

### 温度（Temperature）
- **范围**: 0.0 - 1.0
- **说明**: 控制输出的随机性
  - 较低的值（如 0.5）使输出更确定、更准确
  - 较高的值（如 0.8）使输出更随机、更有创意
- **推荐值**: 
  - 数学题分析：**0.5-0.6**（更准确）
  - 错题分析：**0.6-0.7**（平衡准确性和表达）
  - 学习建议：0.7-0.8（更有创意）

### Top-P（核采样）
- **范围**: 0.0 - 1.0
- **说明**: 控制输出词汇的多样性
- **推荐值**: **0.9**（保持默认即可）

### 最大 Token 数（Max Tokens）
- **范围**: 1 - 模型上限
- **说明**: 限制生成的最大 token 数量
- **推荐值**: 
  - 简短分析：1024-2048
  - 详细分析：**2048-4096**（推荐）

### 思考模式（Thinking Mode）
- **值**: true / false
- **说明**: 启用后，模型会进行更深入的推理
  - ✅ 会提高答案质量
  - ⚠️ 会增加推理时间
  - ⚠️ 会增加 token 消耗
- **推荐场景**:
  - ✅ 复杂数学证明题
  - ✅ 多步骤推理题
  - ✅ 逻辑分析题
  - ❌ 简单计算题
  - ❌ 知识点分类

## 使用示例

### 基础对话

```python
from workers.mistake_analyzer.llm_provider import get_llm_provider

# 获取 provider（会自动读取环境变量）
provider = get_llm_provider()

# 文本对话
response = await provider.chat(
    prompt="解释一下什么是二次函数",
    system_prompt="你是一个专业的数学老师"
)
```

### 启用思考模式

```python
# 对于需要深入推理的问题，临时启用思考模式
response = await provider.chat(
    prompt="证明：对于任意正整数 n，n^2 + n 必定是偶数",
    thinking_enabled=True,  # 启用思考模式
    temperature=0.5,        # 降低温度以获得更准确的推理
)
```

### 图像分析

```python
# 分析题目图片
response = await provider.chat_with_vision(
    prompt="分析这道数学题，并给出详细解答步骤",
    image_url="https://example.com/math_problem.jpg",
    temperature=0.6,  # 数学题用较低温度
)
```

### 自定义参数

```python
# 完全自定义参数（覆盖环境变量）
response = await provider.chat(
    prompt="分析这道题",
    temperature=0.5,       # 自定义温度
    top_p=0.95,            # 自定义 top_p
    max_tokens=2048,       # 限制输出长度
    thinking_enabled=True, # 启用思考模式
)
```

## 性能优化建议

### 1. 针对不同场景调整参数

| 场景 | Temperature | Thinking Mode | Max Tokens | 说明 |
|------|-------------|---------------|------------|------|
| 数学题解析 | 0.5-0.6 | true | 2048-4096 | 需要准确和推理 |
| 错题分析 | 0.6-0.7 | false | 1024-2048 | 平衡准确性和表达 |
| 知识点总结 | 0.5-0.6 | false | 512-1024 | 需要准确 |
| 学习建议 | 0.7-0.8 | false | 1024-2048 | 可以更有创意 |

### 2. 合理使用思考模式

**✅ 适合使用思考模式的场景:**
- 复杂数学证明题
- 多步骤逻辑推理题
- 需要详细思考过程的问题
- 物理/化学复杂计算题

**❌ 不建议使用思考模式的场景:**
- 简单事实查询
- 知识点分类
- 格式转换
- 简单计算题

### 3. 超时和重试配置

如果遇到网络不稳定或超时问题：

```bash
# 增加超时时间（对于复杂任务）
VOLC_TIMEOUT=180        # 3 分钟

# 增加重试次数（对于不稳定网络）
VOLC_MAX_RETRIES=5
```

## 错误排查

### 常见错误

1. **401 Unauthorized**
   - 检查 `DOUBAO_API_KEY` 是否正确
   - 确认 API Key 是否已激活

2. **404 Not Found**
   - 检查 `DOUBAO_MODEL` (Endpoint ID) 是否正确
   - 确认 Endpoint 是否已创建并启用

3. **429 Too Many Requests**
   - 已达到 API 调用限额
   - 考虑增加重试延迟或降低并发数

4. **超时错误**
   - 增加 `VOLC_TIMEOUT` 值
   - 检查网络连接
   - 考虑减少 `VOLC_MAX_TOKENS`

### 查看日志

系统会自动记录以下信息：
- 推理 token 使用量（启用思考模式时）
- 重试次数和原因
- 请求耗时

```bash
# 查看实时日志
tail -f logs/worker.log

# 设置详细日志级别
LOG_LEVEL=DEBUG
```

## 迁移说明

### 从旧配置迁移

如果您想使用新的命名方式，可以这样迁移：

```bash
# 旧配置（仍然支持）
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=your_endpoint_id
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# 新配置（等价，可选）
VOLC_API_KEY=your_api_key
VOLC_ENDPOINT_ID=your_endpoint_id
VOLC_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
```

两种命名方式完全等价，系统会自动识别。**建议保持现有配置不变。**

## 获取火山引擎凭证

如果您需要创建新的 Endpoint：

1. 访问[火山引擎控制台](https://console.volcengine.com/)
2. 进入「模型推理」服务
3. 创建推理接入点（Endpoint）
4. 获取 API Key 和 Endpoint ID
5. 将配置添加到 `.env` 文件

## 参考文档

- [火山引擎推理服务文档](https://www.volcengine.com/docs/82379/1449737)
- [多模态接口文档](https://www.volcengine.com/docs/82379/1399009)
- [火山引擎控制台](https://console.volcengine.com/)

## 总结

1. ✅ **您的现有配置完全兼容，无需修改**
2. 🎯 **可选添加高级参数以优化性能**
3. 💡 **数学题推荐配置**: `VOLC_TEMPERATURE=0.6`，复杂题目启用 `VOLC_THINKING_ENABLED=true`
4. 📝 **遇到问题查看日志**: `tail -f logs/worker.log`
