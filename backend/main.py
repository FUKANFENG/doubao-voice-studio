"""FastAPI app 入口。

阶段0：仅 /api/health 端点 + 静态文件挂载占位。
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth_loader
from .config import FRONTEND_DIST, HOST, PORT
from .tts_route import router as tts_router
from .asr_ws import asr_endpoint
from .transcribe_api import router as transcribe_router
from .developer_docs import router as developer_router
from .chat_api import router as chat_router
from .auth_api import router as auth_router
from .api_models import HealthResponse
from fastapi import WebSocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时加载 auth + 握手自检
    await auth_loader.load_and_probe()
    from .transcribe.jobs import manager
    from .transcribe.pipeline import run_pipeline
    manager.start(run_pipeline)
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(
    title="豆包语音工作室 API", version="1.4.0", lifespan=lifespan,
    description="语音合成、实时听写、课程转录、豆包 AI 整理与多轮对话。完整文档见 /api/docs/markdown，"
                "Agent 入口见 /llms.txt。WebSocket /ws/asr 的帧协议见 Markdown 文档。"
                "本服务没有应用级 API Key；建议从项目后端调用，沿用部署层访问控制。",
    servers=[{"url": "/", "description": "当前服务（同源）"},
             {"url": "http://127.0.0.1:8000", "description": "服务所在电脑"}],
    openapi_tags=[
        {"name": "service", "description": "服务健康与音色"},
        {"name": "tts", "description": "文字转音频"},
        {"name": "transcribe", "description": "串行任务队列、文字稿、字幕和 AI 笔记"},
        {"name": "developer", "description": "开发文档和可运行示例"},
        {"name": "chat", "description": "复用豆包登录态的多轮对话与本机历史"},
    ],
)
app.include_router(tts_router)
app.include_router(transcribe_router)
app.include_router(developer_router)
app.include_router(chat_router)
app.include_router(auth_router)

# 放行所有 Host（单用户本地工具，uvicorn 0.46+ 默认开启 TrustedHost 校验会拒 WS）
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.websocket("/ws/asr")
async def ws_asr(websocket: WebSocket):
    await asr_endpoint(websocket)

# CORS（开发期：允许 5173 跨域调 8000；生产期同源不需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        f"http://{HOST}:{PORT}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["service"],
         summary="服务端登录态自检状态", operation_id="getHealth")
async def health():
    snap = auth_loader.get_snapshot()
    return {
        "ok": snap.loaded and snap.auth_ok,
        "ts": time.time(),
        "auth_loaded": snap.loaded,
        "auth_ok": snap.auth_ok,
        "auth_reason": snap.reason,
        "cookie_chars": snap.cookie_chars,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


# ====== 静态文件托管（生产模式，build 完 dist 后自动生效） ======
# 注意：必须放在最后，否则会拦掉 /api 和 /ws 路由
if FRONTEND_DIST.is_dir():
    log.info(f"挂载前端 dist: {FRONTEND_DIST}")
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = ""):
        """SPA fallback：非 /api /ws 请求都返 index.html。

        优先级：先检查 dist 根目录是否有这个文件（比如 /vite.svg），有就返；
        没有就返 index.html（让前端 router 处理）。
        """
        # 跳过 API 和 WS（实际不会到这里，因为已经 include_router 和 ws_decorator 先匹配）
        if full_path.startswith(("api/", "ws/", "assets/")):
            from fastapi import HTTPException
            raise HTTPException(404)

        # 静态文件（如 favicon.ico、robots.txt）
        candidate = (FRONTEND_DIST / full_path).resolve()
        if not candidate.is_relative_to(FRONTEND_DIST.resolve()):
            from fastapi import HTTPException
            raise HTTPException(404)
        if full_path and candidate.is_file():
            return FileResponse(candidate)

        # SPA fallback
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
