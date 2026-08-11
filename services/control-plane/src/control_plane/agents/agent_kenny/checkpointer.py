"""Process-wide AsyncPostgresSaver for the LangGraph runtime (pilot-refresh D1).

Owns the long-lived psycopg connection pool the checkpointer writes
through. The pool is lazily created from ``DATABASE_URL`` on first use and
cached per conninfo string, so tests that repoint ``DATABASE_URL`` at a
fresh container get a fresh pool automatically (mirrors
``control_plane.db.get_engine``'s cache-by-env posture, but keyed by value
instead of memoized once).

Schema: the checkpoint tables are created by Alembic migration
``20260811_0054_langgraph_checkpoints`` — the saver's runtime ``setup()``
is never called here, preserving the migrate-then-serve invariant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from control_plane.agents.agent_kenny.types import (
    AdversarialConcern,
    AgentState,
    CitationReport,
    VerifiedCitation,
)

_log = logging.getLogger(__name__)

_DRIVER_SUFFIX_RE = re.compile(r"^postgresql\+[a-z0-9]+://")

# AgentState nests dataclasses from types.py (CitationReport,
# VerifiedCitation, AdversarialConcern). Registering the concrete types
# keeps JsonPlusSerializer's msgpack path happy when
# LANGGRAPH_STRICT_MSGPACK flips on in a future library version.
_ALLOWED_MSGPACK_TYPES: tuple[type, ...] = (
    AgentState,
    CitationReport,
    VerifiedCitation,
    AdversarialConcern,
)

_POOL_MAX_SIZE = 4

_SaverPool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]]

_lock = asyncio.Lock()
_cached: tuple[str, _SaverPool, AsyncPostgresSaver] | None = None


def checkpointer_conninfo() -> str:
    """Return the plain-``postgresql://`` conninfo derived from ``DATABASE_URL``."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://deployai:deployai@localhost:5432/deployai",
    )
    return _DRIVER_SUFFIX_RE.sub("postgresql://", url)


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return the cached saver, (re)building the pool when conninfo changed."""
    global _cached
    conninfo = checkpointer_conninfo()
    async with _lock:
        if _cached is not None and _cached[0] == conninfo:
            return _cached[2]
        if _cached is not None:
            await _close_locked()
        pool: _SaverPool = AsyncConnectionPool(
            conninfo,
            min_size=0,
            max_size=_POOL_MAX_SIZE,
            open=False,
            connection_class=cast("type[AsyncConnection[dict[str, Any]]]", AsyncConnection),
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        await pool.open()
        saver = AsyncPostgresSaver(
            conn=pool,
            serde=JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_TYPES),
        )
        _cached = (conninfo, pool, saver)
        return saver


async def close_checkpointer() -> None:
    """Close the pooled connections (app shutdown / test teardown)."""
    global _cached
    async with _lock:
        await _close_locked()


async def _close_locked() -> None:
    global _cached
    if _cached is None:
        return
    _, pool, _saver = _cached
    _cached = None
    try:
        await pool.close()
    except Exception:  # pragma: no cover — teardown best-effort
        _log.exception("checkpointer pool close failed")


__all__ = ["checkpointer_conninfo", "close_checkpointer", "get_checkpointer"]
