# 稳了！后端开发辅助命令

.PHONY: help setup init verify seed clean

help:
	@echo "稳了！后端开发命令"
	@echo ""
	@echo "使用方法: make [命令]"
	@echo ""
	@echo "可用命令:"
	@echo "  setup      - 设置Python虚拟环境并安装依赖"
	@echo "  init       - 初始化Appwrite数据库"
	@echo "  verify     - 验证数据库配置"
	@echo "  seed       - 导入知识点种子数据"
	@echo "  clean      - 清理临时文件和缓存"
	@echo ""
	@echo "示例:"
	@echo "  make setup   # 首次设置环境"
	@echo "  make init    # 初始化数据库"

setup:
	@echo "📦 设置Python虚拟环境..."
	python3 -m venv .venv
	@echo "✅ 虚拟环境创建完成"
	@echo ""
	@echo "📥 安装依赖..."
	.venv/bin/pip install -r requirements.txt
	@echo "✅ 依赖安装完成"
	@echo ""
	@echo "💡 提示："
	@echo "   请配置 .env 文件，然后运行: make init"
	@echo "   激活环境: source .venv/bin/activate"

init:
	@echo "🚀 初始化Appwrite数据库..."
	@if [ ! -f .env ]; then \
		echo "❌ 错误：.env 文件不存在"; \
		echo "   请从 .env.example 复制并配置"; \
		exit 1; \
	fi
	@. .venv/bin/activate && set -a && . .env && set +a && python init_database.py

verify:
	@echo "🔍 验证数据库配置..."
	@. .venv/bin/activate && set -a && . .env && set +a && python verify_database.py

verify-detail:
	@echo "🔍 验证数据库配置（详细模式）..."
	@. .venv/bin/activate && set -a && . .env && set +a && python verify_database.py --details

seed:
	@echo "🌱 导入知识点种子数据..."
	@. .venv/bin/activate && set -a && . .env && set +a && python seed_knowledge_points.py

clean:
	@echo "🧹 清理临时文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	@echo "✅ 清理完成"

clean-all: clean
	@echo "🗑️  删除虚拟环境..."
	rm -rf .venv
	@echo "✅ 完全清理完成"

