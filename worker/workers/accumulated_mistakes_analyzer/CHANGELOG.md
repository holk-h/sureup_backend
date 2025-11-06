# 更新日志

## 2025-01-XX - 流式输出重构

### 主要更新

#### 1. LLM Provider 支持流式输出

**文件**: `backend/worker/workers/mistake_analyzer/llm_provider.py`

- ✨ **新增**：`_chat_with_sdk` 方法支持返回流式响应对象
- 🔧 **修改**：当 `stream=True` 时，直接返回 response 对象供调用方处理
- 📝 **说明**：使用火山引擎 ARK SDK 的原生流式 API

```python
# 使用示例
stream_response = await provider.chat(
    prompt="你好",
    stream=True  # 启用流式输出
)

with stream_response:
    for chunk in stream_response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end='')
```

#### 2. Worker 流式处理重构

**文件**: `backend/worker/workers/accumulated_mistakes_analyzer/worker.py`

##### 修改的方法

1. **`_generate_analysis`**
   - 从一次性生成改为流式调用
   - 调用 `_process_stream_response` 处理流式响应

2. **新增 `_process_stream_response`**
   - 实时接收 LLM 流式输出
   - 累积内容并按 0.5 秒频率更新数据库
   - 使用 `with` 语句管理连接生命周期

3. **新增 `_update_analysis_content`**
   - 专门负责更新分析内容到数据库
   - 使用异步执行器避免阻塞
   - 错误不抛出，避免中断流式输出

4. **删除 `_stream_content_to_database`**
   - 旧的分段更新方法已废弃
   - 被新的流式处理方法替代

### 技术改进

| 方面 | 旧方案 | 新方案 |
|------|--------|--------|
| **API 调用** | 一次性生成完整内容 | 流式接收，逐 chunk 处理 |
| **更新策略** | 按段落分割（\n\n） | 按时间间隔（0.5 秒） |
| **用户体验** | 跳跃式显示 | 流畅连续显示 |
| **首字延迟** | 高（需等待第一段生成完） | 低（实时显示） |
| **连接管理** | 无 | `with` 语句自动管理 |
| **更新频率** | 不可控（取决于段落数） | 可控（固定 0.5 秒） |

### 性能优化

- ⚡ **首字延迟降低**：用户几乎立即看到第一个字
- 🎯 **更新频率可控**：0.5 秒间隔，平衡性能和体验
- 💪 **连接可靠性**：使用 `with` 确保连接正确关闭
- 📉 **数据库负载**：限频更新，避免过度写入

### 文档更新

1. **README.md**
   - 更新流式输出实现说明
   - 添加技术架构图
   - 增加代码示例

2. **STREAM_GUIDE.md** (新增)
   - 详细的流式输出实现指南
   - 架构图和数据流说明
   - 前端集成示例
   - 故障排查和最佳实践

3. **test_stream.py** (新增)
   - 流式输出功能测试脚本
   - 验证基本流式功能
   - 验证 0.5 秒更新频率

4. **functions/ai-accumulated-analyzer/README.md**
   - 添加流式输出特性说明
   - 突出实时生成能力

### 代码示例

#### 完整的流式处理流程

```python
async def _generate_analysis(self, analysis_id, mistakes, stats):
    """生成分析内容（流式输出）"""
    prompt = self._build_analysis_prompt(mistakes, stats)
    
    # 1. 调用流式 API
    stream_response = await self.llm_provider.chat(
        prompt=prompt,
        temperature=0.7,
        max_tokens=30000,
        stream=True  # 关键
    )
    
    # 2. 处理流式响应
    await self._process_stream_response(analysis_id, stream_response)


async def _process_stream_response(self, analysis_id, stream_response):
    """处理流式响应"""
    accumulated_content = ''
    last_update_time = asyncio.get_event_loop().time()
    update_interval = 0.5  # 0.5 秒更新一次
    
    with stream_response:  # 确保连接关闭
        for chunk in stream_response:
            # 提取增量内容
            if chunk.choices[0].delta.content is not None:
                accumulated_content += chunk.choices[0].delta.content
                
                # 限频更新数据库
                current_time = asyncio.get_event_loop().time()
                if current_time - last_update_time >= update_interval:
                    await self._update_analysis_content(
                        analysis_id,
                        accumulated_content
                    )
                    last_update_time = current_time
    
    # 最后一次更新
    if accumulated_content:
        await self._update_analysis_content(analysis_id, accumulated_content)
```

### 前端影响

**无需修改**：前端代码保持不变，仍然通过 Appwrite Realtime 订阅：

```dart
// 前端代码无需修改
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

### 环境要求

- Python 3.8+
- `volcengine-python-sdk[ark]` >= 1.0.0
- 环境变量：
  - `DOUBAO_API_KEY`
  - `DOUBAO_MODEL`

### 测试方法

```bash
# 运行测试脚本
cd backend/worker/workers/accumulated_mistakes_analyzer
python test_stream.py
```

### 已知限制

1. **更新频率固定**：目前为 0.5 秒，如需调整需修改代码
2. **网络依赖**：需要稳定的网络连接到火山引擎 API
3. **错误恢复**：如果中途失败，需要重新开始（不支持断点续传）

### 未来改进

- [ ] 支持可配置的更新频率
- [ ] 添加断点续传能力
- [ ] 支持更细粒度的进度反馈
- [ ] 添加流式输出的性能监控

### 向后兼容性

✅ **完全兼容**：前端无需修改，数据库结构无变化

### 贡献者

- 实现：AI Assistant
- 时间：2025-01-XX

---

## 升级指南

### 对于 Worker 部署

1. **更新代码**
   ```bash
   git pull origin main
   ```

2. **确保依赖已安装**
   ```bash
   pip install -r requirements.txt
   ```

3. **验证环境变量**
   ```bash
   echo $DOUBAO_API_KEY
   echo $DOUBAO_MODEL
   ```

4. **运行测试**
   ```bash
   cd workers/accumulated_mistakes_analyzer
   python test_stream.py
   ```

5. **重启 Worker**
   ```bash
   # 根据您的部署方式重启
   systemctl restart worker
   # 或
   docker-compose restart worker
   ```

### 对于前端

**无需任何操作**，前端代码保持不变。

### 验证升级成功

1. 触发一次积累错题分析
2. 观察前端是否实时显示内容
3. 检查更新频率是否符合预期（约 0.5 秒一次）
4. 查看 Worker 日志确认无错误

---

## 回滚方案

如果新版本出现问题，可以回滚到旧版本：

```bash
# 回退到上一个版本
git checkout <previous-commit>

# 或者临时禁用流式输出
# 在 worker.py 中将 stream=True 改为 stream=False
```

