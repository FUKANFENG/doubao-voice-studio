# 豆包语音工作室 · Doubao Voice Studio

把豆包的语音能力封装成可供其他项目调用的 HTTP / WebSocket 服务，并提供一个中文 Web 工作台。

支持文字转语音、实时听写、YouTube / 本地音视频转录、豆包 AI 学习笔记和串行任务队列。附带开发文档、OpenAPI、Agent 接入索引，以及 Python / Node.js 示例。

这是一个非官方客户端，使用你自己的豆包登录态连接上游服务；登录过期、人工验证或上游协议变化会影响可用性。

## 功能

- **语音合成**：音色选择、语速与音高调整，AAC / MP3 / Opus / PCM 输出。
- **实时听写**：麦克风输入，WebSocket 传输 16kHz 单声道 PCM。
- **课程转录**：YouTube 视频或本地文件，生成文字稿、片段级 SRT 字幕和带时间戳原稿。
- **AI 整理**：转录后通过豆包对话生成 Markdown 学习笔记，复用服务端登录态。
- **任务队列**：一个课程任务完成后再处理下一个，任务间隔 2 秒；支持排队取消和历史结果。
- **计时**：区分排队、处理、总耗时及音视频时长，终态冻结计时。
- **开发文档**：左侧第四项，提供参数表、代码复制、章节搜索和 Agent 接入说明。

## 技术栈与环境

- Python 3.11+
- Node.js 22+（前端构建与 yt-dlp 的 JavaScript 运行时）
- FFmpeg，用于课程音视频转码，需加入 PATH 或配置其路径
- 后端：FastAPI / Uvicorn / aiohttp / websockets / yt-dlp
- 前端：React 18 / TypeScript / Vite / Zustand / Tailwind CSS

核心语音 SDK 已包含在 `vendor/doubao_voice/`，不需要外部目录链接。已有音视频通过本服务转录时仍需要连接豆包；这不是离线识别引擎。

## 快速开始

### 1. 克隆并安装依赖

```powershell
git clone https://github.com/FUKANFENG/doubao-voice-studio.git
Set-Location doubao-voice-studio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm ci --prefix frontend
```

Windows 也可以运行 `install.bat`，它会创建本地虚拟环境并安装前后端依赖。Python 与 npm 需要在 PATH 中。

### 2. 配置自己的登录态

复制模板，在本机填入你自己授权使用的豆包会话信息：

```powershell
Copy-Item auth.example.json auth.json
```

`cookie` 是会话 Cookie；`web_id`、`tea_uuid` 来自同一会话的请求参数。可选的 `proxy` 用于访问豆包上游。不要把真实值写进源码、提交记录、截图或 issue。

仓库只包含空白模板，`auth.json` 已被 Git 忽略。未配置时 Web 页面和文档仍可打开，但语音和 AI 功能不可用。启动时的自检会通过豆包合成一句短文本。

### 3. 配置 FFmpeg

已加入 PATH 时无需额外配置：

```powershell
ffmpeg -version
```

也可以在启动服务的终端设置路径：

```powershell
$env:FFMPEG_PATH = "C:/tools/ffmpeg/bin/ffmpeg.exe"
```

或者复制 `settings.example.json` 为 `settings.local.json`，填写 `ffmpeg_path`。优先级：环境变量 → 本机配置文件 → PATH。该本机配置文件不会进入 Git。

### 4. 构建并启动

```powershell
npm run build --prefix frontend
.\.venv\Scripts\python.exe -X utf8 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Windows 快捷入口：`build.bat` → `start.bat`。

打开 **http://127.0.0.1:8000**。页面包含语音合成、实时听写、课程转录和开发文档四个入口。

其他系统同样可以安装 Python 依赖、构建前端并运行 Uvicorn；虚拟环境 Python 路径通常为 `.venv/bin/python`。浏览器录音需要 HTTPS 或 localhost。

### 开发模式

两个终端分别运行 `dev-backend.bat` 与 `dev-frontend.bat`，或使用以下命令：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
npm run dev --prefix frontend
```

Vite 默认使用 5173 端口，并将 API、WebSocket 和开发文档请求代理到 8000。

## 集成到其他项目

完整文档：[API.md](API.md)。

| 入口 | 作用 |
| --- | --- |
| `/#developer` | Web 开发文档模块 |
| `/api/docs/markdown` | 完整 Markdown 接入文档 |
| `/llms.txt` | Agent 阅读入口 |
| `/openapi.json` | 由路由与响应模型生成的 HTTP OpenAPI |
| `/docs` | 交互式 HTTP 文档 |
| `/api/docs/examples/python` | Python 客户端下载 |
| `/api/docs/examples/node` | Node.js 客户端下载 |

核心接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | /api/health | 启动时登录态自检状态 |
| GET | /api/speakers | 可用音色 |
| POST | /api/tts | 文本生成音频字节流 |
| WS | /ws/asr | 实时语音识别 |
| GET | /api/transcribe/capabilities | AI 与队列配置 |
| POST | /api/transcribe/url | 提交 YouTube 转录任务 |
| POST | /api/transcribe/file | 上传音视频并提交任务 |
| GET | /api/transcribe/jobs | 任务列表 |
| GET | /api/transcribe/jobs/{id} | 任务详情与结果 |
| POST | /api/transcribe/jobs/{id}/cancel | 取消尚未开始的任务 |

提交任务返回 HTTP 200 和任务对象，保存 `id` 后每 2 秒查询。终态为 `done / error / cancelled`；AI 是否成功还要查看 `summary_status`。客户端应为一次提交生成并复用 `request_id`；响应超时后用同一个标识重试，服务端会返回原任务，不会重复上传或创建任务。

示例客户端在 [examples/](examples/)；Python 需要 requests，Node.js 示例使用内置 fetch。示例默认只检查健康状态，不创建模型任务。

## 部署与运行边界

- **保持一个 Uvicorn worker / 一个服务进程。** 多进程不共享课程队列与识别锁。
- 课程队列覆盖下载、识别和 AI 整理；TTS 不在课程队列中。实时听写与课程识别共用一个 ASR 通道。
- 任务结果保存在 `transcribe_out/jobs/`。重启后恢复排队任务，正在处理的任务会标记为中断，完成结果保留。
- AI 失败不删除文字稿与字幕。勾选整理会把转录文字发送给当前豆包账号，可能出现在该账号的会话历史中。
- 当前没有应用级 API Key 或用户隔离。跨项目建议从业务后端调用；远程部署可使用现有反向代理访问控制。
- Cloudflare Tunnel 的服务 URL 指向 `http://127.0.0.1:8000`；域名与 Tunnel 凭据由部署者自行配置。
- 上传应用上限为 1 GiB，公网代理可能有更低限制。音频流中途异常及 WebSocket 错误边界见 API 文档。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm run build --prefix frontend
```

自动测试隔离上游调用，不需要真实 Cookie。GitHub Actions 在 push / pull request 时运行后端测试和前端构建。

## 目录

```text
backend/           FastAPI、语音接口、转录管线和队列
frontend/          React Web 工作台
vendor/            项目使用的语音 SDK
examples/          Python / Node.js 接入客户端
docs/llms.txt      Agent 接入索引
tests/             队列、转录与 API 契约测试
API.md             页面与原始 Markdown 共用的完整文档
auth.example.json  空白登录态模板
```

真实登录态、个人转录记录、日志、本机设置、历史备份、构建产物和依赖目录均不纳入版本控制。
