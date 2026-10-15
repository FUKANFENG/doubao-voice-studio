"""doubao_voice — 豆包 ASR/TTS 独立客户端（逆向自豆包 PC web 包）。"""
from .common import Auth, VoiceConfig, build_url, common_params, ASR_URL, TTS_URL
from .asr import AsrClient, AsrResult
from .tts import TtsClient, TtsChunk

__all__ = [
    "Auth", "VoiceConfig", "build_url", "common_params", "ASR_URL", "TTS_URL",
    "AsrClient", "AsrResult", "TtsClient", "TtsChunk",
]
__version__ = "1.0.0"
