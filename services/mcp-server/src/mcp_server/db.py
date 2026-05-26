"""Async SQLAlchemy session factory pointing at the same DB as control-plane.

We deliberately reuse the control-plane ORM models so the MCP server reads
from the same tables without duplicating schema knowledge. A read-only DB
role is preferred at deploy time; if the cluster doesn't have one, the
``ensure_read_only`` helper in :mod:`mcp_server.auth` short-circuits any
write attempt before it reaches the session.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # accept the same psycopg sync URL CP uses for migrations; coerce to asyncpg
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(_database_url(), future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


def clear_engine_cache() -> None:
    """Test helper: drop the cached engine + factory so a new DATABASE_URL takes effect."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


__all__ = ["clear_engine_cache", "get_engine", "get_session", "get_session_factory"]
