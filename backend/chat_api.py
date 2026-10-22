"""Local conversation history and an SSE proxy; credentials never reach the browser."""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .chat_client import ChatError, stream_reply
from .config import PROJECT_ROOT
from .tts_route import require_auth

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str = ""
    status: Literal["done", "streaming", "stopped", "error"] = "done"
    error: str = ""
    created_at: float
    request_id: str


class SessionInfo(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float
    generating: bool


class SessionDetail(SessionInfo):
    messages: list[Message]


class StoredSession(BaseModel):
    id: str
    title: str = "新对话"
    created_at: float
    updated_at: float
    messages: list[Message] = Field(default_factory=list)
    upstream_conversation_id: str = "0"
    local_conversation_id: str = Field(default_factory=lambda: "local_" + uuid.uuid4().hex)


class SendMessage(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class ChatStore:
    def __init__(self, folder: Path):
        self.folder = folder
        self.sessions: dict[str, StoredSession] = {}
        self.active: set[str] = set()
        self.load()

    def load(self):
        for path in self.folder.glob("*.json"):
            try:
                session = StoredSession.model_validate_json(path.read_text(encoding="utf-8"))
                if path.stem != session.id or not session.id.isalnum():
                    continue
                interrupted = False
                for message in session.messages:
                    if message.status == "streaming":
                        message.status = "stopped"
                        message.error = "服务已重启，上一条回复已中断。"
                        interrupted = True
                self.sessions[session.id] = session
                if interrupted:
                    self.save(session)
            except (ValueError, OSError):
                log.warning("跳过无法读取的本地对话文件")

    def save(self, session: StoredSession):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.folder,
                                         suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(session.model_dump_json())
                file.close()
                temporary.replace(self.folder / (session.id + ".json"))
            finally:
                temporary.unlink(missing_ok=True)

    def create(self):
        now = time.time()
        session = StoredSession(id=uuid.uuid4().hex, created_at=now, updated_at=now)
        self.save(session)
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "对话不存在")
        return session

    def info(self, session: StoredSession):
        return {"id": session.id, "title": session.title, "created_at": session.created_at,
                "updated_at": session.updated_at, "generating": session.id in self.active}

    def detail(self, session: StoredSession):
        return {**self.info(session), "messages": [m.model_dump() for m in session.messages]}


store = ChatStore(PROJECT_ROOT / "chat_out" / "sessions")


@router.get("/sessions", response_model=list[SessionInfo], operation_id="listChatSessions",
            summary="本机对话列表")
async def list_sessions():
    return [store.info(s) for s in sorted(store.sessions.values(), key=lambda s: s.updated_at, reverse=True)]


@router.post("/sessions", response_model=SessionDetail, operation_id="createChatSession",
             summary="创建独立对话")
async def create_session():
    return store.detail(store.create())


@router.get("/sessions/{session_id}", response_model=SessionDetail, operation_id="getChatSession",
            summary="查看本机对话及消息")
async def get_session(session_id: str):
    return store.detail(store.get(session_id))


def sse(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


@router.post("/sessions/{session_id}/messages", response_class=StreamingResponse,
             operation_id="sendChatMessage", summary="发送消息并流式接收回复",
             responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
                        409: {"description": "正在回复，或 request_id 已用于不同内容"},
                        503: {"description": "登录态不可用"}})
async def send_message(session_id: str, request: SendMessage, auth=Depends(require_auth)):
    session = store.get(session_id)
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    if session_id in store.active:
        raise HTTPException(409, "这段对话正在回复，请等待完成或停止后继续。")
    previous = next((m for m in session.messages if m.role == "user" and m.request_id == request.request_id), None)
    if previous:
        if previous.content != text:
            raise HTTPException(409, "request_id 已用于其他消息，请使用新的标识。")
        async def replay():
            yield sse({"type": "done", "session": store.detail(session)})
        return StreamingResponse(replay(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    now = time.time()
    user = Message(id=uuid.uuid4().hex, role="user", content=text, created_at=now, request_id=request.request_id)
    answer = Message(id=uuid.uuid4().hex, role="assistant", status="streaming", created_at=now,
                     request_id=request.request_id)
    if not session.messages:
        session.title = " ".join(text.split())[:28]
    session.messages.extend([user, answer])
    session.updated_at = now
    store.active.add(session_id)
    try:
        store.save(session)
    except OSError:
        store.active.discard(session_id)
        session.messages = session.messages[:-2]
        raise HTTPException(500, "无法保存对话，请检查本机磁盘空间。")

    async def generate():
        last_saved = time.monotonic()
        try:
            yield sse({"type": "session", "session": store.detail(session)})
            async for event in stream_reply(auth, text, session.upstream_conversation_id,
                                             session.local_conversation_id):
                if event["type"] == "metadata":
                    upstream_id = event["conversation_id"]
                    if upstream_id != session.upstream_conversation_id:
                        session.upstream_conversation_id = upstream_id
                        store.save(session)
                elif event["type"] == "text":
                    answer.content = event["text"]
                    if time.monotonic() - last_saved >= 0.5:
                        store.save(session)
                        last_saved = time.monotonic()
                    yield sse({"type": "text", "message_id": answer.id, "text": answer.content})
            answer.status = "done"
        except asyncio.CancelledError:
            answer.status = "stopped"
            answer.error = "已停止接收回复。"
            raise
        except ChatError as error:
            answer.status = "error"
            answer.error = str(error)
        except Exception as error:
            log.warning("对话回复异常: %s", type(error).__name__)
            answer.status = "error"
            answer.error = "回复暂时失败，已保留对话，请稍后再试。"
        finally:
            if answer.status == "streaming":
                answer.status = "stopped"
                answer.error = "已停止接收回复。"
            store.active.discard(session_id)
            session.updated_at = time.time()
            store.save(session)
        yield sse({"type": "done", "session": store.detail(session)})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
