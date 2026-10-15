# 豆包语音工作室 API

版本 1.3.0 · 更新于 2026-10-13。本文对应正在运行的本地服务；HTTP 契约由代码生成 OpenAPI，WebSocket 协议在本文单独说明。

## 快速开始

本文使用 `your-domain.example` 作为公网域名占位。请替换为实际部署域名；从本机调用可以使用 `http://127.0.0.1:8000`。Web 页面的「复制 Agent 接入说明」会自动填入当前服务地址。

把声音能力接到你的项目：业务后端调用本服务，本服务处理豆包登录态、协议、课程任务队列和结果保存。

| 环境 | Base URL |
| --- | --- |
| 公网入口（替换为你的域名） | `https://your-domain.example` |
| 服务所在电脑 | `http://127.0.0.1:8000` |
| WebSocket 公网入口 | `wss://your-domain.example/ws/asr` |
| WebSocket 同机入口 | `ws://127.0.0.1:8000/ws/asr` |

URL 末尾不加 `/api`，下文路径已包含它。建议把 Base URL 存入业务项目的 `DOUBAO_BASE_URL` 环境变量。

### 先确认服务状态

```powershell
$base = "https://your-domain.example"
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod "$base/api/transcribe/capabilities"
```

- `GET /api/health`：返回 `ok, ts, auth_loaded, auth_ok, auth_reason, cookie_chars`。HTTP 200 不一定可用，请检查 `ok`。
- `ok` 反映服务启动时的登录态加载和 TTS 握手自检，不是每次请求的上游实时探测。没有暴露 Cookie 内容。
- `GET /api/transcribe/capabilities`：返回 `summary.available/provider/label/reason`、`queue_concurrency=1`、`cooldown_sec=2`。
- `summary.available` 基于登录态自检；实际对话仍可能遇到验证、过期或限流。

### 访问与集成方式

当前没有应用级 API Key；调用方不需要豆包 Cookie，登录态保留在服务端。部署层若另有访问控制，需要沿用已有授权配置。

从其他项目的后端调用即可；跨站网页直连还受 CORS 限制。当前只放行本机开发来源，没有默认允许任意网站跨域。推荐通过你的业务后端中转。服务是个人共享队列，没有用户隔离，能访问接口的调用方可以查询全部任务。

[完整 Markdown](/api/docs/markdown) · [OpenAPI](/openapi.json) · [交互式 HTTP 文档](/docs) · [Agent 索引](/llms.txt)

## 语音合成 TTS

### POST /api/tts

`Content-Type: application/json`。HTTP 200 返回音频字节流，不是 JSON。

| 字段 | 类型 | 默认值 / 限制 |
| --- | --- | --- |
| text | string，必填 | 1–2000 字符，不能全是空白 |
| speaker | string | 空字符串，使用豆包默认音色；可从音色接口获取 ID |
| format | string | aac；可选 aac / mp3 / opus / pcm |
| speech_rate | number | 1.0；范围 0.7–2.0 |
| pitch | integer | 0；范围 -10–10 |

```json
{
  "text": "让文字自然开口。",
  "speaker": "",
  "format": "aac",
  "speech_rate": 1.0,
  "pitch": 0
}
```

| format | 返回 Content-Type |
| --- | --- |
| aac | audio/aac |
| mp3 | audio/mpeg |
| opus | audio/ogg; codecs=opus |
| pcm | audio/pcm（原始数据，无 WAV 文件头） |

```powershell
$body = @{ text = "你好，这是一次语音合成测试"; format = "aac" } | ConvertTo-Json
Invoke-WebRequest "$base/api/tts" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile "speech.aac"
```

流开始后，上游异常无法再改写 HTTP 状态码。目前这类错误写入服务器日志，调用方应检查空音频及解码是否成功，不应把 HTTP 200 直接当作音频完整的保证。原始 PCM 建议在明确采样参数后再解码，跨项目优先使用 AAC / MP3。

### GET /api/speakers

返回 `{"default": "音色 ID", "speakers": [{"id": "音色 ID", "name": "音色名"}]}`。请求不需要参数；音色以该接口返回为准。

TTS 不在课程队列中，调用方应自行串行或限制并发；没有承诺固定的上游安全 RPS。

## 实时听写 WebSocket

### WS /ws/asr

公网使用 `wss://your-domain.example/ws/asr`。需要实时传音频时使用这个接口；已有文件或长课程通常直接用文件转录接口更方便。

### 上行帧

| 类型 | 内容 |
| --- | --- |
| binary | 原始 PCM：16000 Hz、单声道、signed 16-bit little-endian |
| text | 结束输入：`{"type":"finish"}` |

建议每帧 4096 字节（2048 个样本，128ms），按音频时间节奏发送。最后不足一帧时补零。不要把 WAV 文件头、MP3 数据或 Base64 文本当成 PCM 帧。发送 finish 后继续接收，直到 final 或 error；不要立即断开。

```powershell
ffmpeg -i input.wav -ar 16000 -ac 1 -f s16le output.pcm
```

### 下行事件

```json
{"type":"partial","text":"当前完整识别文本"}
{"type":"final"}
{"type":"queued","position":1,"message":"当前有任务正在使用 ASR，已进入第 1 位等待队列。"}
{"type":"ready"}
{"type":"error","code":"auth_expired","message":"登录态失效"}
```

- `partial.text` 是当前文本快照，每次替换；不要逐条追加，否则会重复。
- `final` 不携带文本；最终文字使用最后一次 partial.text。
- `error` 后结束会话；连接关闭但没收到 final 时，保留部分文字并标记未完整完成。
- 实时听写与课程识别共用一个 ASR 通道。通道忙时 WebSocket 保持连接并先返回 `queued`，服务端按 FIFO 顺序等待；拿到通道并连上豆包后返回 `ready`，客户端收到 `ready` 再开始发送音频。无效登录态用 `auth_expired` / 1008；上游连接失败可能以 1011 关闭。
- 这份 WebSocket 帧协议不包含在 HTTP OpenAPI 中。

```javascript
let transcript = '';
const ws = new WebSocket('wss://your-domain.example/ws/asr');
ws.binaryType = 'arraybuffer';
ws.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.type === 'partial') transcript = message.text;
  if (message.type === 'final') {
    console.log('完成:', transcript);
    ws.close();
  }
  if (message.type === 'error') {
    console.error(message.code, message.message);
    ws.close();
  }
};
// 收到 ready 后，由你的录音器按音频节奏调用 ws.send(pcmFrame)；收到 queued 时先等待。
// 采集结束：ws.send(JSON.stringify({ type: 'finish' }));
// 录音器须将麦克风音频重采样为 16kHz mono PCM16，不可直接发送 MediaRecorder 的 WebM。
```

## YouTube 课程转录

### POST /api/transcribe/url

`Content-Type: application/json`。HTTP 200 表示任务已创建，尚未完成；保存返回的 `id`，然后轮询任务详情。

| 字段 | 类型 | 默认值 / 限制 |
| --- | --- | --- |
| url | string，必填 | 1–2048 字符；YouTube 普通视频或 Shorts 链接 |
| summarize | boolean | false；true 表示识别完成后继续 AI 整理 |
| request_id | string | 可选，客户端为一次提交生成的幂等标识（最多 128 字符）；超时重试必须复用 |

支持 `youtube.com`、`www.youtube.com`、`m.youtube.com`、`music.youtube.com`、`youtu.be`。播放列表不会展开为多个任务。

```powershell
$body = @{ url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"; summarize = $true } | ConvertTo-Json
$job = Invoke-RestMethod "$base/api/transcribe/url" -Method Post -ContentType "application/json" -Body $body
$job.id
Invoke-RestMethod "$base/api/transcribe/jobs/$($job.id)"
```

返回完整 `JobDetail`，与任务详情接口同结构。文档示例链接是短公开视频，实际提交会调用豆包并产生任务。

## 本地文件转录

### POST /api/transcribe/file

`multipart/form-data`，不要使用 JSON 或服务器文件路径。上传实际文件字节。

| 表单字段 | 类型 | 默认值 / 限制 |
| --- | --- | --- |
| file | file，必填 | 非空音频 / 视频文件 |
| summarize | boolean | false；表单中传字符串 true / false |
| request_id | string | 可选，和 URL 提交相同；同一标识会返回原任务 |

支持扩展名：`.mp4 .mkv .mov .avi .webm .mp3 .wav .m4a .aac .flac .ogg .opus`。服务端应用上限为 1 GiB；公网代理可能有更低的限制。大文件可以在服务所在电脑上使用本机地址上传。

```powershell
curl.exe --fail-with-body "$base/api/transcribe/file" -F "file=@C:/media/lesson.mp4" -F "summarize=true"
```

不要手动设置 multipart 的 Content-Type 边界，让 HTTP 客户端生成。上传成功返回 HTTP 200 和 `JobDetail`，随后进入同一串行队列。

## 任务、进度与结果

### HTTP 接口

| 方法 | 路径 | 返回 / 行为 |
| --- | --- | --- |
| GET | /api/transcribe/jobs | JobInfo[]，按创建时间倒序，不包含结果全文；目前无分页 |
| GET | /api/transcribe/jobs/{job_id} | JobDetail，包含状态、耗时和全部已保存结果 |
| POST | /api/transcribe/jobs/{job_id}/cancel | 返回 JobDetail；只能取消尚未开始的排队任务 |
| GET | /api/transcribe/jobs/{job_id}/text | UTF-8 文字稿附件 .txt |
| GET | /api/transcribe/jobs/{job_id}/srt | UTF-8 字幕附件 .srt |
| GET | /api/transcribe/jobs/{job_id}/summary | UTF-8 Markdown 笔记附件 .md |

三个下载接口都返回 `text/plain; charset=utf-8` 并带 Content-Disposition（包括 UTF-8 文件名）。接口无对应结果时返回 400，任务不存在返回 404。SRT 当前按识别片段生成，时间精度为片段级，不是逐字对齐字幕。

### 状态与轮询

常见流程：`pending → downloading / extracting → chunking → recognizing → merging → summarizing（可选） → done`。等待实时录音释放识别通道时为 `waiting_asr`；流程也可能进入 `error` 或 `cancelled`。

每 2 秒查询详情，遇到 `done / error / cancelled` 停止轮询。阶段进度不是剩余时间预测，不应按百分比推算精确 ETA。

| 字段 | 说明 |
| --- | --- |
| id / client_request_id / title / source / source_type | 任务 ID、客户端幂等标识、标题、来源、url 或 file；文件来源只返回标题 |
| status / progress_pct / current_step | 状态、0–100 阶段进度、可展示的当前步骤 |
| total_chunks / done_chunks | 识别片段总数 / 已完成数量 |
| duration_sec | 音视频时长（秒），音频提取前为 0 |
| created_at / started_at / finished_at | Unix 时间戳，单位秒；未开始 / 未结束为 0 |
| server_time | 此响应生成时的服务器 Unix 时间 |
| elapsed_sec | 总耗时 = wait_sec + processing_sec |
| wait_sec | 从创建到开始处理；仍排队时持续增长 |
| processing_sec | 从出队到结束，包含下载、识别通道等待、识别及 AI 整理 |
| queue_position | 等待队列位置，从 1 开始；其他状态为 0 |
| summary_requested / summary_status / summary_error | 是否请求 AI、AI 状态和错误说明 |
| error | 整体任务失败原因，无失败时为空字符串 |

终态耗时冻结。页面实时计时应从响应中的秒数递增，不要直接用调用方时区计算。

### JobDetail 独有结果字段

| 字段 | 内容 |
| --- | --- |
| result_text | 纯文字稿 |
| srt_text | SRT 字幕全文 |
| structured_text | 带时间戳的 Markdown 原稿 |
| summary | AI 生成的 Markdown 学习笔记 |

这些字段在结果未产生时为空字符串。列表接口刻意省略四个全文字段；要读取结果须查询详情。全部字段、类型和枚举见 [OpenAPI](/openapi.json)。

## AI 整理与队列约定

### 转录后自动整理

提交 URL 或文件时指定 `summarize=true`。服务使用服务器上已有的豆包登录态，不需要额外 LLM Key；文字稿会交给该豆包账号整理，可能出现在会话历史中。

目前没有独立摘要或通用聊天端点；AI 整理随课程任务执行。只需原稿时传 `summarize=false`。

| summary_status | 含义 |
| --- | --- |
| not_requested | 未启用整理 |
| pending | 等待整理；整体任务提前失败时也可能保留此状态 |
| running | 正在调用豆包整理 |
| done | 已生成 summary |
| error | 整理失败，查看 summary_error |
| skipped | 没有识别到文字等原因导致跳过 |

必须同时看整体 `status` 和 `summary_status`。整体 `done` 表示转录流程结束，AI 仍可能 error 或 skipped；原稿和字幕保留。当前没有仅重试 AI 的端点，重新提交会创建新的完整任务。

长文字每 12,000 字分段串行整理，保留全部分段笔记；不保证合成为全篇统一大纲。

### 队列与恢复

- 同一个服务进程只执行一个课程任务，包含下载、识别及 AI 整理；结束后间隔 2 秒再执行下一项。
- 多个业务项目共用同一个队列。TTS 不参与此队列；实时听写和课程 ASR 共用识别通道。
- 浏览器刷新或客户端轮询超时不会取消服务端任务。
- 服务重启后恢复排队任务；正在处理的任务标记为中断；已经完成的结果保留在本机。
- 保持单个 Uvicorn worker。多个进程或独立 CLI 不共享内存队列与识别锁。
- POST 无幂等键；网络超时不能证明任务没创建，先查询历史再决定是否重提。
- 不承诺上游固定速率额度；不要依据旧压测数字提高并发。

## 错误与重试

保留现有接口的错误格式，调用方需兼容下列三种响应：

```json
{"detail":{"code":"auth_expired","message":"登录态失效"}}
{"detail":"任务不存在"}
{"detail":[{"loc":["body","text"],"msg":"Field required","type":"missing"}]}
```

| HTTP 状态 | 常见场景 | 处理 |
| --- | --- | --- |
| 400 | TTS 空白文本 / 格式错误；转录链接、文件或 AI 前置检查失败；结果尚不存在 | 读取 detail，修正参数或等待结果 |
| 404 | job_id 或示例语言不存在 | 检查标识，不循环重试 |
| 409 | 取消已开始或结束的任务 | 保留任务并查询其状态 |
| 413 | 应用上传超过 1 GiB；代理也可能返回其自身错误页 | 缩小文件或使用同机入口 |
| 422 | 缺字段、类型不合法、参数超出模型约束 | 读取 detail 数组定位字段 |
| 503 | TTS 登录态未加载 / 失效 | 服务端更新登录态后再调用 |
| 5xx / 网络中断 | 应用、上游或反向代理异常 | GET 可有限退避重试；POST 先查任务，避免重复 |

队列中的处理失败由 `job.status=error` 与 `job.error` 表达，查询这个任务仍返回 HTTP 200。AI 失败由 `summary_status=error` 表达。代理可能返回非 JSON，请保留通用 HTTP 错误处理。

TTS 音频流中途失败与 WebSocket error 的行为分别见对应章节。连接关闭不应一律解释为成功。

## Python 与 Node.js 示例

可下载的客户端包含健康检查、音色查询、TTS、URL / 文件提交、任务查询、取消、轮询和下载。示例默认只查健康，不会自动发起模型任务；显式调用生成方法后才执行。

[下载 Python 客户端](/api/docs/examples/python) · [下载 Node.js 客户端](/api/docs/examples/node)

### Python

依赖 Python 3.10+ 与 requests。将客户端保存为 `doubao_client.py`。

```powershell
python -m pip install requests
python doubao_client.py --base https://your-domain.example
```

```python
from pathlib import Path
from doubao_client import DoubaoClient

client = DoubaoClient("https://your-domain.example")
if not client.health()["ok"]:
    raise RuntimeError("请先确认服务端登录态")

# 语音合成
Path("speech.aac").write_bytes(client.tts("你好，欢迎回来。", format="aac"))

# 提交后保存 id；网络超时后可用同一个 id 继续查询。
job = client.submit_url("https://www.youtube.com/watch?v=jNQXAC9IVRw", summarize=True)
print("job_id:", job["id"], flush=True)
result = client.wait(job["id"], timeout=3600)
Path("transcript.txt").write_text(result["result_text"], encoding="utf-8")
if result["summary_status"] == "done":
    Path("notes.md").write_text(result["summary"], encoding="utf-8")
elif result["summary_requested"]:
    print("AI 提示:", result["summary_error"] or result["summary_status"])

# 文件提交：client.submit_file("lesson.mp4", summarize=True)
# 下载字幕：client.download(job["id"], "srt")
```

### Node.js

Node.js 18+，使用内置 fetch，不需要 npm 依赖。保存为 `doubao_client.mjs`。

```powershell
$env:DOUBAO_BASE_URL = "https://your-domain.example"
node doubao_client.mjs
```

```javascript
import { writeFile } from 'node:fs/promises';
import { DoubaoClient } from './doubao_client.mjs';

const client = new DoubaoClient(process.env.DOUBAO_BASE_URL);
if (!(await client.health()).ok) throw new Error('请先确认服务端登录态');
await writeFile('speech.aac', await client.tts('你好，欢迎回来。', { format: 'aac' }));

const job = await client.submitUrl('https://www.youtube.com/watch?v=jNQXAC9IVRw', true);
console.log('job_id:', job.id);
const result = await client.wait(job.id);
await writeFile('transcript.txt', result.result_text, 'utf8');
if (result.summary_status === 'done') await writeFile('notes.md', result.summary, 'utf8');
else if (result.summary_requested) console.warn(result.summary_error || result.summary_status);

// 文件提交：await client.submitFile('lesson.mp4', true)
// 下载字幕：await client.download(job.id, 'srt')
```

示例客户端上传普通文件时会占用与文件大小相关的内存，超大文件优先使用 `curl.exe -F`。客户端等待期限只结束等待，不会停止服务器任务；保留 job id 即可恢复查询。

## 给 Agent 的接入说明

可把下面这段交给其他项目的开发 Agent。先读取完整 Markdown 和 OpenAPI；不需要截图、浏览器登录态或本机源码。

```text
请为当前项目接入豆包语音工作室。
Base URL: https://your-domain.example
先读取 /llms.txt、/api/docs/markdown 和 /openapi.json。

从业务后端调用 HTTP / WebSocket，不读取或复制服务器 auth.json。
覆盖所需的 TTS、实时 ASR、课程转录与可选 AI 整理。
转录保存 job id，每 2 秒查询，终态 done/error/cancelled 停止轮询。
AI 成功单独判断 summary_status === "done"。
不要自动重试提交 POST；超时后查询历史，避免重复任务。
保持服务端单进程串行队列，不增加 worker 或绕过识别锁。
兼容 detail 字符串、对象、数组和代理非 JSON 错误。
WebSocket partial 是快照；final 无文本；finish 后等待 final 再断开。
按本项目的配置方式保存 Base URL，补充适合该项目的验证。
```

[Agent 索引](/llms.txt) 是入口摘要；[Markdown](/api/docs/markdown) 是完整协议说明；[OpenAPI](/openapi.json) 由运行代码生成，适合类型生成与工具接入。本文不包含任何登录凭据。
