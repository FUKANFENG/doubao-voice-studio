"""WS /ws/asr — 浏览器 ↔ FastAPI ↔ 豆包 双向中转。

设计：
  - 浏览器上行二进制 PCM 帧 + 文本 {"type":"finish"} → 透传/转译到豆包
  - 豆包下行 JSON result/finish/code 事件 → 转成 {type:partial|final|error} 推浏览器
  - 一旦任一方向异常，立即关闭整个会话（不自动重连）
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, status

from . import auth_loader
from .errors import ERR_AUTH_EXPIRED, ERR_UPSTREAM_FAILED, ERR_RATE_LIMITED

log = logging.getLogger("asr_ws")


# ====== 豆包 WS ↔ 浏览器 WS 协议转换 ======
async def _browser_to_doubao(client_ws: WebSocket, doubao_ws) -> None:
    """浏览器 → 豆包。

    浏览器上行：
      - binary ArrayBuffer: 4096 字节 PCM 帧 → 透传到豆包
      - text {"type":"finish"} → 转译为豆包 {"event":"finish"}
    """
    while True:
        try:
            msg = await client_ws.receive()
        except WebSocketDisconnect:
            log.info("asr: browser disconnected (uplink)")
            return
        except Exception as e:
            log.warning(f"asr: browser receive error: {e}")
            return

        if msg["type"] == "websocket.disconnect":
            log.info("asr: browser sent disconnect (uplink)")
            return

        if "bytes" in msg and msg["bytes"] is not None:
            await doubao_ws.send(msg["bytes"])
            continue

        if "text" in msg and msg["text"] is not None:
            try:
                data = json.loads(msg["text"])
            except (ValueError, TypeError):
                continue
            t = data.get("type")
            if t == "finish":
                await doubao_ws.send(json.dumps({"event": "finish"}))
            # 其它 type 忽略（前端误发的不要影响后端）
            continue


async def _doubao_to_browser(client_ws: WebSocket, doubao_ws) -> None:
    """豆包 → 浏览器。

    豆包下行：
      - {"event":"result","result":{"Text":"..."}} → {"type":"partial","text":...}
      - {"event":"finish"} → {"type":"final"} 然后结束
      - {"code":非0, "message":...} → {"type":"error","code":str(code),"message":...} 然后结束
    """
    while True:
        try:
            msg = await doubao_ws.recv()
        except Exception as e:
            log.warning(f"asr: doubao recv error: {e}")
            try:
                await client_ws.send_json({
                    "type": "error",
                    "code": "upstream_broken",
                    "message": f"豆包连接异常: {type(e).__name__}: {e}",
                })
            except Exception:
                pass
            return

        if isinstance(msg, (bytes, bytearray)):
            # ASR 接口不会有二进制下行
            continue

        try:
            data = json.loads(msg)
        except (ValueError, TypeError):
            continue

        ev = data.get("event")
        if ev == "result":
            txt = (data.get("result") or {}).get("Text", "")
            try:
                await client_ws.send_json({"type": "partial", "text": txt})
            except Exception:
                return
        elif ev == "finish":
            try:
                await client_ws.send_json({"type": "final"})
            except Exception:
                pass
            return
        elif "code" in data and int(data.get("code", 0)) != 0:
            code = int(data["code"])
            msg_text = data.get("message", "unknown")
            err_type = ERR_RATE_LIMITED if "too many" in msg_text.lower() else "upstream_error"
            try:
                await client_ws.send_json({
                    "type": "error",
                    "code": err_type,
                    "message": f"豆包 {code}: {msg_text}",
                })
            except Exception:
                pass
            return


# ====== 端点 ======
async def asr_endpoint(client_ws: WebSocket) -> None:
    """WS /ws/asr 入口。"""
    await client_ws.accept()
    from .asr_gate import asr_slot
    if asr_slot.locked():
        await client_ws.send_json({"type": "error", "code": "asr_busy",
                                   "message": "语音识别正在使用中，请等待当前转录或录音结束。"})
        await client_ws.close(code=1013)
        return
    async with asr_slot:
        await _relay_asr(client_ws)


async def _relay_asr(client_ws: WebSocket) -> None:

    # 鉴权
    snap = auth_loader.get_snapshot()
    if not snap.loaded or not snap.auth_ok:
        await client_ws.send_json({
            "type": "error",
            "code": ERR_AUTH_EXPIRED,
            "message": f"登录态失效: {snap.reason or '未加载'}",
        })
        await client_ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    auth = auth_loader.get_auth()

    # 延迟导入（启动握手已加载 SDK）
    from doubao_voice import AsrClient
    from doubao_voice.common import ws_connect

    # 建立上游豆包 WS
    asr = AsrClient(auth)
    upstream_url = asr.url()
    log.info(f"asr: connecting to upstream: {upstream_url[:120]}...")
    try:
        doubao_ws = await ws_connect(upstream_url, auth)
    except Exception as e:
        log.error(f"asr: upstream connect failed: {e}")
        await client_ws.send_json({
            "type": "error",
            "code": "upstream_connect_failed",
            "message": f"连不上豆包: {type(e).__name__}: {e}",
        })
        await client_ws.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    log.info("asr: upstream connected, both sides relaying")

    # 两个方向各起一个 task
    uplink = asyncio.create_task(_browser_to_doubao(client_ws, doubao_ws))
    downlink = asyncio.create_task(_doubao_to_browser(client_ws, doubao_ws))

    try:
        # 任一 task 结束就终止另一个
        done, pending = await asyncio.wait(
            {uplink, downlink},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        # 资源清理
        try:
            await doubao_ws.close()
        except Exception:
            pass
        try:
            await client_ws.close()
        except Exception:
            pass
        log.info("asr: session closed")
