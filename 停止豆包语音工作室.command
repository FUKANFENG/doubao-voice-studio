#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT="$SCRIPT_DIR"
PYTHON="$ROOT/.venv/bin/python"
PID_FILE="$ROOT/logs/local-server.pid"
PORT_FILE="$ROOT/logs/local-server.port"

if [[ ! -f "$PID_FILE" ]]; then
  rm -f "$PORT_FILE"
  print "没有找到本工具启动的服务。"
  exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
if [[ "$command" != *"$ROOT/.venv/bin/python"* || "$command" != *"uvicorn backend.main:app"* ]]; then
  rm -f "$PID_FILE" "$PORT_FILE"
  print "服务已停止。"
  exit 0
fi

kill "$pid" 2>/dev/null || true
for _ in {1..60}; do
  if ! ps -p "$pid" >/dev/null 2>&1; then
    rm -f "$PID_FILE" "$PORT_FILE"
    print "豆包语音工作室已停止。"
    exit 0
  fi
  sleep 0.5
done

print -u2 "服务仍在结束任务，请稍后重试。"
exit 1
