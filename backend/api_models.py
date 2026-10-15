"""Public response contracts shared by the API and generated OpenAPI document."""
from typing import Literal
from pydantic import BaseModel, Field
from .transcribe.jobs import JobStatus


class HealthResponse(BaseModel):
    ok: bool = Field(description="服务端登录态已加载且启动时 TTS 握手自检通过；不是每次请求的上游实时探测。")
    ts: float = Field(description="服务端 Unix 时间戳，秒。")
    auth_loaded: bool
    auth_ok: bool
    auth_reason: str
    cookie_chars: int = Field(description="登录态字符串长度，不包含凭据内容。")


class Speaker(BaseModel):
    id: str
    name: str


class SpeakersResponse(BaseModel):
    default: str
    speakers: list[Speaker]


class SummaryCapability(BaseModel):
    available: bool = Field(description="依据本机登录态自检；实际对话仍可能遇到过期、验证或限流。")
    provider: Literal["doubao_session"]
    label: str
    reason: str


class CapabilitiesResponse(BaseModel):
    summary: SummaryCapability
    queue_concurrency: int
    cooldown_sec: float


class JobInfo(BaseModel):
    id: str
    status: JobStatus
    source: str = Field(description="YouTube 链接或上传文件标题；不公开本机临时路径。")
    source_type: Literal["url", "file"]
    title: str
    duration_sec: float = Field(description="音视频实际时长（秒），提取前为 0。")
    progress_pct: int
    current_step: str
    total_chunks: int
    done_chunks: int
    summary_requested: bool
    summary_status: Literal["not_requested", "pending", "running", "done", "error", "skipped"]
    summary_error: str
    error: str
    created_at: float = Field(description="提交时间，Unix 秒。")
    started_at: float = Field(description="开始处理时间，Unix 秒；尚未开始为 0。")
    finished_at: float = Field(description="结束时间，Unix 秒；尚未结束为 0。")
    server_time: float
    elapsed_sec: float = Field(description="总耗时 = 排队 + 处理；任务结束后冻结。")
    wait_sec: float
    processing_sec: float = Field(description="从出队开始，包含下载、等待识别通道、识别及 AI 整理。")
    queue_position: int = Field(description="等待队列序号从 1 开始；非等待中为 0。")


class JobDetail(JobInfo):
    result_text: str
    srt_text: str
    structured_text: str = Field(description="带片段时间戳的 Markdown 原稿，不是 AI 笔记。")
    summary: str = Field(description="豆包生成的 Markdown 学习笔记；不可仅根据 status=done 判断生成成功。")


class TextError(BaseModel):
    detail: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class CodedError(BaseModel):
    detail: ErrorDetail
