"""POST /api/tts — 文本 → 音频流。

策略：
  - TtsClient.synthesize 内部用 on_audio 同步回调 → 不适合 async 流
  - 改成自己跑 ws_connect 内部循环 + asyncio.Queue 在两个 task 间传帧
  - StreamingResponse 从 queue 逐块 yield 给前端
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import auth_loader
from .api_models import SpeakersResponse, CodedError
from .errors import (
    ERR_INVALID_PARAM, ERR_INVALID_TEXT, ERR_UPSTREAM_FAILED,
    ERR_AUTH_EXPIRED, http_error,
)

log = logging.getLogger("tts_route")

router = APIRouter()

# format → MIME 类型
FORMAT_MIME = {
    "aac": "audio/aac",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg; codecs=opus",
    "pcm": "audio/pcm",
}

# 支持的 format 白名单
ALLOWED_FORMATS = set(FORMAT_MIME.keys())


# ====== 请求体 ======
class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="要合成的文本")
    speaker: str = Field(default="", description="音色 ID，空则用豆包默认")
    format: str = Field(default="aac", description="输出格式: aac|mp3|opus|pcm",
                        json_schema_extra={"enum": ["aac", "mp3", "opus", "pcm"]})
    speech_rate: float = Field(default=1.0, ge=0.7, le=2.0, description="语速 0.7~2.0")
    pitch: int = Field(default=0, ge=-10, le=10, description="音高 -10~10")


# ====== 鉴权依赖 ======
def require_auth():
    snap = auth_loader.get_snapshot()
    if not snap.loaded:
        raise http_error(ERR_AUTH_EXPIRED, f"auth.json 未加载: {snap.reason}", 503)
    if not snap.auth_ok:
        raise http_error(ERR_AUTH_EXPIRED, f"登录态失效: {snap.reason}", 503)
    return auth_loader.get_auth()


# ====== 内部流式合成 ======
async def _tts_stream(req: TtsRequest, auth) -> AsyncIterator[bytes]:
    """用 asyncio.Queue 把豆包 TTS 的二进制帧异步推给 StreamingResponse。

    设计：两个协程：
      - 上游任务：跑豆包 TTS 内部循环，二进制帧塞 queue；文本事件单独处理
      - 下游（gen）：从 queue 取出 yield
    终止：上游放 None 进 queue 作为哨兵
    """
    from doubao_voice import TtsClient
    from doubao_voice.common import ws_connect

    client = TtsClient(
        auth,
        speaker=req.speaker,
        fmt=req.format,
        speech_rate=req.speech_rate,
        pitch=req.pitch,
    )
    url = client.url()

    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=64)
    error_holder: dict = {"err": None}

    async def upstream_task():
        try:
            async with await ws_connect(url, auth) as ws:
                await ws.send(json.dumps({"event": "text", "text": req.text}))
                await ws.send(json.dumps({"event": "finish"}))
                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        await queue.put(bytes(msg))
                    else:
                        try:
                            data = json.loads(msg)
                        except (ValueError, TypeError):
                            continue
                        ev = data.get("event")
                        if ev == "finish":
                            break
                        elif "code" in data and int(data.get("code", 0)) != 0:
                            error_holder["err"] = (
                                int(data["code"]), data.get("message", "unknown")
                            )
                            break
        except Exception as e:
            error_holder["err"] = (0, f"{type(e).__name__}: {e}")
        finally:
            await queue.put(None)  # 哨兵

    task = asyncio.create_task(upstream_task())
    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                # 上游结束
                break
            yield chunk
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # 上游错误检查
    if error_holder["err"]:
        code, msg = error_holder["err"]
        # 已经 yield 完了，不能再抛 HTTPException；只能记日志
        log.warning(f"TTS upstream error: code={code} msg={msg}")


# ====== 端点 ======
@router.post("/api/tts", tags=["tts"], summary="合成语音（返回音频字节流）",
             operation_id="synthesizeSpeech", response_class=StreamingResponse,
             responses={
                 200: {"description": "音频字节流。流开始后上游错误无法改成 HTTP 错误码。",
                       "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                   for mime in FORMAT_MIME.values()}},
                 400: {"model": CodedError, "description": "空白文本或不支持的格式"},
                 503: {"model": CodedError, "description": "服务端登录态不可用"},
             })
async def synthesize(req: TtsRequest, auth=Depends(require_auth)):
    # 1. 参数校验
    if not req.text or not req.text.strip():
        raise http_error(ERR_INVALID_TEXT, "文本不能为空", 400)
    if len(req.text) > 2000:
        raise http_error(ERR_INVALID_TEXT, "文本不能超过 2000 字符", 400)
    if req.format not in ALLOWED_FORMATS:
        raise http_error(
            ERR_INVALID_PARAM,
            f"format 必须是 {sorted(ALLOWED_FORMATS)}，got {req.format}",
            400,
        )

    mime = FORMAT_MIME[req.format]
    log.info(f"TTS: {req.text[:30]!r}... speaker={req.speaker!r} fmt={req.format}")

    return StreamingResponse(
        _tts_stream(req, auth),
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲（虽然我们没用 nginx）
        },
    )


# ====== 音色列表 ======
@router.get("/api/speakers", response_model=SpeakersResponse, tags=["service"],
            summary="列出可选音色", operation_id="listSpeakers")
async def list_speakers():
    """返回可用音色列表（写死，跟原 SDK README 一致）。"""
    return {
        "default": "zh_female_taozi_conversation_v4_wvae_bigtts",
        "speakers": [
            {"id": "zh_female_taozi_conversation_v4_wvae_bigtts", "name": "温柔桃子（豆包默认）"},
            {"id": "zh_male_wennuanahu_moon_bigtts", "name": "温暖阿虎"},
            {"id": "zh_female_wanwanxiaohe_moon_bigtts", "name": "湾湾小何"},
            {"id": "zh_male_beijingxiaoye_moon_bigtts", "name": "北京小爷"},
        ],
    }
