"""TTS：实时语音合成 (WebSocket 流式)。

协议要点（逆向自 async/22596.ce5c09a5.js）：
  - 连接：wss://ws-samantha.doubao.com/samantha/audio/tts?<urlencode(params)>
      params = {speaker, format:"aac", speech_rate, pitch, ...commonParams}
      speech_rate: 0.7~2.0 -> round((rate-1)*100)  即 -30..100
  - 上行：{"event":"text","text":"..."} 可多次；最后 {"event":"finish"}
  - 下行：二进制音频帧 (format 指定容器) + 文本 JSON 事件
      {"event":"sentence_start","sentence_start_result":{"readable_text":"..."}}
      {"event":"sentence_end"}
      {"event":"finish"}
      {"code":..,"message":".."}   错误
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .common import TTS_URL, Auth, build_url, common_params, ws_connect


@dataclass
class TtsChunk:
    """按句聚合的一段合成音频。"""
    text: str
    audio: bytes


def real_speech_rate(rate: float) -> int:
    """复刻 getRealSpeechRate()。"""
    if 0.7 <= rate <= 2.0:
        return round((rate - 1) * 100)
    return 0


class TtsClient:
    def __init__(self, auth: Auth, speaker: str = "", fmt: str = "aac",
                 speech_rate: float = 1.0, pitch: int = 0):
        self.auth = auth
        self.speaker = speaker
        self.fmt = fmt
        self.speech_rate = speech_rate
        self.pitch = pitch

    def url(self) -> str:
        params = dict(common_params(self.auth), **{
            "speaker": self.speaker or "",
            "format": self.fmt,
            "speech_rate": real_speech_rate(self.speech_rate),
            "pitch": self.pitch,
        })
        return build_url(TTS_URL, params, encode=True)

    async def synthesize(self, text: str,
                         on_sentence: Optional[Callable[[TtsChunk], None]] = None,
                         on_audio: Optional[Callable[[bytes], None]] = None
                         ) -> List[TtsChunk]:
        """输入文本，返回按句切分的音频块；同时回调。"""
        import asyncio, json

        async with await ws_connect(self.url(), self.auth) as ws:
            await ws.send(json.dumps({"event": "text", "text": text}))
            await ws.send(json.dumps({"event": "finish"}))

            chunks: List[TtsChunk] = []
            buf = bytearray()
            cur_text = ""
            async for msg in ws:
                if isinstance(msg, (bytes, bytearray)):
                    buf += msg
                    if on_audio:
                        on_audio(bytes(msg))
                    continue
                try:
                    data = json.loads(msg)
                except (ValueError, TypeError):
                    continue
                ev = data.get("event")
                if ev == "sentence_start":
                    cur_text = (data.get("sentence_start_result") or {}).get(
                        "readable_text", "")
                elif ev == "sentence_end":
                    if buf:
                        ch = TtsChunk(cur_text, bytes(buf))
                        chunks.append(ch)
                        if on_sentence:
                            on_sentence(ch)
                    buf = bytearray()
                elif ev == "finish":
                    break
                elif "code" in data and int(data["code"]) != 0:
                    raise RuntimeError(f"TTS error {data.get('code')}: "
                                       f"{data.get('message')}")
            return chunks

    def synthesize_to_file(self, text: str, out_path: str) -> List[TtsChunk]:
        import asyncio
        chunks = asyncio.run(self.synthesize(text))
        with open(out_path, "wb") as f:
            for ch in chunks:
                f.write(ch.audio)
        return chunks
