from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

SignFn = Callable[[Sequence[bytes]], Awaitable[None]]


def hash_payload(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()


@dataclass
class TsaBatcher:
    """Empties a pending digest list every `interval_sec` (default 5) — NFR6 amortization."""

    sign_digests: SignFn
    interval_sec: float = 5.0
    _pending: list[bytes] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _task: asyncio.Task[None] | None = None
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_sec)
            except TimeoutError:
                await self._flush()
        await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            batch: list[bytes] = self._pending[:]
            self._pending.clear()
        await self.sign_digests(batch)

    async def submit(self, digest: bytes) -> None:
        self.start()
        async with self._lock:
            self._pending.append(digest)

    async def flush_now(self) -> None:
        await self._flush()
