"""转录主流程编排。

run_pipeline(job) 跑完整流程：
  1. 下载（URL）或接受本地文件
  2. 提取音频
  3. 切片
  4. 串行 ASR 识别
  5. 合并 + 输出 .txt / .srt
  6. (可选) 豆包对话接口 AI 整理
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from .chunker import AudioChunk, split_pcm, BYTES_PER_SEC
from .downloader import MediaInfo, download_youtube, extract_pcm
from .jobs import Job, JobStatus, manager

log = logging.getLogger("transcribe.pipeline")

# 临时文件根目录
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "doubao_transcribe")


def _merge_to_srt(chunks_results: list[tuple[AudioChunk, str]]) -> str:
    """生成 SRT 字幕格式。

    每段一行带序号、时间戳、文字。
    """
    srt_lines = []
    for chunk, text in chunks_results:
        if not text.strip():
            continue
        start = _format_srt_time(chunk.start_sec)
        end = _format_srt_time(chunk.end_sec)
        srt_lines.append(f"{len(srt_lines) + 1}\n{start} --> {end}\n{text.strip()}\n")
    return "\n".join(srt_lines)


def _format_srt_time(sec: float) -> str:
    """秒 → SRT 时间格式 HH:MM:SS,mmm"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _merge_to_text(chunks_results: list[tuple[AudioChunk, str]]) -> str:
    """合并成纯文字。"""
    parts = []
    for chunk, text in chunks_results:
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _merge_to_structured(chunks_results: list[tuple[AudioChunk, str]]) -> str:
    """合并成 Markdown 带时间戳。"""
    parts = []
    for chunk, text in chunks_results:
        if text.strip():
            mm = int(chunk.start_sec // 60)
            ss = int(chunk.start_sec % 60)
            parts.append(f"**[{mm:02d}:{ss:02d}]** {text.strip()}")
    return "\n\n".join(parts)


async def run_pipeline(
    job: Job,
    is_url: bool,
    file_path: Optional[str] = None,
    do_summarize: bool = False,
):
    """跑完整转录流程。"""
    job_id = job.id
    work_dir = os.path.join(TEMP_ROOT, job_id)
    os.makedirs(work_dir, exist_ok=True)
    log.info(f"[{job_id}] 工作目录: {work_dir}")

    try:
        manager.update(job_id, source_type="url" if is_url else "file",
                       summary_requested=do_summarize,
                       summary_status="pending" if do_summarize else "not_requested")
        if not job.started_at:
            manager.update(job_id, started_at=time.time())
        # ====== 阶段 1: 下载 / 提取音频 ======
        if is_url:
            manager.update(job_id, status=JobStatus.DOWNLOADING, progress_pct=3, current_step="下载 YouTube 音频…")
            loop = asyncio.get_event_loop()
            media = await loop.run_in_executor(
                None, lambda: download_youtube(job.source, work_dir)
            )
        else:
            manager.update(job_id, status=JobStatus.EXTRACTING, progress_pct=5, current_step="提取音频…")
            loop = asyncio.get_event_loop()
            media = await loop.run_in_executor(
                None, lambda: extract_pcm(file_path, work_dir)
            )

        job.title = job.title if not is_url and job.title else media.title
        job.duration_sec = media.duration_sec
        log.info(f"[{job_id}] 提取完成: {media.title} ({media.duration_sec:.1f}s)")

        # ====== 阶段 2: 切片 ======
        manager.update(job_id, status=JobStatus.CHUNKING, progress_pct=12, current_step="切分音频…")
        chunks = await loop.run_in_executor(
            None,
            lambda: split_pcm(media.pcm_path, os.path.join(work_dir, "chunks"))
        )
        job.total_chunks = len(chunks)
        log.info(f"[{job_id}] 切分完成: {len(chunks)} 段")

        if not chunks:
            raise RuntimeError("音频切片为空（音频文件可能为空）")

        # ====== 阶段 3: ASR 识别 ======
        manager.update(job_id, status=JobStatus.RECOGNIZING, current_step="开始 ASR 识别...")

        # 延迟导入（避免循环）
        from .recognizer import recognize_all

        completed_results: list[tuple[AudioChunk, str]] = []

        def on_progress(done: int, total: int, text: str):
            completed_results.append((chunks[done - 1], text))
            # 截前 30 字给前端预览
            preview = text[:30].replace("\n", " ") if text else ""
            manager.update(job_id, done_chunks=done, progress_pct=15 + int(done / total * 70),
                           current_step=f"识别 {done}/{total}: {preview}...",
                           result_text=_merge_to_text(completed_results),
                           srt_text=_merge_to_srt(completed_results),
                           structured_text=_merge_to_structured(completed_results))

        def on_retry(index: int, attempt: int, max_attempts: int, delay: float):
            manager.update(job_id, current_step=(
                f"第 {index + 1}/{len(chunks)} 段连接中断或超时，"
                f"{delay:g} 秒后重试（{attempt}/{max_attempts}）…"))

        # 串行识别（每段间隔 1 秒，避免 burst 限流）
        from ..asr_gate import asr_slot
        if asr_slot.locked():
            manager.update(job_id, status=JobStatus.WAITING_ASR, current_step="等待当前录音结束…")
        async with asr_slot:
            manager.update(job_id, status=JobStatus.RECOGNIZING, progress_pct=15, current_step="逐段识别音频…")
            texts = await recognize_all(chunks, progress_cb=on_progress, cooldown_sec=1.0,
                                        retry_cb=on_retry)
        chunks_results = list(zip(chunks, texts))
        log.info(f"[{job_id}] 识别完成: {len(texts)} 段")

        # ====== 阶段 4: 合并 ======
        manager.update(job_id, status=JobStatus.MERGING, progress_pct=88, current_step="合并文字稿…")
        job.result_text = _merge_to_text(chunks_results)
        job.srt_text = _merge_to_srt(chunks_results)
        job.structured_text = _merge_to_structured(chunks_results)
        log.info(f"[{job_id}] 合并完成: {len(job.result_text)} 字")

        # ====== 阶段 5: AI 整理（可选）======
        if do_summarize and job.result_text:
            manager.update(job_id, status=JobStatus.SUMMARIZING, progress_pct=92,
                           summary_status="running", current_step="豆包正在整理学习笔记…")
            try:
                from .summarizer import summarize
                job.summary = await summarize(
                    job.result_text,
                    on_progress=lambda t: setattr(job, "current_step", t),
                )
                log.info(f"[{job_id}] AI 整理完成: {len(job.summary)} 字")
                manager.update(job_id, summary_status="done")
            except Exception as e:
                log.warning(f"[{job_id}] AI 整理失败: {e}")
                manager.update(job_id, summary_status="error", summary_error=str(e), summary="")
        elif do_summarize:
            manager.update(job_id, summary_status="skipped", summary_error="没有识别到文字，已跳过 AI 整理。")

        # ====== 完成 ======
        manager.update(job_id, status=JobStatus.DONE, progress_pct=100,
                       current_step="转录完成" if not job.summary_error else "转录完成，请查看 AI 整理提示", finished_at=time.time())
        log.info(f"[{job_id}] ✅ pipeline 完成")

    except Exception as e:
        log.exception(f"[{job_id}] pipeline 失败")
        if job.summary_requested and job.summary_status == "pending":
            job.summary_status = "skipped"
        manager.update(job_id, status=JobStatus.ERROR, error=f"{type(e).__name__}: {e}",
                       current_step=(f"转录中断 · 已保留 {job.done_chunks}/{job.total_chunks} 段"
                                     if job.total_chunks else "转录失败"),
                       finished_at=time.time())
    finally:
        # Result text is persisted separately; intermediate audio is no longer needed.
        resolved_work = Path(work_dir).resolve()
        resolved_root = Path(TEMP_ROOT).resolve()
        if resolved_work != resolved_root and resolved_work.is_relative_to(resolved_root):
            shutil.rmtree(resolved_work, ignore_errors=True)
        if not is_url and file_path:
            upload_root = os.path.join(tempfile.gettempdir(), "doubao_uploads")
            if os.path.dirname(os.path.abspath(file_path)) == os.path.abspath(upload_root):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
