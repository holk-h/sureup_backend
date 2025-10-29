# 快速开始指南

3步完成数据库初始化 🚀

## 方式一：使用Makefile（推荐）

如果你的系统支持 `make`（macOS/Linux 默认支持）：

```bash
cd backend

# 1. 设置环境（创建venv + 安装依赖）
make setup

# 2. 配置 .env 文件
cp .env.example .env
# 编辑 .env 填写你的配置

# 3. 初始化数据库
make init

# 4. （可选）验证
make verify

# 5. （可选）导入种子数据
make seed
```

查看所有可用命令：
```bash
make help
```

---

## 方式二：手动执行

## 步骤1：设置Python虚拟环境

使用venv创建独立的Python环境：

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# macOS/Linux:
source .venv/bin/activate

# Windows:
# .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

**提示**：每次运行脚本前，记得激活虚拟环境。

## 步骤2：配置环境变量

复制示例文件并填写你的配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your-project-id        # 从Appwrite Console获取
APPWRITE_API_KEY=your-api-key-here         # 从Appwrite Console获取
```

### 如何获取配置信息？

1. 访问 [Appwrite Console](https://cloud.appwrite.io)
2. 创建或选择项目
3. 复制 **Project ID**
4. 前往 **Settings → API Keys** 创建新的API Key（选择所有权限）

## 步骤3：初始化数据库

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 加载环境变量并运行初始化脚本
# macOS/Linux:
export $(cat .env | xargs) && python init_database.py

# 或者直接在命令行设置：
APPWRITE_ENDPOINT="https://cloud.appwrite.io/v1" \
APPWRITE_PROJECT_ID="your-project-id" \
APPWRITE_API_KEY="your-api-key" \
python init_database.py
```

等待脚本执行完成（约1-2分钟），你将看到：

```
✅ 数据库创建成功: 稳了！主数据库
✅ 集合创建成功: 用户档案
✅ 集合创建成功: 知识点
...
✅ 数据库初始化完成！
```

## 步骤4（可选）：验证安装

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

python verify_database.py
```

查看详细信息：

```bash
python verify_database.py --details
```

## 步骤5（可选）：导入种子数据

导入预置的知识点数据（约100+个常见知识点）：

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

python seed_knowledge_points.py
```

这将导入约100+个常见知识点（数学、物理、化学、生物）。

---

## 完成！🎉

现在你可以：

1. ✅ 在 [Appwrite Console](https://cloud.appwrite.io) 中查看数据库结构
2. ✅ 查看 [数据库设计文档](../doc/design/05_database_schema.md)
3. ✅ 开始开发云函数 (见 `functions/` 目录)
4. ✅ 集成前端 Flutter 应用

---

## 🛠️ 开发工具

### Makefile 命令

```bash
make setup          # 设置虚拟环境和依赖
make init           # 初始化数据库
make verify         # 验证数据库配置
make verify-detail  # 验证（详细模式）
make seed           # 导入种子数据
make clean          # 清理临时文件
make clean-all      # 完全清理（包括venv）
```

### 虚拟环境管理

```bash
# 激活环境
source .venv/bin/activate

# 退出环境
deactivate
```

---

## 常见问题

### Q: 初始化失败怎么办？

**A**: 检查以下几点：
- API Key是否有足够权限
- Project ID是否正确
- 网络连接是否正常
- 是否已安装依赖 `pip install -r requirements.txt`

### Q: 如何重新初始化？

**A**: 在 Appwrite Console 中手动删除数据库，然后重新运行脚本。

### Q: 本地开发如何配置？

**A**: 如果使用本地Appwrite：

```bash
APPWRITE_ENDPOINT=http://localhost/v1
APPWRITE_PROJECT_ID=your-local-project-id
APPWRITE_API_KEY=your-local-api-key
```

### Q: 如何备份数据？

**A**: Appwrite Console → Databases → Export，或使用API批量导出。

---

## 下一步

- 📖 阅读 [数据库设计文档](../doc/design/05_database_schema.md)
- 💻 查看 [使用示例](./USAGE_EXAMPLES.md)
- 🔧 开发 [云函数](./functions/README.md)
- 📱 集成 [Flutter前端](../frontend/README.md)

---

**遇到问题？** 查看 [README.md](./README.md) 或提Issue

