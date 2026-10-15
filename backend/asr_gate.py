"""One upstream ASR slot for course transcription and live recording."""
import asyncio

asr_slot = asyncio.Lock()
