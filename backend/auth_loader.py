"""auth.json 单例加载 + 启动握手自检。

启动时做一次 TTS 握手（合成一个空格）验证登录态是否有效。
握手失败时把 reason 存到全局状态，/api/health 返回 auth_ok=false。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from .config import AUTH_PATH

log = logging.getLogger("auth_loader")

_auth_state: dict = {
    "loaded": False,
    "auth": None,         # Auth 实例
    "auth_ok": False,
    "reason": "",
    "loaded_at": 0.0,
    "cookie_chars": 0,
}


@dataclass
class AuthSnapshot:
    loaded: bool
    auth_ok: bool
    reason: str
    loaded_at: float
    cookie_chars: int


def get_snapshot() -> AuthSnapshot:
    return AuthSnapshot(
        loaded=_auth_state["loaded"],
        auth_ok=_auth_state["auth_ok"],
        reason=_auth_state["reason"],
        loaded_at=_auth_state["loaded_at"],
        cookie_chars=_auth_state["cookie_chars"],
    )


def get_auth():
    """获取已加载的 Auth 对象（不健全！请求处理时再用）。"""
    return _auth_state["auth"]


def activate(auth) -> None:
    """Install an already verified, persisted account without restarting tasks."""
    _auth_state.update(auth=auth, loaded=True, auth_ok=True, reason="",
                       loaded_at=time.time(), cookie_chars=len(auth.cookie))


async def _probe_tts_handshake(auth) -> tuple[bool, str]:
    """启动时做一次 TTS 握手（合成单字节文本）验证登录态。

    成功：(True, "")
    失败：(False, "原因")
    """
    from doubao_voice import TtsClient  # 注入后才可 import

    try:
        client = TtsClient(auth, speaker="", fmt="aac", speech_rate=1.0, pitch=0)
        # 合成短句触发真实握手（用 probe.py 验过的文本）
        chunks = await asyncio.wait_for(client.synthesize("你好呀，这是联调测试。"), timeout=10.0)
        # 累计到一定字节数算成功
        total = sum(len(c.audio) for c in chunks)
        if total > 100:
            return True, ""
        return False, f"TTS 响应字节数过少 ({total})"
    except asyncio.TimeoutError:
        return False, "TTS 握手超时（10s）"
    except Exception as e:
        return False, f"TTS 握手失败: {type(e).__name__}: {e}"


async def load_and_probe() -> None:
    """加载 auth.json + 握手自检。失败也不抛，存到 _auth_state。"""
    from doubao_voice import Auth  # 注入后才可 import

    _auth_state["loaded_at"] = time.time()

    if not AUTH_PATH.is_file():
        _auth_state["reason"] = f"auth.json 不存在: {AUTH_PATH}"
        log.error(_auth_state["reason"])
        return

    try:
        auth = Auth.load(str(AUTH_PATH))
    except Exception as e:
        _auth_state["reason"] = f"auth.json 解析失败: {e}"
        log.error(_auth_state["reason"])
        return

    if not auth.cookie:
        _auth_state["reason"] = "auth.json 中 cookie 为空"
        log.error(_auth_state["reason"])
        return

    _auth_state["auth"] = auth
    _auth_state["loaded"] = True
    _auth_state["cookie_chars"] = len(auth.cookie)
    log.info(f"auth.json 加载成功，cookie {len(auth.cookie)} 字符")

    # 握手自检（带超时保护）
    log.info("启动 TTS 握手自检...")
    ok, reason = await _probe_tts_handshake(auth)
    _auth_state["auth_ok"] = ok
    _auth_state["reason"] = reason
    if ok:
        log.info("✅ TTS 握手自检通过")
    else:
        log.warning(f"❌ TTS 握手自检失败: {reason}")


def reload() -> None:
    """重置状态（供调试 / 手动触发）。"""
    _auth_state["loaded"] = False
    _auth_state["auth"] = None
    _auth_state["auth_ok"] = False
    _auth_state["reason"] = ""
