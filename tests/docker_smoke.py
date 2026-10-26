"""Test a built Compose image without a real account or upstream calls.

Run: python tests/docker_smoke.py (after docker compose build).
Only the randomly named test project's containers and volumes are removed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "doubao-voice-studio:local"


def run(args: list[str], *, env: dict[str, str], source: str | None = None) -> str:
    result = subprocess.run(args, cwd=ROOT, env=env, input=source, text=True,
                            encoding="utf-8", capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args!r}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def main() -> None:
    project = "doubao-smoke-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=project) as folder:
        folder_path = Path(folder)
        auth = folder_path / "auth.json"
        auth.write_bytes((ROOT / "auth.example.json").read_bytes())
        # This is a blank test fixture, readable by the image's non-root uid.
        auth.chmod(0o644)
        empty_env = folder_path / "empty.env"
        empty_env.touch()
        env = {**os.environ, "DOUBAO_AUTH_FILE": str(auth),
               "DOUBAO_PORT": "0", "DOUBAO_BIND_IP": "127.0.0.1"}
        compose = ["docker", "compose", "--project-name", project,
                   "--env-file", str(empty_env), "--file", str(ROOT / "compose.yaml")]

        def command(*args: str, source: str | None = None) -> str:
            return run([*compose, *args], env=env, source=source)

        def fetch(path: str, method: str = "GET") -> bytes:
            address = command("port", "studio", "8000").splitlines()[0]
            request = urllib.request.Request(f"http://{address}{path}", method=method)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=10) as response:
                return response.read()

        # Inspect the unmounted image; credentials must not be baked into a layer.
        run(["docker", "run", "--rm", "-i", IMAGE, "python", "-"], env=env, source="""
import os, pathlib, subprocess, tempfile, wave
assert os.getuid() == 10001
root = pathlib.Path('/app')
assert not list(root.rglob('auth*.json'))
assert not list(root.rglob('.env*'))
for name in ('settings.local.json', 'llm.json', '.git', 'backups'):
    assert not (root / name).exists(), name
assert not (root / 'frontend/node_modules').exists()
subprocess.run(['node', '--version'], check=True)
subprocess.run(['yt-dlp', '--version'], check=True)
from backend.transcribe.downloader import extract_pcm
with tempfile.TemporaryDirectory() as folder:
    wav_path = str(pathlib.Path(folder) / 'silence.wav')
    with wave.open(wav_path, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(32000))
    result = extract_pcm(wav_path, folder)
    assert result.duration_sec == 1.0
""")
        try:
            command("up", "-d", "--no-build", "--wait", "--wait-timeout", "90")
            assert json.loads(fetch("/api/health"))["auth_loaded"] is False
            assert json.loads(fetch("/api/transcribe/capabilities"))["queue_concurrency"] == 1
            assert "/api/transcribe/file" in json.loads(fetch("/openapi.json"))["paths"]
            assert json.loads(fetch("/api/chat/sessions")) == []
            chat = json.loads(fetch("/api/chat/sessions", method="POST"))
            asset = re.search(r'src="(/assets/[^\"]+\.js)"', fetch("/").decode())
            assert asset and len(fetch(asset.group(1))) > 1000
            for path in ("/api/docs/markdown", "/llms.txt",
                         "/api/docs/examples/python", "/api/docs/examples/node"):
                assert fetch(path)
            # Seed a completed result and an upload fixture as the runtime uid.
            command("exec", "-T", "studio", "python", "-", source="""
import os, time
from pathlib import Path
from backend.transcribe.jobs import JobManager, JobStatus
assert os.getuid() == 10001
try:
    Path('/app/auth.json').open('a').close()
except OSError:
    pass
else:
    raise AssertionError('auth mount must be read-only')
Path('/tmp/doubao_uploads/persistence-fixture.wav').write_bytes(b'queued-upload-fixture')
manager = JobManager()
job = manager.create('docker-smoke', request_id='docker-smoke-history')
manager.update(job.id, status=JobStatus.DONE, result_text='persistent result',
               finished_at=time.time())
""")
            command("up", "-d", "--no-build", "--force-recreate",
                    "--wait", "--wait-timeout", "90")
            jobs = json.loads(fetch("/api/transcribe/jobs"))
            job = next(item for item in jobs if item["client_request_id"] == "docker-smoke-history")
            assert job["status"] == "done"
            assert json.loads(fetch("/api/transcribe/jobs/" + job["id"]))["result_text"] == "persistent result"
            command("exec", "-T", "studio", "python", "-c",
                    "from pathlib import Path; assert Path('/tmp/doubao_uploads/persistence-fixture.wav').read_bytes() == b'queued-upload-fixture'")
            assert json.loads(fetch("/api/chat/sessions/" + chat["id"]))["id"] == chat["id"]
            print("Docker smoke passed: UI/API/docs, non-root, read-only auth, Node/FFmpeg/yt-dlp, persistence.")
        finally:
            # The project name is generated here; never operate on the user's stack.
            command("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
