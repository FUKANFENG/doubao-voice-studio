"""Python 接入示例。依赖：python -m pip install requests
默认只检查健康；带 --youtube URL 才会创建真实转录任务。
"""
from __future__ import annotations
import argparse
import os
import time
from pathlib import Path
import requests


class DoubaoClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs):
        # 不自动重试 POST：响应丢失时任务可能已经创建。
        response = self.session.request(method, self.base_url + path,
                                        timeout=(10, 300), **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
                message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            except ValueError:
                message = response.text[:500]
            raise RuntimeError(f"HTTP {response.status_code}: {message}")
        return response

    def health(self):
        return self._request("GET", "/api/health").json()

    def speakers(self):
        return self._request("GET", "/api/speakers").json()

    def capabilities(self):
        return self._request("GET", "/api/transcribe/capabilities").json()

    def tts(self, text: str, **options) -> bytes:
        audio = self._request("POST", "/api/tts", json={"text": text, **options}).content
        if not audio:
            raise RuntimeError("返回了空音频，请检查服务端上游状态。")
        return audio

    def submit_url(self, url: str, summarize: bool = False):
        return self._request("POST", "/api/transcribe/url",
                             json={"url": url, "summarize": summarize}).json()

    def submit_file(self, path: str, summarize: bool = False):
        # requests multipart 适合普通文件；超大文件请用 curl.exe -F 流式上传。
        with Path(path).open("rb") as source:
            return self._request("POST", "/api/transcribe/file",
                                 files={"file": (Path(path).name, source)},
                                 data={"summarize": str(summarize).lower()}).json()

    def jobs(self):
        return self._request("GET", "/api/transcribe/jobs").json()

    def job(self, job_id: str):
        return self._request("GET", f"/api/transcribe/jobs/{job_id}").json()

    def cancel(self, job_id: str):
        return self._request("POST", f"/api/transcribe/jobs/{job_id}/cancel").json()

    def wait(self, job_id: str, timeout: float = 3600):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] in {"done", "error", "cancelled"}:
                if job["status"] != "done":
                    raise RuntimeError(job["error"] or f"任务 {job_id} 已取消")
                return job  # 还需要单独检查 summary_status。
            time.sleep(2)
        raise TimeoutError(f"等待任务 {job_id} 超时；服务端继续执行，可使用相同 id 查询。")

    def download(self, job_id: str, kind: str = "text") -> str:
        if kind not in {"text", "srt", "summary"}:
            raise ValueError("kind 只支持 text / srt / summary")
        response = self._request("GET", f"/api/transcribe/jobs/{job_id}/{kind}")
        return response.content.decode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("DOUBAO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--youtube", help="指定后才会创建任务")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    client = DoubaoClient(args.base)
    health = client.health()
    print(health)
    if args.youtube:
        if not health["ok"]:
            raise SystemExit("服务端登录态不可用")
        submitted = client.submit_url(args.youtube, summarize=args.summarize)
        print("已提交，请保存 job id:", submitted["id"], flush=True)
        result = client.wait(submitted["id"])
        print(result["result_text"])
        if result["summary_status"] == "done":
            print(result["summary"])
        elif result["summary_requested"]:
            print("AI 整理未完成:", result["summary_error"] or result["summary_status"])
