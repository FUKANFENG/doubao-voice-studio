"""Chat contracts, persistence, interruption, and upstream SSE without real credentials."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import chat_api
from backend.chat_api import ChatStore, SendMessage
from backend.chat_client import ChatError, stream_reply
from backend.main import app
from backend.tts_route import require_auth
from doubao_voice import Auth


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


class ChatContractTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = ChatStore(Path(self.folder.name))
        self.patch = patch.object(chat_api, "store", self.store)
        self.patch.start()
        self.client = TestClient(app)  # No lifespan: never probe the real account.
        app.dependency_overrides[require_auth] = lambda: object()

    def tearDown(self):
        app.dependency_overrides.pop(require_auth, None)
        self.client.close()
        self.patch.stop()
        self.folder.cleanup()

    def test_multiturn_reuses_upstream_id_and_history_survives_restart(self):
        calls = []
        async def reply(auth, text, conversation_id, local_id):
            calls.append((text, conversation_id, local_id))
            yield {"type": "metadata", "conversation_id": "upstream-123"}
            yield {"type": "text", "text": "你"}
            yield {"type": "text", "text": "你好"}
        created = self.client.post("/api/chat/sessions").json()
        session_id = created["id"]
        endpoint = f"/api/chat/sessions/{session_id}/messages"
        with patch.object(chat_api, "stream_reply", reply):
            response = self.client.post(endpoint, json={"text": "你好", "request_id": "first"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            received = events(response)
            self.assertEqual([e["type"] for e in received], ["session", "text", "text", "done"])
            self.assertEqual(received[-1]["session"]["messages"][-1]["content"], "你好")
            self.assertFalse(received[-1]["session"]["generating"])
            repeated = self.client.post(endpoint, json={"text": "你好", "request_id": "first"})
            self.assertEqual(len(events(repeated)[-1]["session"]["messages"]), 2)
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.client.post(endpoint, json={"text": "不同内容", "request_id": "first"}).status_code, 409)
            restored = ChatStore(Path(self.folder.name))
            with patch.object(chat_api, "store", restored):
                second = self.client.post(endpoint, json={"text": "继续", "request_id": "second"})
            self.assertEqual(len(events(second)[-1]["session"]["messages"]), 4)
        self.assertEqual(calls[0][1], "0")
        self.assertEqual(calls[1][1], "upstream-123")
        self.assertEqual(calls[0][2], calls[1][2])
        public = self.client.get(f"/api/chat/sessions/{session_id}").json()
        self.assertNotIn("upstream_conversation_id", public)
        self.assertNotIn("cookie", response.text)
        self.assertEqual(len(self.client.get("/api/chat/sessions").json()), 1)
        if os.name == "posix":  # Windows ACLs are not represented by POSIX mode bits.
            self.assertEqual((Path(self.folder.name) / (session_id + ".json")).stat().st_mode & 0o777, 0o600)

    def test_upstream_failure_keeps_partial_reply_and_releases_conversation(self):
        async def broken(*args):
            yield {"type": "text", "text": "已收到的部分"}
            raise ChatError("豆包要求人工验证。")
        session_id = self.client.post("/api/chat/sessions").json()["id"]
        with patch.object(chat_api, "stream_reply", broken):
            response = self.client.post(f"/api/chat/sessions/{session_id}/messages", json={"text": "测试", "request_id": "error"})
        final = events(response)[-1]["session"]
        self.assertFalse(final["generating"])
        self.assertEqual(final["messages"][-1]["status"], "error")
        self.assertEqual(final["messages"][-1]["content"], "已收到的部分")
        self.assertIn("人工验证", final["messages"][-1]["error"])
        restored = ChatStore(Path(self.folder.name)).get(session_id)
        self.assertEqual(restored.messages[-1].content, "已收到的部分")

    def test_validation_and_busy_session_do_not_append_messages(self):
        session_id = self.client.post("/api/chat/sessions").json()["id"]
        endpoint = f"/api/chat/sessions/{session_id}/messages"
        self.assertEqual(self.client.post(endpoint, json={"text": " ", "request_id": "blank"}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, json={"text": "x" * 12001, "request_id": "long"}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, json={"text": "x", "request_id": ""}).status_code, 422)
        self.store.active.add(session_id)
        self.assertEqual(self.client.post(endpoint, json={"text": "x", "request_id": "busy"}).status_code, 409)
        self.assertEqual(self.store.get(session_id).messages, [])
        self.assertEqual(self.client.get("/api/chat/sessions/unknown").status_code, 404)


class ChatAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_keeps_partial_text_and_restart_recovers_interrupted_reply(self):
        async def reply(*args):
            yield {"type": "metadata", "conversation_id": "native-1"}
            yield {"type": "text", "text": "保留这段回复"}
            await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as folder:
            store = ChatStore(Path(folder))
            session = store.create()
            with patch.object(chat_api, "store", store), patch.object(chat_api, "stream_reply", reply):
                response = await chat_api.send_message(session.id, SendMessage(text="测试中断", request_id="stop"), object())
                stream = response.body_iterator
                await anext(stream)  # session
                await anext(stream)  # partial answer
                waiting = asyncio.create_task(anext(stream))
                await asyncio.sleep(0)
                waiting.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiting
                self.assertFalse(store.active)
                self.assertEqual(session.messages[-1].status, "stopped")
                self.assertEqual(session.messages[-1].content, "保留这段回复")
            session.messages[-1].status = "streaming"  # Simulate an abrupt process exit.
            store.save(session)
            recovered = ChatStore(Path(folder)).get(session.id)
            self.assertEqual(recovered.upstream_conversation_id, "native-1")
            self.assertEqual(recovered.messages[-1].status, "stopped")
            self.assertEqual(recovered.messages[-1].content, "保留这段回复")

    async def test_upstream_delta_snapshot_and_incomplete_stream(self):
        def event(kind, detail):
            return ("data: " + json.dumps({"event_type": kind, "event_data": json.dumps(detail)}) + "\n").encode()
        lines = [event(2002, {"conversation_id": "42"}),
                 event(2001, {"message": {"content_type": 2001, "content": '{"text":"hello"}'}, "is_delta": True}),
                 event(2001, {"message": {"content_type": 2001, "content": '{"text":"hello world"}'}, "is_delta": False}),
                 event(2003, {})]
        payloads = []
        class Response:
            status = 200
            content_type = "text/event-stream"
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            @property
            def content(self):
                async def iterator():
                    for line in lines: yield line
                return iterator()
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def post(self, *args, **kwargs):
                payloads.append(kwargs["json"])
                return Response()
        with patch("backend.chat_client.aiohttp.ClientSession", Client):
            result = [e async for e in stream_reply(Auth(cookie="fake"), "你好", "42", "local_test")]
            self.assertEqual([e["text"] for e in result if e["type"] == "text"], ["hello", "hello world"])
            self.assertEqual(payloads[0]["conversation_id"], "42")
            self.assertFalse(payloads[0]["completion_option"]["need_create_conversation"])
            lines.pop()
            with self.assertRaises(ChatError):
                _ = [e async for e in stream_reply(Auth(cookie="fake"), "你好", "0", "local_new")]


if __name__ == "__main__":
    unittest.main()
