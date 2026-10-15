#!/usr/bin/env python
"""CLI 转录工具。

用法:
  # YouTube 链接
  python transcribe.py "https://www.youtube.com/watch?v=xxx"
  python transcribe.py "URL" --summarize

  # 本地文件
  python transcribe.py local.mp4
  python transcribe.py local.mp4 --chunk-sec 30 --summarize

输出:
  - <title>.txt 纯文字稿
  - <title>.srt 字幕（含时间戳）
  - <title>_summary.md AI 整理（如果启用）
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# 允许作为脚本运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("transcribe_cli")


def main():
    ap = argparse.ArgumentParser(description="豆包 ASR 长音频转录 CLI")
    ap.add_argument("source", help="YouTube URL 或本地视频/音频文件路径")
    ap.add_argument("--chunk-sec", type=float, default=50.0, help="每段秒数（默认 50）")
    ap.add_argument("--overlap-sec", type=float, default=1.0, help="段间重叠秒数（默认 1）")
    ap.add_argument("--summarize", action="store_true", help="启用 AI 整理")
    ap.add_argument("--out-dir", default="./transcribe_out", help="输出目录（默认 ./transcribe_out）")
    args = ap.parse_args()

    is_url = args.source.startswith("http")
    source = args.source

    if not is_url and not Path(source).is_file():
        print(f"[X] 文件不存在: {source}")
        sys.exit(1)

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # 初始化
    from backend.transcribe import jobs
    from backend.transcribe.pipeline import run_pipeline, _merge_to_text, _merge_to_srt

    job = jobs.manager.create(source=source)
    print(f"--- 创建任务 {job.id}")
    print(f"    源: {source}")
    print(f"    is_url: {is_url}, summarize: {args.summarize}")
    print(f"    输出目录: {out_dir}")
    print()

    # 注册进度回调
    def on_log():
        from backend.transcribe import jobs as _jobs
        j = _jobs.manager.get(job.id)
        if j:
            print(f"  [{j.status.value:14s}] {j.progress_pct:3d}% {j.current_step}")

    # 简易进度：每秒打印一次
    import threading, time
    stop_flag = [False]
    def progress_thread():
        while not stop_flag[0]:
            time.sleep(2)
            if stop_flag[0]:
                break
            on_log()

    t = threading.Thread(target=progress_thread, daemon=True)
    t.start()

    # 跑
    try:
        asyncio.run(run_pipeline(
            job,
            is_url=is_url,
            file_path=None if is_url else source,
            do_summarize=args.summarize,
        ))
    finally:
        stop_flag[0] = True
        t.join(timeout=2)

    # 结果
    final = jobs.manager.get(job.id)
    if final.status.value == "done":
        title = final.title or "transcript"
        # 写文件
        if final.result_text:
            txt_path = os.path.join(out_dir, f"{title}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(final.result_text)
            print(f"\n[OK] 文字稿: {txt_path} ({len(final.result_text)} 字)")
        if final.srt_text:
            srt_path = os.path.join(out_dir, f"{title}.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(final.srt_text)
            print(f"[OK] 字幕: {srt_path}")
        if final.summary:
            sum_path = os.path.join(out_dir, f"{title}_summary.md")
            with open(sum_path, "w", encoding="utf-8") as f:
                f.write(final.summary)
            print(f"[OK] AI 整理: {sum_path}")
        print(f"\n=== 全部完成！耗时 {final.finished_at - final.created_at:.1f}s")
    else:
        print(f"\n[X] 任务失败: {final.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
