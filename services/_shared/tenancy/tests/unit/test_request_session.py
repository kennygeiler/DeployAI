"""``TenantScopedRequestSession`` contract — the commit-surviving variant.

Same sqlite + ``set_config`` shim approach as ``test_session.py``, with the
shim extended to *record* every call so we can prove the GUC is re-applied on
the transaction that begins after a mid-scope ``commit()`` — the exact hole
that makes plain :class:`TenantScopedSession` unsuitable for route handlers.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from deployai_tenancy import (
    TENANT_ID_KEY,
    TENANT_SCOPED_KEY,
    IsolationViolation,
    MissingTenantScope,
    TenantScopedRequestSession,
)
from deployai_tenancy.session import current_tenant

_SAMPLE_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _GucRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, name: str, value: str, _is_local: int) -> str:
        self.calls.append((name, value))
        return value


@pytest_asyncio.fixture
async def engine_and_recorder() -> AsyncIterator[tuple[AsyncEngine, _GucRecorder]]:
    recorder = _GucRecorder()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _register_funcs(dbapi_conn: object, _: object) -> None:
        dbapi_conn.create_function("set_config", 3, recorder)  # type: ignore[attr-defined]

    try:
        yield engine, recorder
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_guc_reapplied_after_commit(engine_and_recorder: tuple[AsyncEngine, _GucRecorder]) -> None:
    """The tenant GUC must be set on *every* transaction, not just the first."""
    engine, recorder = engine_and_recorder
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with TenantScopedRequestSession(_SAMPLE_TENANT, maker) as session:
        await session.execute(text("SELECT 1"))
        await session.commit()
        await session.execute(text("SELECT 1"))

    tenant_calls = [c for c in recorder.calls if c[0] == "app.current_tenant"]
    assert len(tenant_calls) == 2, "expected one set_config per transaction (before and after commit)"
    assert all(value == str(_SAMPLE_TENANT) for _, value in tenant_calls)


@pytest.mark.asyncio
async def test_session_is_flagged_tenant_scoped(engine_and_recorder: tuple[AsyncEngine, _GucRecorder]) -> None:
    engine, _ = engine_and_recorder
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with TenantScopedRequestSession(_SAMPLE_TENANT, maker) as session:
        assert session.info[TENANT_ID_KEY] == _SAMPLE_TENANT
        assert session.info[TENANT_SCOPED_KEY] is True
        assert session.tenant_id == _SAMPLE_TENANT  # type: ignore[attr-defined]
        assert session.is_tenant_scoped is True  # type: ignore[attr-defined]
        assert current_tenant() == _SAMPLE_TENANT
    assert current_tenant() is None


@pytest.mark.asyncio
async def test_validation_matches_tenant_scoped_session(
    engine_and_recorder: tuple[AsyncEngine, _GucRecorder],
) -> None:
    engine, _ = engine_and_recorder
    maker = async_sessionmaker(engine, expire_on_commit=False)

    with pytest.raises(MissingTenantScope):
        async with TenantScopedRequestSession(None, maker):  # type: ignore[arg-type]
            pass
    with pytest.raises(MissingTenantScope, match="nil UUID"):
        async with TenantScopedRequestSession(uuid.UUID(int=0), maker):
            pass
    with pytest.raises(MissingTenantScope, match="app_role"):
        async with TenantScopedRequestSession(_SAMPLE_TENANT, maker, app_role="not-a-role"):
            pass


@pytest.mark.asyncio
async def test_cross_tenant_nesting_forbidden(
    engine_and_recorder: tuple[AsyncEngine, _GucRecorder],
) -> None:
    engine, _ = engine_and_recorder
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with TenantScopedRequestSession(_SAMPLE_TENANT, maker):
        with pytest.raises(IsolationViolation):
            async with TenantScopedRequestSession(_OTHER_TENANT, maker):
                pass
        # Same-tenant nesting stays allowed.
        async with TenantScopedRequestSession(_SAMPLE_TENANT, maker):
            pass


@pytest.mark.asyncio
async def test_listener_removed_on_exit(engine_and_recorder: tuple[AsyncEngine, _GucRecorder]) -> None:
    """A later plain session from the same maker must not inherit the GUC hook."""
    engine, recorder = engine_and_recorder
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with TenantScopedRequestSession(_SAMPLE_TENANT, maker) as session:
        await session.execute(text("SELECT 1"))
    calls_before = len(recorder.calls)

    async with maker() as plain:
        await plain.execute(text("SELECT 1"))
    assert len(recorder.calls) == calls_before, "unscoped session must not set the tenant GUC"
