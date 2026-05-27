"""Standalone embedder worker process (v2 Phase 5.5 Wave B, scope-v2 §10.2).

Polls ``embedding_jobs`` on a 2-second cadence, runs one tick per iteration,
and exits cleanly on SIGINT / SIGTERM. Invoked by the ``embedder``
docker-compose service as ``python -m control_plane.cli.embedder``.

Behaviour
---------
- Sleep 0s after a tick that processed jobs (drain as fast as possible).
- Sleep ``--poll-interval`` (default 2s) after an empty tick.
- Backoff to 10s after a tick that raised so a degraded Voyage/Postgres
  doesn't burn the log.

The CLI keeps the loop dumb on purpose — observability + alerting live in
the metrics pipeline, not in this script.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from types import FrameType

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane.workers.embedder import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    run_embedder_tick,
)

_log = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_S = 2.0
ERROR_BACKOFF_S = 10.0


def _coerce_async_url(url: str) -> str:
    """Force the ``postgresql+asyncpg`` driver — the worker uses asyncpg."""
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
        parsed = parsed.set(drivername="postgresql+asyncpg")
    return parsed.render_as_string(hide_password=False)


class _StopFlag:
    """Threadsafe stop flag flipped by SIGINT / SIGTERM handlers."""

    def __init__(self) -> None:
        self._stop = False

    def set(self, *_: object) -> None:
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop


async def _run_loop(
    database_url: str,
    *,
    batch_size: int,
    max_attempts: int,
    poll_interval_s: float,
    stop: _StopFlag,
) -> None:
    engine = create_async_engine(_coerce_async_url(database_url), pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        while not stop.stopped:
            try:
                async with maker() as session:
                    report = await run_embedder_tick(
                        session,
                        batch_size=batch_size,
                        max_attempts=max_attempts,
                    )
                    await session.commit()
            except Exception as exc:  # broad: never crash the loop
                _log.exception("embedder tick raised: %s", exc)
                await _interruptible_sleep(ERROR_BACKOFF_S, stop)
                continue

            if report.processed:
                _log.info(
                    "embedder tick: processed=%d succeeded=%d failed=%d latency_ms=%d",
                    report.processed,
                    report.succeeded,
                    report.failed,
                    report.latency_ms,
                )
                # No sleep — drain greedily while the queue has work.
                continue
            await _interruptible_sleep(poll_interval_s, stop)
    finally:
        await engine.dispose()


async def _interruptible_sleep(seconds: float, stop: _StopFlag) -> None:
    """Sleep in 0.5s slices so SIGTERM stops the loop within ~500 ms."""
    remaining = seconds
    slice_s = 0.5
    while remaining > 0 and not stop.stopped:
        await asyncio.sleep(min(slice_s, remaining))
        remaining -= slice_s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voyage-3 embedding backfill worker")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL; defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Jobs claimed per tick (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Mark a job failed after this many attempts (default {DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_S,
        help=f"Seconds to sleep after an empty tick (default {DEFAULT_POLL_INTERVAL_S})",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Python logging level (default INFO; override with $LOG_LEVEL)",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    stop = _StopFlag()

    def _signal_handler(signum: int, _frame: FrameType | None) -> None:
        _log.info("embedder received signal %s; draining and exiting", signum)
        stop.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        asyncio.run(
            _run_loop(
                args.database_url,
                batch_size=args.batch_size,
                max_attempts=args.max_attempts,
                poll_interval_s=args.poll_interval,
                stop=stop,
            )
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
