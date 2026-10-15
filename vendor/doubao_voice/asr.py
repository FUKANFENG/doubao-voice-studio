"""ASR：实时语音识别 (WebSocket 流式)。

协议要点（逆向自 flow-component-asr-service-sdk.be57b397.js）：
  - 上行：16kHz / 单声道 / 16bit-LE PCM 原始二进制帧，帧长 4096 字节 (2048 采样 ≈128ms)
  - 结束：发文本帧 {"event":"finish"}
  - 下行：文本 JSON 事件
      {"event":"result","result":{"Text":"..."}}
      {"event":"finish"}
      {"code":0}                       成功
      {"code":710010701}               超时
      {"code":710010702}               参数非法
"""
from __future__ import annotations

import asyncio
import json
import wave
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Iterable, List, Optional

from .common import (
    ASR_URL, Auth, CODE_OK, CODE_TIMEOUT, CODE_INVALID,
    FRAME_SAMPLES, SAMPLE_RATE, build_url, common_params, ws_connect,
)

FRAME_BYTES = FRAME_SAMPLES * 2  # 16bit -> 2 字节/采样


@dataclass
class AsrResult:
    text: str = ""
    code: int = CODE_OK
    segments: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.code == CODE_OK


def read_pcm(path: str) -> bytes:
    """读取音频：.pcm 直读原始字节；.wav 必须是 16k/单声道/16bit。"""
    if path.lower().endswith((".pcm", ".raw")):
        with open(path, "rb") as f:
            return f.read()
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as w:
            if (w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1
                    or w.getsampwidth() != 2):
                raise ValueError(
                    f"WAV 需为 {SAMPLE_RATE}Hz/单声道/16bit，实为 "
                    f"{w.getframerate()}Hz/{w.getnchannels()}ch/"
                    f"{w.getsampwidth() * 8}bit。请先转码：\n"
                    f"  ffmpeg -i in.wav -ar 16000 -ac 1 -f s16le out.pcm")
            return w.readframes(w.getnframes())
    raise ValueError("仅支持 .pcm / .raw / .wav")


def iter_frames(pcm: bytes, frame_bytes: int = FRAME_BYTES) -> Iterable[bytes]:
    for i in range(0, len(pcm), frame_bytes):
        yield pcm[i:i + frame_bytes]


def float_to_pcm16(samples: Iterable[float]) -> bytes:
    """Float32(-1..1) -> Int16-LE，复刻 app 的 floatTo16BitPCM。"""
    out = bytearray()
    for s in samples:
        v = int(s * 0x8000) if s < 0 else int(s * 0x7FFF)
        v = max(-32768, min(32767, v))
        out += v.to_bytes(2, "little", signed=True)
    return bytes(out)


class AsrClient:
    def __init__(self, auth: Auth, language: Optional[str] = None):
        self.auth = auth
        if language:
            self.auth.language = language

    def url(self) -> str:
        params = dict(common_params(self.auth), format="pcm")
        return build_url(ASR_URL, params)

    async def recognize_frames(
        self,
        frames: AsyncIterator[bytes],
        on_result: Optional[Callable[[str], None]] = None,
    ) -> AsrResult:
        url = self.url()
        res = AsrResult()
        last = ""  # 上一个 result 事件文本（豆包是累计式：新事件覆盖旧前缀）
        async with await ws_connect(url, self.auth) as ws:
            sender_done = asyncio.Event()

            async def pump():
                async for fr in frames:
                    if fr:
                        await ws.send(fr)
                await ws.send(json.dumps({"event": "finish"}))
                sender_done.set()

            send_task = asyncio.create_task(pump())
            try:
                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        continue  # 上行接口不会有二进制下行
                    try:
                        data = json.loads(msg)
                    except (ValueError, TypeError):
                        continue
                    ev = data.get("event")
                    if ev == "result":
                        txt = (data.get("result") or {}).get("Text", "")
                        if txt:
                            res.segments.append(txt)
                            if last and res.text.endswith(last):
                                res.text = res.text[:-len(last)] + txt
                            else:
                                res.text += txt
                            last = txt
                            if on_result:
                                on_result(txt)
                    elif ev == "finish":
                        break
                    elif "code" in data:
                        res.code = int(data["code"])
                        if res.code != CODE_OK:
                            res.error = {CODE_TIMEOUT: "timeout",
                                         CODE_INVALID: "invalid params"}.get(
                                             res.code, data.get("message", "unknown"))
                            break
            finally:
                send_task.cancel()
        return res

    async def recognize_pcm(self, pcm: bytes,
                            on_result: Optional[Callable[[str], None]] = None,
                            fast: bool = False) -> AsrResult:
        """把整段 PCM 切成帧后流式发送。fast=True 时不加帧间延时。"""
        frame_bytes = FRAME_BYTES

        async def gen() -> AsyncIterator[bytes]:
            for i in range(0, len(pcm), frame_bytes):
                yield pcm[i:i + frame_bytes]
                if not fast:
                    await asyncio.sleep(0)  # 让出事件循环，模拟实时
        return await self.recognize_frames(gen(), on_result=on_result)

    def recognize_file(self, path: str,
                       on_result: Optional[Callable[[str], None]] = None,
                       fast: bool = False) -> AsrResult:
        """同步入口：识别一个 .pcm / .wav 文件。"""
        return asyncio.run(self.recognize_pcm(read_pcm(path),
                                              on_result=on_result, fast=fast))


def _ffmpeg_to_pcm(path: str) -> bytes:
    """用 ffmpeg 把任意音频转成 16k/mono/s16le，写到 stdout（不留临时文件）。"""
    import shutil
    import subprocess

    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "非 WAV/PCM 音频需要 ffmpeg 转码。可上传 16k/单声道/16bit 的 .wav，"
            "或安装 ffmpeg。")
    proc = subprocess.run(
        [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", path,
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True)
    return proc.stdout


def load_any(path: str) -> bytes:
    """尽量把任意音频读成 16k/mono/s16le PCM。"""
    if path.lower().endswith((".pcm", ".raw", ".wav")):
        try:
            return read_pcm(path)
        except ValueError:
            return _ffmpeg_to_pcm(path)
    return _ffmpeg_to_pcm(path)
