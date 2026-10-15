"""Public contract tests: isolated in-process HTTP, never call Doubao."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import PROJECT_ROOT
from backend.transcribe.jobs import JobManager, JobStatus
from backend.tts_route import require_auth


class DeveloperContractTests(unittest.TestCase):
    def setUp(self):
        # Intentionally not entering lifespan: tests must not probe a real account.
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_markdown_index_and_examples_are_readable_without_spa_fallback(self):
        response = self.client.get("/api/docs/markdown")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/markdown"))
        self.assertEqual(response.text, (PROJECT_ROOT / "API.md").read_text(encoding="utf-8"))
        self.assertIn("/ws/asr", response.text)
        self.assertIn("summary_status", response.text)
        self.assertIn("/openapi.json", self.client.get("/llms.txt").text)
        for language, filename in (("python", "doubao_client.py"), ("node", "doubao_client.mjs")):
            example = self.client.get("/api/docs/examples/" + language)
            self.assertEqual(example.status_code, 200)
            self.assertIn(filename, example.headers["content-disposition"])
            self.assertEqual(example.text, (PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
        self.assertEqual(self.client.get("/api/docs/examples/auth.json").status_code, 404)

    def test_openapi_contains_typed_results_binary_audio_and_correct_mime_types(self):
        schema = self.client.get("/openapi.json").json()
        self.assertNotIn("/{full_path}", schema["paths"])
        self.assertNotIn("/", schema["paths"])
        operations = [method for route in schema["paths"].values() for method in route.values()]
        ids = [operation["operationId"] for operation in operations]
        self.assertEqual(len(ids), len(set(ids)))
        audio = schema["paths"]["/api/tts"]["post"]["responses"]["200"]["content"]
        self.assertNotIn("application/json", audio)
        self.assertEqual(audio["audio/aac"]["schema"]["format"], "binary")
        self.assertIn("text/markdown", schema["paths"]["/api/docs/markdown"]["get"]["responses"]["200"]["content"])
        download = schema["paths"]["/api/transcribe/jobs/{job_id}/text"]["get"]["responses"]
        self.assertIn("text/plain", download["200"]["content"])
        self.assertIn("application/json", download["404"]["content"])
        job = schema["components"]["schemas"]["JobDetail"]["properties"]
        self.assertIn("summary_status", job)
        self.assertIn("result_text", job)
        self.assertNotIn("result_text", schema["components"]["schemas"]["JobInfo"]["properties"])

    def test_job_submission_history_cancel_and_download_preserve_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder))
            with patch("backend.transcribe_api.manager", manager):
                submitted = self.client.post("/api/transcribe/url", json={"url": "https://youtu.be/jNQXAC9IVRw"})
                self.assertEqual(submitted.status_code, 200)
                detail = submitted.json()
                self.assertEqual(detail["summary_status"], "not_requested")
                self.assertEqual(detail["queue_position"], 1)
                job_id = detail["id"]
                history = self.client.get("/api/transcribe/jobs").json()
                self.assertNotIn("result_text", history[0])
                fetched = self.client.get(f"/api/transcribe/jobs/{job_id}").json()
                self.assertEqual(fetched["id"], job_id)
                self.assertEqual(fetched["result_text"], "")
                self.assertGreaterEqual(fetched["elapsed_sec"], fetched["processing_sec"])
                cancelled = self.client.post(f"/api/transcribe/jobs/{job_id}/cancel")
                self.assertEqual(cancelled.json()["status"], "cancelled")
                self.assertEqual(self.client.post(f"/api/transcribe/jobs/{job_id}/cancel").status_code, 409)
                manager.update(job_id, status=JobStatus.DONE, result_text="示例文字", summary="## 笔记", summary_status="done")
                self.assertEqual(self.client.get(f"/api/transcribe/jobs/{job_id}/text").text, "示例文字")
                missing = self.client.get("/api/transcribe/jobs/unknown/text")
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(missing.json(), {"detail": "任务不存在"})

    def test_file_submission_and_three_error_shapes(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder) / "jobs")
            with patch("backend.transcribe_api.manager", manager), patch("backend.transcribe_api.UPLOAD_DIR", Path(folder)):
                uploaded = self.client.post("/api/transcribe/file", files={"file": ("lesson.wav", b"fake-audio")}, data={"summarize": "false"})
                self.assertEqual(uploaded.status_code, 200)
                self.assertEqual(uploaded.json()["source_type"], "file")
                self.assertEqual(uploaded.json()["source"], "lesson")
                bad_url = self.client.post("/api/transcribe/url", json={"url": "https://example.com"})
                self.assertIsInstance(bad_url.json()["detail"], str)
                validation = self.client.post("/api/transcribe/url", json={})
                self.assertEqual(validation.status_code, 422)
                self.assertIsInstance(validation.json()["detail"], list)
        app.dependency_overrides[require_auth] = lambda: object()
        try:
            bad_tts = self.client.post("/api/tts", json={"text": "   "})
            self.assertEqual(bad_tts.status_code, 400)
            self.assertEqual(bad_tts.json()["detail"]["code"], "invalid_text")
            async def audio(req, auth):
                yield b"test-aac-audio"
            with patch("backend.tts_route._tts_stream", audio):
                response = self.client.post("/api/tts", json={"text": "hello"})
                self.assertEqual(response.content, b"test-aac-audio")
                self.assertEqual(response.headers["content-type"], "audio/aac")
        finally:
            app.dependency_overrides.pop(require_auth, None)


if __name__ == "__main__":
    unittest.main()
