"""A fair, process-local ASR slot shared by live and course transcription."""
from __future__ import annotations

import asyncio


class AsrSlot:
    """A FIFO wrapper around :class:`asyncio.Lock` with queue visibility."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._waiting = 0

    def locked(self) -> bool:
        return self._lock.locked()

    @property
    def waiting(self) -> int:
        return self._waiting

    def position(self) -> int:
        """Return the 1-based position for a new waiter, or 0 if free."""
        return self._waiting + 1 if self._lock.locked() else 0

    async def __aenter__(self) -> "AsrSlot":
        self._waiting += 1
        try:
            await self._lock.acquire()
        except BaseException:
            self._waiting -= 1
            raise
        self._waiting -= 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._lock.release()


asr_slot = AsrSlot()
