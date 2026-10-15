"""ASR 串行识别：每段 1 个 WebSocket session，串行处理。

直接复用 doubao_voice SDK 里的 AsrClient 和 ws_connect，不重新造轮子。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

import websockets

# 注入 SDK 路径
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_SDK_PATH = os.path.join(_PROJECT_ROOT, "doubao_voice_asr_tts")
if _SDK_PATH not in sys.path:
    sys.path.insert(0, _SDK_PATH)

from doubao_voice import AsrClient  # noqa: E402
from doubao_voice.common import ws_connect  # noqa: E402

from .chunker import AudioChunk, BYTES_PER_SEC

log = logging.getLogger("transcribe.recognizer")

FRAME_BYTES = 4096  # 2048 samples * 2 bytes


def _load_auth():
    from ..config import AUTH_PATH
    import json as _json
    with open(AUTH_PATH, "r", encoding="utf-8") as f:
        return _json.load(f)


async def _recognize_one(
    chunk: AudioChunk,
    auth,  # doubao_voice.Auth
    progress_cb=None,
) -> str:
    """识别一个 PCM 片段，返回该段文本。直接复用 SDK。"""
    file_size = os.path.getsize(chunk.pcm_path)
    if file_size == 0:
        return ""

    asr = AsrClient(auth)
    url = asr.url()
    log.info(f"[chunk {chunk.index:03d}] connecting... ({file_size} bytes, {chunk.duration_sec:.1f}s)")
    t0 = time.time()

    try:
        async with await ws_connect(url, auth) as ws:
            # 流式发音频帧
            with open(chunk.pcm_path, "rb") as f:
                while True:
                    buf = f.read(FRAME_BYTES)
                    if not buf:
                        break
                    if len(buf) < FRAME_BYTES:
                        buf = buf.ljust(FRAME_BYTES, b"\x00")
                    await ws.send(buf)
                    # 给服务端一点点处理时间，避免 burst
                    # 4096B / 16000Hz = 256ms/帧，但等这么久太慢；
                    # 1ms 足够防止被服务端误判为 burst
                    await asyncio.sleep(0.001)

            # 发 finish（SDK 原始 ASR 协议）
            import json
            await ws.send(json.dumps({"event": "finish"}))

            # 收结果
            final_text = ""
            last_partial = ""
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    raise RuntimeError(f"第 {chunk.index + 1} 段识别超时，请稍后重试")

                if isinstance(msg, (bytes, bytearray)):
                    continue
                try:
                    data = json.loads(msg)
                except (ValueError, TypeError):
                    continue

                ev = data.get("event")
                if ev == "result":
                    last_partial = (data.get("result") or {}).get("Text", "")
                    if progress_cb:
                        progress_cb(chunk.index, last_partial)
                elif ev == "finish":
                    break
                elif "code" in data and int(data.get("code", 0)) != 0:
                    raise RuntimeError(f"第 {chunk.index + 1} 段被上游拒绝（代码 {data.get('code')}），请稍后重试")

            elapsed = time.time() - t0
            log.info(f"[chunk {chunk.index:03d}] done in {elapsed:.1f}s, text len={len(last_partial)}")
            return last_partial

    except Exception as e:
        log.error(f"[chunk {chunk.index:03d}] failed: {type(e).__name__}: {e!r}")
        raise


async def recognize_all(
    chunks: list[AudioChunk],
    progress_cb=None,
    cooldown_sec: float = 1.0,
) -> list[str]:
    """串行识别所有片段。"""
    from doubao_voice import Auth

    auth_dict = _load_auth()
    auth = Auth(**{k: v for k, v in auth_dict.items() if k in ("cookie", "web_id", "tea_uuid", "language", "region", "proxy", "access_key", "overrides")})

    results: list[str] = []
    for i, chunk in enumerate(chunks):
        text = await _recognize_one(chunk, auth)
        results.append(text)
        if progress_cb:
            progress_cb(i + 1, len(chunks), text)
        if i < len(chunks) - 1:
            await asyncio.sleep(cooldown_sec)
    return results
