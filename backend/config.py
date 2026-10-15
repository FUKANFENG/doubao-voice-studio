"""路径常量。
加载仓库内附的 SDK，auth.json 使用项目根目录的私有配置。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 项目根：backend 的上一级
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# auth.json 在项目根
AUTH_PATH = PROJECT_ROOT / "auth.json"

# The bundled client makes a fresh clone independent of local directory links.
SDK_DIR = PROJECT_ROOT / "vendor"
if SDK_DIR.is_dir() and str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))

# 前端 build 产物
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

# 服务端口（监听 0.0.0.0 让局域网/内网穿透能访问）
HOST = "0.0.0.0"
PORT = 8000
