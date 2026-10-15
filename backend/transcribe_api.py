"""Transcription submission, FIFO queue, history and result downloads."""
from __future__ import annotations
import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .transcribe.jobs import manager, JobStatus
from .transcribe.summarizer import get_status
from .api_models import CapabilitiesResponse, JobInfo, JobDetail, TextError

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])
UPLOAD_DIR = Path(tempfile.gettempdir()) / "doubao_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_ERRORS = {
    code: {"description": description, "content": {
        "application/json": {"schema": TextError.model_json_schema()}}}
    for code, description in {400: "当前任务尚无此结果", 404: "任务不存在"}.items()
}


class UrlSubmission(BaseModel):
    url: str = Field(min_length=1, max_length=2048, description="单个 YouTube 视频或 Shorts 链接，不展开播放列表")
    summarize: bool = Field(default=False, description="转录后使用现有豆包登录态生成 Markdown 学习笔记")
    request_id: str = Field(default="", max_length=128, description="客户端幂等标识；重试同一提交时保持不变")


def _validate_summary(requested: bool) -> None:
    if requested and not get_status()["available"]:
        raise HTTPException(400, "豆包 AI 整理暂不可用，请更新登录态或关闭 AI 整理后转录。")


@router.get("/capabilities", response_model=CapabilitiesResponse,
            summary="AI 可用状态与队列配置", operation_id="getTranscriptionCapabilities")
async def capabilities():
    return {"summary": get_status(), "queue_concurrency": 1, "cooldown_sec": manager.cooldown_sec}


@router.post("/url", response_model=JobDetail, summary="提交 YouTube 转录任务",
             operation_id="submitYouTubeTranscription",
             description="HTTP 200 表示已创建任务，任务尚未完成。保存 id 后轮询详情。重试同一 request_id 会返回原任务。",
             responses={400: {"model": TextError, "description": "链接不合法或 AI 暂不可用"}})
async def submit_url(payload: UrlSubmission):
    url = payload.url.strip()
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise HTTPException(400, "请输入有效的 YouTube 视频链接")
    if parsed.scheme not in {"https", "http"} or host not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"
    } or parsed.username or parsed.password or port not in {None, 80, 443}:
        raise HTTPException(400, "请输入有效的 YouTube 视频链接")
    _validate_summary(payload.summarize)
    existing = manager.find_by_request_id(payload.request_id)
    if existing:
        return manager.to_dict(existing)
    job = manager.create(source=url, summarize=payload.summarize, request_id=payload.request_id)
    manager.enqueue(job)
    return manager.to_dict(job)


@router.post("/file", response_model=JobDetail, summary="上传音视频并加入队列",
             operation_id="submitFileTranscription",
             description="multipart/form-data；应用上限 1 GiB，公网代理可能限制更小。HTTP 200 返回任务。",
             responses={400: {"model": TextError, "description": "空文件、不支持的格式或 AI 不可用"},
                        413: {"model": TextError, "description": "超出应用上传上限"}})
async def submit_file(file: UploadFile = File(...), summarize: bool = Form(default=False),
                      request_id: str = Form(default="")):
    if not file.filename:
        raise HTTPException(400, "请选择音频或视频文件")
    _validate_summary(summarize)
    # Never trust a client filename as a filesystem path.
    filename = unquote(file.filename).replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(filename).suffix.lower()
    if extension not in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
        raise HTTPException(400, "不支持此格式，请选择常见音频或视频文件")
    save_path = UPLOAD_DIR / (uuid.uuid4().hex + extension)
    size = 0
    try:
        with save_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 1024 * 1024 * 1024:
                    raise HTTPException(413, "文件超过本机 1 GB 上传上限")
                await asyncio.to_thread(output.write, chunk)
        if not size:
            raise HTTPException(400, "文件为空")
        existing = manager.find_by_request_id(request_id)
        if existing:
            save_path.unlink(missing_ok=True)
            return manager.to_dict(existing)
        job = manager.create(source=str(save_path), source_type="file",
                             title=Path(filename).stem, summarize=summarize,
                             request_id=request_id)
        manager.enqueue(job)
        return manager.to_dict(job)
    except BaseException:
        save_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/jobs", response_model=list[JobInfo], summary="列出任务与历史记录",
            operation_id="listTranscriptionJobs", description="按创建时间倒序；不包含文字稿和笔记全文。")
async def list_jobs():
    return [manager.to_dict(job, include_results=False)
            for job in sorted(manager.all(), key=lambda item: item.created_at, reverse=True)]


def _job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/jobs/{job_id}", response_model=JobDetail, summary="查询任务及全部结果",
            operation_id="getTranscriptionJob", responses={404: {"model": TextError}})
async def get_job(job_id: str):
    return manager.to_dict(_job(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobDetail, summary="取消尚未开始的任务",
             operation_id="cancelTranscriptionJob",
             responses={404: {"model": TextError}, 409: {"model": TextError, "description": "任务已经开始或已结束"}})
async def cancel_job(job_id: str):
    job = _job(job_id)
    if not manager.cancel(job):
        raise HTTPException(409, "只能取消尚未开始的排队任务")
    if job.source_type == "file":
        source = Path(job.source).resolve()
        if source.parent == UPLOAD_DIR.resolve():
            source.unlink(missing_ok=True)
    return manager.to_dict(job)


def _download(job_id: str, field: str, suffix: str):
    job = _job(job_id)
    content = getattr(job, field)
    if not content:
        raise HTTPException(400, "当前任务尚无此结果")
    filename = quote((job.title or "transcript") + suffix, safe="")
    return PlainTextResponse(content, headers={
        "Content-Disposition": f"attachment; filename=transcript{suffix}; filename*=UTF-8''{filename}",
        "Cache-Control": "no-store",
    })


@router.get("/jobs/{job_id}/text", response_class=PlainTextResponse,
            summary="下载 UTF-8 文字稿", operation_id="downloadTranscript",
            responses=DOWNLOAD_ERRORS)
async def get_text(job_id: str):
    return _download(job_id, "result_text", ".txt")


@router.get("/jobs/{job_id}/srt", response_class=PlainTextResponse,
            summary="下载 SRT 字幕", operation_id="downloadSubtitles",
            responses=DOWNLOAD_ERRORS)
async def get_srt(job_id: str):
    return _download(job_id, "srt_text", ".srt")


@router.get("/jobs/{job_id}/summary", response_class=PlainTextResponse,
            summary="下载 AI 笔记 Markdown", operation_id="downloadLearningNotes",
            responses=DOWNLOAD_ERRORS)
async def get_summary(job_id: str):
    return _download(job_id, "summary", "_summary.md")
