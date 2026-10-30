"""Account updates are available only through a direct loopback connection."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

import export_auth as exporter
from . import auth_loader
from .config import AUTH_PATH, PROJECT_ROOT

router = APIRouter(prefix='/api/auth', tags=['account'])
TOOL_PATH = PROJECT_ROOT / 'dist' / 'account-tool' / 'DoubaoAuthTool.exe'
if not TOOL_PATH.is_file():
    TOOL_PATH = PROJECT_ROOT / 'dist' / 'DoubaoAuthTool.exe'
MAX_BODY = 65536
_update_lock = asyncio.Lock()


class AccountStatus(BaseModel):
    loaded: bool
    auth_ok: bool
    cookie_chars: int
    can_manage: bool
    local_available: bool
    tool_available: bool


def is_local(request: Request) -> bool:
    try:
        if not request.client or not ipaddress.ip_address(request.client.host).is_loopback:
            return False
    except ValueError:
        return False
    if request.url.hostname not in {'localhost', '127.0.0.1', '::1'} or request.url.username:
        return False
    if any(name in request.headers for name in (
        'forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto',
        'cf-connecting-ip', 'cf-visitor', 'true-client-ip', 'x-real-ip',
    )):
        return False
    origin = request.headers.get('origin')
    allowed = {f'{request.url.scheme}://{request.url.netloc}',
               'http://127.0.0.1:5173', 'http://localhost:5173'}
    return (origin is None or origin in allowed) and request.headers.get('sec-fetch-site') != 'cross-site'


def status(request: Request) -> AccountStatus:
    snapshot = auth_loader.get_snapshot()
    local = is_local(request)
    return AccountStatus(loaded=snapshot.loaded, auth_ok=snapshot.auth_ok,
                         cookie_chars=snapshot.cookie_chars, can_manage=local,
                         local_available=local and sys.platform == 'win32',
                         tool_available=TOOL_PATH.is_file())


async def local_body(request: Request) -> dict:
    if not is_local(request) or request.headers.get('x-doubao-local') != '1':
        raise HTTPException(403, '请在服务所在电脑，通过 localhost 或 127.0.0.1 管理登录态。')
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
        raise HTTPException(415, '请使用 JSON 配置。')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise HTTPException(413, '配置超过 64 KB 上限。')
        body.extend(chunk)
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, '配置 JSON 无法解析，原登录态未修改。') from None
    if not isinstance(data, dict):
        raise HTTPException(400, '配置必须是 JSON 对象。')
    return data


async def apply_config(config: dict) -> None:
    from doubao_voice import Auth
    exporter.validate_config(config)
    if not config.get('cookie') or any(ord(c) < 32 or ord(c) > 126 for c in config['cookie']):
        raise exporter.ExportError('Cookie 为空或包含无效字符。')
    candidate = Auth(**config)
    okay, _ = await auth_loader._probe_tts_handshake(candidate)
    if not okay:
        raise exporter.ExportError('会话验证未通过，请确认登录态、代理和网络；原配置未修改。')
    # This small atomic write must not yield between persistence and activation.
    exporter.save_config(AUTH_PATH, config)
    auth_loader.activate(candidate)


@router.get('/status', response_model=AccountStatus, summary='查看登录态与本机管理能力',
            operation_id='getAccountStatus')
async def get_status(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return status(request)


@router.post('/import', response_model=AccountStatus, summary='本机导入并验证登录态',
             operation_id='importLocalAccount',
             description='仅接受直接本机请求和 X-Doubao-Local: 1。JSON: {"config": {"cookie": "..."}}；'
                         '未提供的字段沿用原配置。验证成功后原子保存并立即生效，不返回凭据。')
async def import_account(request: Request, response: Response):
    data = await local_body(request)
    try:
        if set(data) != {'config'}:
            raise exporter.ExportError('请求必须包含 config。')
        incoming = exporter.validate_config(data['config'])
        async with _update_lock:
            existing = await asyncio.to_thread(exporter.load_config, AUTH_PATH)
            merged = {**existing, **incoming}
            config = exporter.make_config(merged, merged.get('cookie', ''))
            await apply_config(config)
    except exporter.ExportError as error:
        raise HTTPException(400, str(error)) from None
    except Exception:
        raise HTTPException(400, '配置无效、会话验证失败或文件不可写；原登录态未修改。') from None
    response.headers['Cache-Control'] = 'no-store'
    return status(request)


def read_local(request_url: str) -> dict:
    if sys.platform != 'win32' or not os.environ.get('LOCALAPPDATA'):
        raise exporter.ExportError('自动读取需要在 Windows 上运行原生服务。')
    existing = exporter.load_config(AUTH_PATH)
    # Validate the session parameters before decrypting any local credentials.
    config = exporter.make_config(existing, '', request_url=request_url)
    user_data = Path(os.environ['LOCALAPPDATA']) / 'Doubao' / 'User Data'
    config['cookie'], _ = exporter.collect_cookies(user_data, 'Default')
    return config


@router.post('/local', response_model=AccountStatus, summary='读取本机 Windows 豆包登录态',
             operation_id='readLocalWindowsAccount',
             description='仅直接本机访问。JSON: {} 或 {"request_url": "本人实际语音 WS URL"}。'
                         '读取当前 Windows 用户的 Default 配置，验证后保存；不返回 Cookie。')
async def local_account(request: Request, response: Response):
    data = await local_body(request)
    if sys.platform != 'win32':
        raise HTTPException(400, '自动读取需要 Windows 原生服务；其他部署请导入配置。')
    try:
        request_url = data.get('request_url', '')
        if set(data) - {'request_url'} or not isinstance(request_url, str):
            raise exporter.ExportError('无效的读取参数。')
        async with _update_lock:
            config = await asyncio.to_thread(read_local, request_url)
            await apply_config(config)
    except exporter.ExportError as error:
        raise HTTPException(400, str(error)) from None
    except Exception:
        raise HTTPException(400, '读取或验证失败。请确认豆包已登录并完全退出，且已有完整配置或实际语音请求 URL。'
                                '原登录态未修改。') from None
    response.headers['Cache-Control'] = 'no-store'
    return status(request)


@router.get('/tool', response_class=FileResponse, summary='下载 Windows 登录态工具',
            operation_id='downloadWindowsAccountTool')
async def download_tool():
    if not TOOL_PATH.is_file():
        raise HTTPException(404, '此部署未放置 Windows 工具，请从项目 Actions 下载构建。')
    return FileResponse(TOOL_PATH, filename='DoubaoAuthTool.exe',
                        media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})
