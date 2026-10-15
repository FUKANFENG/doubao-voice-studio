"""公共部分：常量、鉴权参数、URL 构造、WebSocket 连接。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional
from urllib.parse import urlencode

# --- 端点 (逆向自 flow-component-asr-service-sdk / chat-voice-asr-service) ---
ASR_URL = "wss://ws-samantha.doubao.com/samantha/audio/asr"
TTS_URL = "wss://ws-samantha.doubao.com/samantha/audio/tts"

ORIGIN = "https://www.doubao.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# --- 常量 (逆向自 bundle 模块 884395 / 663764) ---
VERSION_CODE = 20800        # E.VERSION_CODE
DEVICE_PLATFORM = "web"     # E.DEVICE_PLATFORM
AID = 497858                # getAid()          -> WEB_DOUBAO_APP_ID
REAL_AID = 582478           # getAid(true)      -> DESKTOP_DOUBAO_APP_ID
PKG_TYPE = "release_version"
RUNTIME_VERSION = "2.22.3"  # getSamanthaClientVersion()

SAMPLE_RATE = 16000         # AudioContext({sampleRate:16000})
FRAME_SAMPLES = 2048        # worklet bufferSize -> 4096 字节 / 帧 (~128ms)
MUTE_FRAME = b"\x00" * 16384  # 静音保活帧
MUTE_INTERVAL = 0.2         # 秒
MUTE_MAX_DURATION = 60.0    # 秒，之后自动 stop

# 服务端返回码
CODE_OK = 0
CODE_TIMEOUT = 0x2A51E74D   # 710010701
CODE_INVALID = 0x2A51E74E   # 710010702


@dataclass
class Auth:
    """豆包登录态。cookie 必填；web_id / tea_uuid 从抓包的 URL 里取。"""
    cookie: str = ""
    web_id: str = ""
    tea_uuid: str = ""
    language: str = "zh"
    region: str = "cn"
    # 出网 HTTP 代理 (如 http://127.0.0.1:7879)；空则直连
    proxy: str = ""
    # 公网访问钥匙（隧道发布用；本机/局域网直连不需要）
    access_key: str = ""
    # 抓包里若出现非默认常量，可整段覆盖
    overrides: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 允许从环境变量补全，便于 CLI 使用
        self.cookie = self.cookie or os.environ.get("DB_COOKIE", "")
        self.web_id = self.web_id or os.environ.get("DB_WEB_ID", "")
        self.tea_uuid = self.tea_uuid or os.environ.get("DB_TEA_UUID", "")
        self.proxy = self.proxy or os.environ.get("DB_PROXY", "")

    @classmethod
    def load(cls, path: str) -> "Auth":
        with open(path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @property
    def headers(self):
        return [("Cookie", self.cookie), ("Origin", ORIGIN), ("User-Agent", UA)]


# VoiceConfig 只是 Auth 的别名，方便语义化阅读
VoiceConfig = Auth


def common_params(auth: Auth) -> Dict[str, object]:
    """复刻 getCommonParams()（模块 933113）。"""
    wid = auth.web_id
    p: Dict[str, object] = {
        "version_code": VERSION_CODE,
        "language": auth.language,
        "device_platform": DEVICE_PLATFORM,
        "aid": AID,
        "real_aid": REAL_AID,
        "pkg_type": PKG_TYPE,
        "device_id": wid if wid and wid != "0" else "",
        "web_id": wid,
        "tea_uuid": auth.tea_uuid,
        "use-olympus-account": 1,
        "region": auth.region,
        "sys_region": auth.region,
        "samantha_web": 1,
        "runtime": "web",
        "runtime_version": RUNTIME_VERSION,
        "pc_version": "0",
        "fp": f"verify_{wid}",
    }
    p.update(auth.overrides)
    return p


def build_url(base: str, params: Dict[str, object], encode: bool = False) -> str:
    """复刻 app 的 getUrl()：base?k1=v1&k2=v2。

    ASR 不编码 (encode=False)，TTS 走 urlencode (encode=True)。
    """
    if encode:
        return f"{base}?{urlencode(params)}"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base}?{qs}"


async def ws_connect(url: str, auth: Auth, **kwargs):
    """跨 websockets 版本的连接助手。auth.proxy 非空时走 HTTP 代理。"""
    import websockets  # 延迟导入，便于 --dry-run 无依赖运行

    common = dict(max_size=None, open_timeout=10, close_timeout=5)
    if auth.proxy and "proxy" not in kwargs:
        kwargs["proxy"] = auth.proxy
    common.update(kwargs)
    try:
        return await websockets.connect(url, additional_headers=auth.headers, **common)
    except TypeError:
        return await websockets.connect(url, extra_headers=auth.headers, **common)
