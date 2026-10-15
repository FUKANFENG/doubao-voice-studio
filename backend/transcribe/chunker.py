"""音频切片：把长 PCM 切成 50 秒一段，重叠 1 秒。

豆包 ASR 单 session 限制 ~60s（受 MUTE_MAX_DURATION 影响）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# 16kHz / 单声道 / 16bit-LE = 32000 字节/秒
BYTES_PER_SEC = 16000 * 1 * 2  # 32000

# 默认参数
DEFAULT_CHUNK_SEC = 50.0   # 每段 50 秒
DEFAULT_OVERLAP_SEC = 1.0  # 重叠 1 秒（避免切在词中间）


@dataclass
class AudioChunk:
    """一个 PCM 片段。"""
    index: int            # 0-based
    start_sec: float      # 起
    end_sec: float        # 止
    pcm_path: str         # 写到磁盘的片段路径
    duration_sec: float   # 该段时长（秒）


def split_pcm(
    pcm_path: str,
    out_dir: str,
    chunk_sec: float = DEFAULT_CHUNK_SEC,
    overlap_sec: float = DEFAULT_OVERLAP_SEC,
    progress_cb=None,
) -> list[AudioChunk]:
    """把 PCM 切成多个片段，写到 out_dir。

    progress_cb(done: int, total: int) 用于进度回调。
    """
    os.makedirs(out_dir, exist_ok=True)
    file_size = os.path.getsize(pcm_path)
    if file_size == 0:
        return []

    total_sec = file_size / BYTES_PER_SEC
    step_sec = chunk_sec - overlap_sec
    if step_sec <= 0:
        raise ValueError("chunk_sec 必须大于 overlap_sec")

    chunks: list[AudioChunk] = []
    start_sec = 0.0
    idx = 0

    while start_sec < total_sec:
        end_sec = min(start_sec + chunk_sec, total_sec)
        start_byte = int(start_sec * BYTES_PER_SEC)
        end_byte = int(end_sec * BYTES_PER_SEC)
        # Keep every complete 16-bit sample; pad only the final network frame.
        end_byte -= end_byte % 2
        start_byte -= start_byte % 2

        if end_byte <= start_byte:
            break

        out_path = os.path.join(out_dir, f"chunk_{idx:04d}.pcm")
        with open(pcm_path, "rb") as fin, open(out_path, "wb") as fout:
            fin.seek(start_byte)
            chunk_bytes = end_byte - start_byte
            while chunk_bytes > 0:
                buf = fin.read(min(chunk_bytes, 1024 * 1024))
                if not buf:
                    break
                fout.write(buf)
                chunk_bytes -= len(buf)

        dur = (end_byte - start_byte) / BYTES_PER_SEC
        chunks.append(AudioChunk(
            index=idx,
            start_sec=start_byte / BYTES_PER_SEC,
            end_sec=end_byte / BYTES_PER_SEC,
            pcm_path=out_path,
            duration_sec=dur,
        ))

        idx += 1
        if progress_cb:
            progress_cb(idx, max(idx, int(total_sec / step_sec) + 1))
        if end_byte >= file_size - file_size % 2:
            break
        start_sec += step_sec

    return chunks


def cleanup(chunks: list[AudioChunk]) -> None:
    """删除所有片段文件。"""
    for c in chunks:
        try:
            os.remove(c.pcm_path)
        except OSError:
            pass
