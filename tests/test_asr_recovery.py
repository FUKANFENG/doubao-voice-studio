"""Recover a disconnected chunk without replaying completed chunks or losing text."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from backend.transcribe import pipeline, recognizer
from backend.transcribe.chunker import AudioChunk
from backend.transcribe.downloader import MediaInfo
from backend.transcribe.jobs import JobManager, JobStatus


def sample_chunks(folder: str, count: int = 3) -> list[AudioChunk]:
    return [AudioChunk(i, i * 50, (i + 1) * 50, str(Path(folder) / f'{i}.pcm'), 50)
            for i in range(count)]


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dropped_connection_retries_only_failed_chunk(self):
        chunks = sample_chunks('unused')
        progress, retries = [], []
        attempt = AsyncMock(side_effect=['first', ConnectionClosedError(None, None), 'second', 'third'])
        with patch.object(recognizer, '_load_auth', return_value={}), \
             patch.object(recognizer, '_recognize_one', attempt), \
             patch.object(recognizer.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            result = await recognizer.recognize_all(
                chunks, cooldown_sec=0,
                progress_cb=lambda *args: progress.append(args),
                retry_cb=lambda *args: retries.append(args))
        self.assertEqual(result, ['first', 'second', 'third'])
        self.assertEqual([call.args[0].index for call in attempt.await_args_list], [0, 1, 1, 2])
        self.assertEqual([item[0] for item in progress], [1, 2, 3])
        self.assertEqual(retries, [(1, 2, 3, 2.0)])
        self.assertIn(2.0, [call.args[0] for call in sleep.await_args_list])

    async def test_retries_are_bounded_and_keep_final_chunk_number(self):
        attempt = AsyncMock(side_effect=ConnectionClosedError(None, None))
        with patch.object(recognizer, '_load_auth', return_value={}), \
             patch.object(recognizer, '_recognize_one', attempt), \
             patch.object(recognizer.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(RuntimeError, '第 1/1 段.*3 次'):
                await recognizer.recognize_all(sample_chunks('unused', 1))
        self.assertEqual(attempt.await_count, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [2.0, 4.0])

    async def test_timeout_retries_but_rejection_file_error_and_cancellation_do_not(self):
        chunks = sample_chunks('unused', 1)
        errors = [RuntimeError('upstream rejected'), FileNotFoundError('missing audio'),
                  ConnectionClosedError(Close(1008, 'policy'), Close(1008, 'policy'), True),
                  asyncio.CancelledError()]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                attempt = AsyncMock(side_effect=error)
                with patch.object(recognizer, '_load_auth', return_value={}), \
                     patch.object(recognizer, '_recognize_one', attempt):
                    with self.assertRaises(type(error)):
                        await recognizer.recognize_all(chunks)
                self.assertEqual(attempt.await_count, 1)
        with patch.object(recognizer, '_load_auth', return_value={}), \
             patch.object(recognizer, '_recognize_one', new_callable=AsyncMock,
                          side_effect=[TimeoutError(), 'recovered']), \
             patch.object(recognizer.asyncio, 'sleep', new_callable=AsyncMock):
            self.assertEqual(await recognizer.recognize_all(chunks), ['recovered'])

    async def test_receive_timeout_remains_retryable(self):
        with tempfile.TemporaryDirectory() as folder:
            chunk = sample_chunks(folder, 1)[0]
            Path(chunk.pcm_path).write_bytes(b'\x00\x00')
            ws = AsyncMock()
            ws.__aenter__.return_value = ws
            ws.recv.side_effect = TimeoutError()
            with patch.object(recognizer, 'ws_connect', new_callable=AsyncMock, return_value=ws):
                from doubao_voice import Auth
                with self.assertRaises(TimeoutError):
                    await recognizer._recognize_one(chunk, Auth())

    async def test_pipeline_persists_completed_segments_before_later_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager(Path(folder) / 'jobs')
            job = manager.create('https://youtu.be/example', summarize=True)
            chunks = sample_chunks(folder)

            async def fail_after_progress(chunks, progress_cb, **kwargs):
                progress_cb(1, 3, '第一段内容')
                progress_cb(2, 3, '第二段内容')
                saved = json.loads((manager.storage_dir / f'{job.id}.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['result_text'], '第一段内容\n\n第二段内容')
                self.assertEqual(saved['done_chunks'], 2)
                raise RuntimeError('第 3/3 段识别连接中断')

            with patch.object(pipeline, 'manager', manager), \
                 patch.object(pipeline, 'TEMP_ROOT', str(Path(folder) / 'work')), \
                 patch.object(pipeline, 'download_youtube', return_value=MediaInfo('unused', 'test', 150)), \
                 patch.object(pipeline, 'split_pcm', return_value=chunks), \
                 patch.object(recognizer, 'recognize_all', side_effect=fail_after_progress):
                await pipeline.run_pipeline(job, is_url=True, do_summarize=True)
            self.assertEqual(job.status, JobStatus.ERROR)
            self.assertEqual(job.done_chunks, 2)
            self.assertEqual(job.result_text, '第一段内容\n\n第二段内容')
            self.assertIn('00:00:50,000 --> 00:01:40,000', job.srt_text)
            self.assertIn('**[00:50]** 第二段内容', job.structured_text)
            self.assertIn('2/3', job.current_step)
            self.assertEqual(job.summary_status, 'skipped')


if __name__ == '__main__':
    unittest.main()
