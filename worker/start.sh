#!/bin/bash

# Worker 启动脚本

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "错误: .env 文件不存在"
    echo "请先创建 .env 文件并配置必要的环境变量"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 启动 Worker（推荐方式）
echo "启动 SureUp Worker 系统..."
python3 run.py

