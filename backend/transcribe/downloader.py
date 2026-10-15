"""下载 + 音频提取。

输入：
  - YouTube URL：用 yt-dlp 下载视频，再 ffmpeg 抽音轨
  - 本地视频文件：直接 ffmpeg 抽音轨
输出：
  - 16kHz / 单声道 / 16bit-LE PCM（豆包 ASR 规格）
"""
from __future__ import annotations

import logging
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from ..config import PROJECT_ROOT

log = logging.getLogger("transcribe.downloader")

def _resolve_ffmpeg() -> str:
    configured = os.environ.get("FFMPEG_PATH", "").strip()
    if configured:
        return configured
    local_settings = PROJECT_ROOT / "settings.local.json"
    if local_settings.is_file():
        settings = json.loads(local_settings.read_text(encoding="utf-8-sig"))
        configured = str(settings.get("ffmpeg_path") or "").strip()
        if configured:
            return configured
    return shutil.which("ffmpeg") or "ffmpeg"


FFMPEG = _resolve_ffmpeg()


@dataclass
class MediaInfo:
    """下载/提取产物信息。"""
    pcm_path: str       # 输出 PCM 文件
    title: str          # 视频/文件标题
    duration_sec: float # 时长（秒）


def _run(cmd: list[str], timeout: int = 600) -> None:
    """跑命令，出错抛 RuntimeError。stderr 用 utf-8 + replace 防止 GBK 解码炸。"""
    log.info("$ " + " ".join(cmd[:5]) + (" ..." if len(cmd) > 5 else ""))
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        # 用 utf-8 + replace 解码，兼容 Windows 中文/特殊字符
        try:
            err_text = res.stderr.decode("utf-8", errors="replace")
        except Exception:
            err_text = str(res.stderr)
        log.error(err_text[-1000:])
        raise RuntimeError(f"命令失败 (rc={res.returncode}): {err_text[-500:]}")


def _ffprobe_duration(path: str) -> float:
    """用 ffmpeg 读时长。"""
    res = subprocess.run(
        [FFMPEG, "-i", path],
        capture_output=True, timeout=30,
    )
    # 解析 "Duration: HH:MM:SS.xx"
    try:
        err_text = res.stderr.decode("utf-8", errors="replace")
    except Exception:
        return 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err_text)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _safe_filename(name: str) -> str:
    """过滤 Windows 非法字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:100]


def _yt_dlp_cmd(args: list[str]) -> list[str]:
    """构造 yt-dlp 命令。

    优先用 shutil.which 找的；如果没装就 fallback 用 `python -m yt_dlp`。
    """
    if shutil.which("yt-dlp"):
        return ["yt-dlp"] + args
    # 用 python -m 调用（适用于 pip 装在 site-packages 但 Scripts 没在 PATH）
    import sys
    return [sys.executable, "-m", "yt_dlp"] + args


def download_youtube(url: str, out_dir: str) -> MediaInfo:
    """下载 YouTube 视频并提取 16k PCM 音频。

    Returns: MediaInfo
    """
    os.makedirs(out_dir, exist_ok=True)

    # 1. 拿视频信息（标题）
    log.info(f"获取 YouTube 视频信息: {url}")
    info_proc = subprocess.run(
        _yt_dlp_cmd(["--dump-json", "--no-download", "--no-playlist", url]),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if info_proc.returncode != 0:
        raise RuntimeError(f"yt-dlp 获取信息失败: {info_proc.stderr[-500:]}")
    import json
    info = json.loads(info_proc.stdout.splitlines()[0])
    title = info.get("title", "video")
    log.info(f"标题: {title}")

    # 2. 下载（不超 720p，省时间）
    video_path = os.path.join(out_dir, "source.%(ext)s")
    log.info(f"下载视频到: {video_path}")
    _run(_yt_dlp_cmd([
        "-f", "bestaudio/best",
        "--no-playlist",
        "--no-progress",
        "--js-runtimes", "node",      # 用现成的 Node.js 当 JS 运行时
        "-o", video_path,
        url,
    ]), timeout=900)

    # 3. ffmpeg 抽音轨 + 转 PCM
    candidates = [path for path in Path(out_dir).glob("source.*") if path.suffix not in {".part", ".ytdl"}]
    if len(candidates) != 1:
        raise RuntimeError("下载完成后未找到唯一的音频文件")
    return extract_pcm(str(candidates[0]), out_dir, title)


def extract_pcm(input_path: str, out_dir: str, title: str = "") -> MediaInfo:
    """从本地视频/音频文件提取 16k/mono/16bit PCM。

    兼容: .mp4 .mkv .avi .mov .mp3 .wav .m4a 等
    """
    os.makedirs(out_dir, exist_ok=True)

    if not title:
        title = Path(input_path).stem
    title = _safe_filename(title)

    pcm_path = os.path.join(out_dir, f"{title}.pcm")
    log.info(f"提取音轨 → {pcm_path}")

    _run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-ar", "16000",     # 16kHz
        "-ac", "1",         # 单声道
        "-f", "s16le",      # 16bit-LE
        pcm_path,
    ], timeout=300)

    # Raw PCM: 16 kHz * mono * 16 bits = 32000 bytes per second.
    duration = os.path.getsize(pcm_path) / 32000
    log.info(f"时长: {duration:.1f}秒, PCM: {os.path.getsize(pcm_path)} bytes")

    return MediaInfo(
        pcm_path=pcm_path,
        title=title,
        duration_sec=duration,
    )
