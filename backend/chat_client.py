"""Streaming Doubao conversations using the server's existing session."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import aiohttp

from .transcribe.summarizer import CHAT_URL, decode_event


class ChatError(RuntimeError):
    """An upstream failure safe to show to the local user."""


async def stream_reply(auth, text: str, conversation_id: str,
                       local_conversation_id: str) -> AsyncIterator[dict]:
    from doubao_voice.common import UA, common_params

    payload = {
        "messages": [{"content": json.dumps({"text": text}, ensure_ascii=False),
                      "content_type": 2001, "attachments": [], "references": []}],
        "completion_option": {"is_regen": False, "with_suggest": False,
                              "need_create_conversation": conversation_id == "0",
                              "launch_stage": 1, "is_replace": False, "is_delete": False,
                              "message_from": 0, "use_deep_think": False, "use_auto_cot": False},
        "evaluate_option": {"web_ab_params": ""},
        "conversation_id": conversation_id,
        "local_conversation_id": local_conversation_id,
        "local_message_id": str(uuid.uuid4()),
    }
    headers = {"Cookie": auth.cookie, "User-Agent": UA, "Origin": "https://www.doubao.com",
               "Referer": "https://www.doubao.com/chat/", "Accept-Encoding": "gzip, deflate",
               "agw-js-conv": "str, str"}
    timeout = aiohttp.ClientTimeout(total=180, connect=15, sock_read=60)
    answer = ""
    finished = False
    try:
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.post(CHAT_URL, params=common_params(auth), headers=headers,
                                   json=payload, proxy=auth.proxy or None) as response:
                if response.status != 200:
                    raise ChatError(f"豆包对话请求失败（HTTP {response.status}），请稍后再试。")
                if response.content_type != "text/event-stream":
                    raise ChatError("豆包未返回对话内容，请在豆包客户端检查登录或验证提示。")
                async for raw in response.content:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body:
                        continue
                    if body == "[DONE]":
                        finished = True
                        break
                    event = json.loads(body)
                    detail = event.get("event_data") or {}
                    detail = json.loads(detail) if isinstance(detail, str) else detail
                    if detail.get("conversation_id"):
                        yield {"type": "metadata", "conversation_id": str(detail["conversation_id"])}
                    try:
                        piece, delta, done = decode_event(body)
                    except RuntimeError as error:
                        raise ChatError(str(error)) from error
                    if piece:
                        answer = answer + piece if delta else piece
                        if len(answer) > 100_000:
                            raise ChatError("回复过长，已保留收到的内容，请缩小问题范围后继续。")
                        yield {"type": "text", "text": answer}
                    finished = finished or done
                    if event.get("event_type") == 2003:
                        break
        if not finished or not answer.strip():
            raise ChatError("回复未完整返回，已保留收到的内容，请稍后继续。")
    except (asyncio.TimeoutError, aiohttp.ClientError) as error:
        raise ChatError("豆包连接超时或网络中断，已保留收到的内容，请检查代理后再试。") from error
