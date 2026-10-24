#!/bin/zsh
set -euo pipefail

# 可双击启动的 macOS 入口。项目移动后仍可用：以本脚本位置推导项目目录。
SCRIPT_DIR="${0:A:h}"
ROOT="$SCRIPT_DIR"
PYTHON="$ROOT/.venv/bin/python"
PORT="${DOUBAO_VOICE_PORT:-8000}"
URL="http://127.0.0.1:$PORT"
PID_FILE="$ROOT/logs/local-server.pid"
PORT_FILE="$ROOT/logs/local-server.port"
LOG_FILE="$ROOT/logs/server.log"

if [[ ! -x "$PYTHON" ]]; then
  print -u2 "找不到项目虚拟环境：$PYTHON"
  print -u2 "请先完成一次本地部署。"
  exit 1
fi
if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  print -u2 "找不到前端构建文件，请先在项目目录执行 npm run build --prefix frontend。"
  exit 1
fi

export PATH="$ROOT/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

health_ok() {
  "$PYTHON" - "$URL" <<'PY'
import json, sys, urllib.request
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(sys.argv[1] + "/api/health", timeout=2) as response:
        body = json.load(response)
    raise SystemExit(0 if body.get("ok") else 2)
except Exception:
    raise SystemExit(2)
PY
}

is_our_process() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  local command
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command" == *"$ROOT/.venv/bin/python"* && "$command" == *"uvicorn backend.main:app"* ]]
}

mkdir -p "$ROOT/logs"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if is_our_process "$existing_pid"; then
    existing_port="$(ps -p "$existing_pid" -o command= | sed -n 's/.*--port \([0-9][0-9]*\).*/\1/p')"
    if [[ "$existing_port" == <-> ]]; then
      PORT="$existing_port"
      URL="http://127.0.0.1:$PORT"
    elif [[ -f "$PORT_FILE" ]]; then
      PORT="$(cat "$PORT_FILE")"
      URL="http://127.0.0.1:$PORT"
    fi
    for _ in {1..60}; do
      if health_ok; then
        print "豆包语音工作室已经在运行：$URL"
        open "$URL"
        exit 0
      fi
      sleep 0.5
    done
    print -u2 "已有服务进程但健康检查未通过，请查看日志：$LOG_FILE"
    exit 1
  else
    rm -f "$PID_FILE" "$PORT_FILE"
  fi
fi

if ! health_ok; then
  if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if ! is_our_process "$old_pid"; then
      rm -f "$PID_FILE" "$PORT_FILE"
    fi
  fi

  if ! health_ok; then
    while command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
      PORT=$((PORT + 1))
      URL="http://127.0.0.1:$PORT"
    done
    if [[ "$PORT" != "${DOUBAO_VOICE_PORT:-8000}" ]]; then
      print "8000 已被其他服务占用，本工作台改用 $PORT。"
    fi
    DOUBAO_ACTIVE_PORT="$PORT" "$PYTHON" - "$ROOT" "$LOG_FILE" "$PID_FILE" "$PORT_FILE" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
log_file = Path(sys.argv[2])
pid_file = Path(sys.argv[3])
port_file = Path(sys.argv[4])
port = os.environ["DOUBAO_ACTIVE_PORT"]
with log_file.open("ab") as log:
    process = subprocess.Popen(
        [str(root / ".venv/bin/python"), "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", port, "--workers", "1"],
        cwd=root,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
pid_file.write_text(str(process.pid), encoding="utf-8")
port_file.write_text(port, encoding="utf-8")
PY
  fi
fi

for _ in {1..60}; do
  if health_ok; then
    print "豆包语音工作室已启动：$URL"
    print "登录态、豆包对话和本机历史会沿用现有配置。"
    open "$URL"
    exit 0
  fi
  sleep 0.5
done

print -u2 "服务启动超时，请查看日志：$LOG_FILE"
exit 1
