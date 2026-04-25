"""LangGraph checkpoint helpers with tenant namespacing (Epic 4 Story 4-1, AR6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

__all__ = [
    "async_postgres_saver",
    "checkpointer_thread_id",
]


def checkpointer_thread_id(*, tenant_id: uuid.UUID, run_key: str) -> str:
    """Return a ``thread_id`` for LangGraph checkpoint config (tenant-scoped, stable per run)."""
    r = (run_key or "").strip()
    if not r:
        msg = "run_key is required for checkpointer thread id"
        raise ValueError(msg)
    return f"tenant:{tenant_id}:run:{r}"


@asynccontextmanager
async def async_postgres_saver(
    connection_string: str,
) -> AsyncIterator[Any]:
    """Async ``AsyncPostgresSaver`` with schema ensured via :meth:`setup` (pooled, psycopg3)."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
        await saver.setup()
        yield saver
