# Docker 安装与运维

Docker 版将前端、FastAPI、语音 SDK、Python 3.11、Node.js 22 和 FFmpeg 放入同一个镜像，默认单进程运行。宿主机只需 Git、Docker 和 Compose；无需另装 Python、Node.js 或 FFmpeg。

可部署到 Windows / macOS 的 Docker Desktop（Linux 容器模式）或 Linux Docker Engine。首次安装采用源码构建；目前不提供预构建镜像下载地址。

## 1. 检查 Docker

```text
docker version
docker compose version
```

`docker version` 应同时显示 Client 和 Server。需要 Compose v2.20+ 或更新版本。Docker 安装参见 [Docker Desktop](https://docs.docker.com/get-started/get-docker/) 或 [Linux Docker Engine](https://docs.docker.com/engine/install/)。

## 2. 克隆并配置登录态

```text
git clone https://github.com/FUKANFENG/doubao-voice-studio.git
cd doubao-voice-studio
```

Windows PowerShell：

```powershell
if (!(Test-Path auth.json)) { Copy-Item auth.example.json auth.json }
```

Linux / macOS：

```sh
test -f auth.json || cp auth.example.json auth.json
```

在本机编辑 `auth.json`，填写自己的 `cookie`、`web_id`、`tea_uuid`。已有配置可直接使用；不要用空白模板覆盖它。Docker 本身不会获取或刷新登录态。

获取方法：在豆包官网登录自己的账号，打开浏览器开发者工具的 Network 面板，触发语音输入或回复朗读，查找包含 `samantha/audio/asr` 或 `samantha/audio/tts` 的 WS 请求。从 Request Headers 复制完整 Cookie 值（不含 `Cookie:` 前缀），从同一请求的 URL 查询参数复制 `web_id` 与 `tea_uuid`。网页协议可能变化，以实际请求为准。

容器以 UID/GID `10001:10001` 运行。Linux 上若出现 Permission denied，请让该 UID 能读取挂载文件，例如使用 ACL：`setfacl -m u:10001:r auth.json`。无需将凭证文件设为全员可读。配置必须是有效 UTF-8 JSON，不能含注释或尾随逗号。

真实凭证只在运行时只读挂载到 `/app/auth.json`。`.dockerignore` 使用白名单，排除真实登录态、Git 历史、日志、转录记录、本机设置和依赖目录；不要把这些文件添加到 Dockerfile 的 COPY 中。

## 3. 构建并启动

```text
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
docker compose logs --tail 80 studio
```

打开 **http://127.0.0.1:8000**。初次构建需要联网下载镜像和依赖。构建产物仅保存在本机 Docker，不会上传你的凭证。

若构建阶段的依赖下载需要宿主机代理，可先按实际代理端口构建，再启动。例如：

```text
docker compose build --build-arg HTTP_PROXY=http://host.docker.internal:7890 --build-arg HTTPS_PROXY=http://host.docker.internal:7890
docker compose up -d --wait --wait-timeout 120
```

这只为构建时的包下载指定代理；基础镜像拉取使用 Docker 引擎自身的网络配置，运行时豆包代理仍由登录态配置决定。Linux 的构建环境需单独保证该代理地址可达。

容器内部监听 `0.0.0.0:8000`，默认仅向宿主机 `127.0.0.1:8000` 发布。Docker 的 healthy 表示 HTTP 服务可达，登录态有效性另看 `http://127.0.0.1:8000/api/health` 的 `auth_ok`。空白配置也能打开页面和文档，但不能使用豆包功能。

## 4. 端口、代理与 Cloudflare

按需将 `.env.example` 复制为 `.env` 后修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| DOUBAO_PORT | 8000 | 宿主机端口；容器内部仍为 8000 |
| DOUBAO_BIND_IP | 127.0.0.1 | 发布到宿主机的地址 |
| DOUBAO_AUTH_FILE | ./auth.json | 已存在的登录态文件；Windows 绝对路径建议使用正斜杠 |

例如原本的 Python 服务仍占用 8000 时，先设 `DOUBAO_PORT=18001` 验证 Docker 版。不要让两个实例同时用同一账号处理任务。原生安装的历史记录不会自动搬到 Docker 卷中。

**代理：**容器里的 `127.0.0.1` 是容器自身。如果登录态文件的 `proxy` 指向宿主机代理，将 Docker 使用的配置副本改为 `http://host.docker.internal:实际端口`。Compose 已添加 host-gateway 映射；代理仍需允许 Docker 网络访问。远程服务器上应使用服务器能访问的代理地址。不需要代理时保持空字符串。该字段用于豆包请求，YouTube 下载还取决于部署环境的出网条件。

**Cloudflare Tunnel 在宿主机运行：**服务 URL 使用 `http://127.0.0.1:8000`，改端口时同步修改。例如使用 18001 则填写 `http://127.0.0.1:18001`。

**Cloudflare Tunnel 在另一容器运行：**连接同一个 Compose 网络后使用 `http://studio:8000`。另一个容器的 localhost 不指向本服务。

远程使用麦克风需要 HTTPS；现有服务没有应用级鉴权，远程访问应沿用部署层的访问控制。需要局域网发布时可显式设置 `DOUBAO_BIND_IP=0.0.0.0` 并配置宿主机防火墙。

## 5. 持久化、更新与停止

| 挂载 | 内容 |
| --- | --- |
| auth.json → /app/auth.json | 宿主机提供、只读的登录态 |
| transcripts → /app/transcribe_out | 任务 JSON、文字稿、字幕和 AI 结果 |
| chats → /app/chat_out | 多轮对话历史 |
| uploads → /tmp/doubao_uploads | 尚未处理的上传文件 |

默认卷名为 `doubao-voice-studio_transcripts`、`doubao-voice-studio_chats` 和 `doubao-voice-studio_uploads`。设置不同 Compose 项目名（`-p`）会使用另一套卷。删除、重建容器会保留这三个卷；不要用 `docker compose down -v`，除非明确要清空数据。

先等待正在运行的任务完成，再更新：

```text
git pull --ff-only
docker compose up -d --build --wait --wait-timeout 120
```

只更新登录态文件时无需重建镜像，但需重建容器以重新挂载并加载文件：

```text
docker compose up -d --force-recreate --wait --wait-timeout 120
```

停止并保留数据：

```text
docker compose down
```

重新启动：

```text
docker compose up -d --wait --wait-timeout 120
```

`restart: unless-stopped` 会在 Docker 引擎重启后恢复未手动停止的容器；宿主机仍需启用 Docker 引擎自动启动。应用队列的并发仍为 1，不要增加 worker 或容器副本。排队任务在启动后恢复；运行中任务被停止后标记为中断，不能从音频片段断点续跑。

## 6. 备份

等待任务结束后，用下面的命令将三个卷复制到宿主机备份目录；如已有同名目录，请换一个新名称：

```text
docker compose stop studio
mkdir docker-backup
docker compose cp studio:/app/transcribe_out docker-backup/transcribe_out
docker compose cp studio:/app/chat_out docker-backup/chat_out
docker compose cp studio:/tmp/doubao_uploads docker-backup/doubao_uploads
docker compose start studio
```

另外在安全位置备份宿主机的 `auth.json`；不要提交到公开仓库。恢复到新的同版本容器前，应先停止它，使用 `docker compose cp` 复制备份目录内的内容到对应路径，并确保三个数据目录归 UID/GID 10001 所有。不要直接把 Windows 原生运行中的任务 JSON 搬进容器：其中的上传路径属于原宿主机。

## 7. 验证与常见问题

- **bind source path does not exist**：先创建真实的 `auth.json` 文件；Compose 特意关闭了缺失路径自动创建目录的行为。
- **port is already allocated**：调整 `DOUBAO_PORT`，或在切换前停止占用该端口的旧服务。
- **healthy 但 auth_ok=false**：检查 JSON、文件读取权限、会话是否过期及代理可达性；日志中的原因来自启动自检。
- **重新创建后找不到历史**：检查 Compose 项目名是否变化，以及三个 named volume 是否仍存在。
- **Docker 内存不足**：默认上限 2 GiB / 2 CPU，可按媒体大小调整 Compose 的 `mem_limit` 和 `cpus`；同时为上传、下载和 PCM 临时文件留足磁盘空间。

开发者可运行以下容器冒烟检查（额外需要宿主机 Python）。它使用空白配置、随机本地端口与独立测试卷，不调用真实豆包账号；完成后只清理测试资源：

```text
docker compose build
python tests/docker_smoke.py
```

参考：[Compose 配置插值](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)、[Docker 卷](https://docs.docker.com/engine/storage/volumes/)。
