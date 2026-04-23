"""Async engine + tenant-session glue for control-plane (Story 1.9).

Repositories and services should import :func:`tenant_session` and *never* the
shared package's :func:`TenantScopedSession` directly — that way if the engine
plumbing evolves (failover pool, read replicas) we can rewire it in one place.
"""

from __future__ import annotations

import os
from contextlib import AbstractAsyncContextManager
from functools import lru_cache
from uuid import UUID

from deployai_tenancy import TenantScopedSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine.

    Reads ``DATABASE_URL`` from the environment. Defaults to
    ``postgresql+psycopg://`` (psycopg 3 async mode) — the driver already in
    the dep stack and the one the integration suite uses. ``asyncpg`` would
    need a separate dep.
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://deployai:deployai@localhost:5432/deployai",
    )
    return create_async_engine(url, pool_pre_ping=True)


def tenant_session(tenant_id: UUID) -> AbstractAsyncContextManager[AsyncSession]:
    """Open a tenant-scoped session against the cached engine."""
    return TenantScopedSession(tenant_id, get_engine())


def clear_engine_cache() -> None:
    """Test hook: :func:`get_engine` is memoized; clear before switching ``DATABASE_URL``."""
    get_engine.cache_clear()
