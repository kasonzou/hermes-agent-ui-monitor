#!/bin/bash

# Hermes Monitor API 启动脚本

set -e

# 默认配置
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
WORKERS=${WORKERS:-1}
LOG_LEVEL=${LOG_LEVEL:-info}

echo "Starting Hermes Monitor API..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"

# 启动 uvicorn
exec uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL" \
    --access-log
