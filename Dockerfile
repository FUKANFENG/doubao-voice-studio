# syntax=docker/dockerfile:1
# Both stages use Debian Bookworm; the runtime also needs Node for yt-dlp.
FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    FFMPEG_PATH=/usr/bin/ffmpeg
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 studio \
    && useradd --uid 10001 --gid studio --create-home studio \
    && mkdir -p /app/transcribe_out /tmp/doubao_uploads \
    && chown studio:studio /app/transcribe_out /tmp/doubao_uploads
RUN mkdir -p /app/chat_out && chown studio:studio /app/chat_out
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY vendor/doubao_voice/ ./vendor/doubao_voice/
COPY API.md ./API.md
COPY docs/llms.txt ./docs/llms.txt
COPY examples/ ./examples/
COPY --from=frontend /build/frontend/dist/ ./frontend/dist/
# Credentials are mounted only at runtime. No auth.json is copied into a layer.
USER 10001:10001
EXPOSE 8000
# Liveness only: an expired account must not make the documentation unavailable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
