"""Persistent job history and one FIFO transcription worker."""
from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable
from ..config import PROJECT_ROOT

log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    WAITING_ASR = "waiting_asr"
    RECOGNIZING = "recognizing"
    MERGING = "merging"
    SUMMARIZING = "summarizing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL = {JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED}


@dataclass
class Job:
    id: str
    status: JobStatus
    source: str
    source_type: str = "url"
    title: str = ""
    duration_sec: float = 0.0
    progress_pct: int = 0
    current_step: str = "等待开始"
    total_chunks: int = 0
    done_chunks: int = 0
    result_text: str = ""
    srt_text: str = ""
    structured_text: str = ""
    summary: str = ""
    summary_requested: bool = False
    summary_status: str = "not_requested"
    summary_error: str = ""
    error: str = ""
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    client_request_id: str = ""


class JobManager:
    def __init__(self, storage_dir: Path | None = None, cooldown_sec: float = 2.0):
        self._jobs: dict[str, Job] = {}
        self.storage_dir = storage_dir or PROJECT_ROOT / "transcribe_out" / "jobs"
        self.cooldown_sec = cooldown_sec
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued_ids: set[str] = set()
        self._worker: asyncio.Task | None = None

    def _save(self, job: Job) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        target = self.storage_dir / f"{job.id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(job), ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)

    def find_by_request_id(self, request_id: str) -> Job | None:
        if not request_id:
            return None
        return next((job for job in self._jobs.values() if job.client_request_id == request_id), None)

    def create(self, source: str, source_type: str = "url", title: str = "", summarize: bool = False,
               request_id: str = "") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], status=JobStatus.PENDING, source=source,
                  source_type=source_type, title=title, created_at=time.time(),
                  summary_requested=summarize, summary_status="pending" if summarize else "not_requested",
                  client_request_id=request_id)
        self._save(job)
        self._jobs[job.id] = job
        return job

    def enqueue(self, job: Job) -> None:
        if job.status != JobStatus.PENDING or job.id in self._queued_ids:
            return
        self._queued_ids.add(job.id)
        self._queue.put_nowait(job.id)

    def start(self, runner: Callable[..., Awaitable[None]]) -> None:
        if self._worker and not self._worker.done():
            return
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        allowed = {item.name for item in fields(Job)}
        for path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["status"] = JobStatus(data["status"])
                job = Job(**{key: value for key, value in data.items() if key in allowed})
                if job.id != path.stem:
                    continue
                if job.status not in TERMINAL and job.status != JobStatus.PENDING:
                    job.status = JobStatus.ERROR
                    job.error = "服务重启时任务中断，请重新提交。已完成的文字稿仍可查看。"
                    job.finished_at = time.time()
                    self._save(job)
                self._jobs[job.id] = job
            except (OSError, ValueError, TypeError, KeyError):
                log.warning("Cannot restore job file %s", path.name)
        for job in sorted(self.all(), key=lambda item: item.created_at):
            if job.status == JobStatus.PENDING:
                self.enqueue(job)
        self._worker = asyncio.create_task(self._run(runner), name="transcription-queue")

    async def _run(self, runner: Callable[..., Awaitable[None]]) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs[job_id]
            try:
                if job.status != JobStatus.PENDING:
                    continue
                self.update(job_id, started_at=time.time(), current_step="准备处理")
                await runner(job, is_url=job.source_type == "url",
                             file_path=job.source if job.source_type == "file" else None,
                             do_summarize=job.summary_requested)
            except asyncio.CancelledError:
                if job.status not in TERMINAL:
                    self.update(job_id, status=JobStatus.ERROR, error="服务已停止，请重新提交任务。",
                                finished_at=time.time())
                raise
            except Exception:
                log.exception("Task %s failed", job_id)
                self.update(job_id, status=JobStatus.ERROR, error="任务处理异常，请重新提交。",
                            finished_at=time.time())
            finally:
                self._queued_ids.discard(job_id)
                self._queue.task_done()
            await asyncio.sleep(self.cooldown_sec)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        job = self._jobs.get(job_id)
        if job:
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            self._save(job)

    def cancel(self, job: Job) -> bool:
        if job.status != JobStatus.PENDING or job.started_at:
            return False
        self.update(job.id, status=JobStatus.CANCELLED, current_step="已取消排队", finished_at=time.time())
        return True

    def to_dict(self, job: Job, include_results: bool = True) -> dict:
        data = asdict(job)
        now = time.time()
        end = job.finished_at or now
        data.update(status=job.status.value, server_time=now,
                    elapsed_sec=max(0.0, end - job.created_at),
                    wait_sec=max(0.0, (job.started_at or end) - job.created_at),
                    processing_sec=max(0.0, end - job.started_at) if job.started_at else 0.0,
                    queue_position=0)
        if job.status == JobStatus.PENDING and not job.started_at:
            pending = [item for item in self.all() if item.status == JobStatus.PENDING and not item.started_at]
            data["queue_position"] = sorted(pending, key=lambda item: item.created_at).index(job) + 1
        if job.source_type == "file":
            data["source"] = job.title or "本地文件"
        if not include_results:
            for key in ("result_text", "srt_text", "structured_text", "summary"):
                data.pop(key)
        return data

    def all(self) -> list[Job]:
        return list(self._jobs.values())


manager = JobManager()
