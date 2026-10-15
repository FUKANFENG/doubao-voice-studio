import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.transcribe.jobs import JobManager, JobStatus
from backend.transcribe.downloader import extract_pcm
from backend.transcribe.chunker import split_pcm
from backend.transcribe.summarizer import decode_event
from backend.transcribe_api import UrlSubmission, submit_url, _download
from backend.asr_gate import AsrSlot
from fastapi import HTTPException


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_asr_slot_waits_in_fifo_order(self):
        slot = AsrSlot()
        events = []

        async def work(name, pause=0):
            async with slot:
                events.append(f"{name}:start")
                await asyncio.sleep(pause)
                events.append(f"{name}:end")

        first = asyncio.create_task(work("first", 0.02))
        await asyncio.sleep(0)
        second = asyncio.create_task(work("second"))
        third = asyncio.create_task(work("third"))
        await asyncio.gather(first, second, third)
        self.assertEqual(events, ["first:start", "first:end", "second:start", "second:end", "third:start", "third:end"])

    async def test_fifo_one_worker_failure_does_not_block_and_cancel_skips(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder), cooldown_sec=0)
            calls = []
            active = maximum = 0
            async def runner(job, **kwargs):
                nonlocal active, maximum
                active += 1
                maximum = max(active, maximum)
                calls.append(job.source)
                await asyncio.sleep(0.01)
                active -= 1
                if job.source == "bad":
                    raise RuntimeError("simulated error")
                manager.update(job.id, status=JobStatus.DONE, finished_at=time.time())
            manager.start(runner)
            jobs = [manager.create(source) for source in ("one", "cancel", "bad", "last")]
            self.assertTrue(manager.cancel(jobs[1]))
            for job in jobs:
                manager.enqueue(job)
            await asyncio.wait_for(manager._queue.join(), timeout=2)
            await manager.stop()
            self.assertEqual(calls, ["one", "bad", "last"])
            self.assertEqual(maximum, 1)
            self.assertEqual(jobs[2].status, JobStatus.ERROR)
            self.assertEqual(jobs[3].status, JobStatus.DONE)
            self.assertGreaterEqual(jobs[3].started_at, jobs[2].finished_at)

    async def test_history_restores_and_queued_jobs_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            first = JobManager(Path(folder), cooldown_sec=0)
            done = first.create("done")
            first.update(done.id, status=JobStatus.DONE, result_text="历史文字", finished_at=time.time())
            interrupted = first.create("interrupted")
            first.update(interrupted.id, status=JobStatus.RECOGNIZING, started_at=time.time())
            queued = first.create("queued")
            second = JobManager(Path(folder), cooldown_sec=0)
            calls = []
            async def runner(job, **kwargs):
                calls.append(job.id)
                second.update(job.id, status=JobStatus.DONE, finished_at=time.time())
            second.start(runner)
            await asyncio.wait_for(second._queue.join(), timeout=2)
            await second.stop()
            self.assertEqual(calls, [queued.id])
            self.assertEqual(second.get(done.id).result_text, "历史文字")
            self.assertEqual(second.get(interrupted.id).status, JobStatus.ERROR)

    async def test_url_validation_rejects_lookalike_hosts(self):
        for url in ["https://youtube.com.evil.test/watch?v=1", "https://example.com/youtube.com", "ftp://youtube.com/a", "https://youtube.com:bad/a"]:
            with self.assertRaises(HTTPException):
                await submit_url(UrlSubmission(url=url))

    def test_elapsed_is_wait_plus_processing_and_freezes(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder))
            job = manager.create("one")
            manager.update(job.id, created_at=100, started_at=110, finished_at=135, status=JobStatus.DONE)
            with patch("backend.transcribe.jobs.time.time", return_value=999):
                result = manager.to_dict(job)
            self.assertEqual((result["wait_sec"], result["processing_sec"], result["elapsed_sec"]), (10, 25, 35))
            manager.update(job.id, started_at=0, finished_at=0, status=JobStatus.PENDING)
            with patch("backend.transcribe.jobs.time.time", return_value=120):
                result = manager.to_dict(job)
            self.assertEqual((result["wait_sec"], result["processing_sec"], result["queue_position"]), (20, 0, 1))

    def test_chunking_preserves_short_audio_and_final_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.pcm"
            for byte_count, expected_chunks in ((3200, 1), (32000 * 50, 1), (32000 * 51 + 30, 2)):
                source.write_bytes(bytes(byte_count))
                chunks = split_pcm(str(source), str(Path(folder) / "chunks"))
                self.assertEqual(len(chunks), expected_chunks)
                self.assertEqual(chunks[-1].end_sec, byte_count / 32000)
                self.assertEqual(Path(chunks[0].pcm_path).stat().st_size, min(byte_count, 32000 * 50))

    def test_pcm_duration_uses_samples_not_container_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            def run(command, **kwargs):
                Path(command[-1]).write_bytes(bytes(32000 * 3))
            with patch("backend.transcribe.downloader._run", side_effect=run):
                media = extract_pcm("sample.wav", folder, "sample")
            self.assertEqual(media.duration_sec, 3)

    def test_sse_answer_delta_snapshot_finish_and_error(self):
        def event(detail, kind=2001):
            return json.dumps({"event_type": kind, "event_data": json.dumps(detail)})
        self.assertEqual(decode_event(event({"message": {"content_type": 2001, "content": '{"text":"hello"}'}, "is_delta": True})), ("hello", True, False))
        self.assertEqual(decode_event(event({"message": {"content_type": 2001, "content": '{"text":"full"}'}, "is_delta": False, "is_finish": True})), ("full", False, True))
        self.assertEqual(decode_event(event({}, 2003)), ("", True, True))
        with self.assertRaises(RuntimeError):
            decode_event(event({"code": 710022004}, 2005))

    def test_unicode_download_headers_and_file_path_not_exposed(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder))
            job = manager.create("C:/private/upload.wav", source_type="file", title='中文课程 "标题"')
            manager.update(job.id, result_text="内容", status=JobStatus.DONE)
            with patch("backend.transcribe_api.manager", manager):
                response = _download(job.id, "result_text", ".txt")
            self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])
            response.headers["content-disposition"].encode("latin-1")
            self.assertNotIn("private", manager.to_dict(job)["source"])


if __name__ == "__main__":
    unittest.main()
