"""``TenantScopedSession`` contract, tested without a real database.

SQLAlchemy's ``AsyncSession`` + ``aiosqlite`` gives us an in-process async
engine to exercise the enter/exit flow, the ``session.info`` payload, and the
parameterized ``SET LOCAL`` call (sqlite silently accepts arbitrary
``set_config`` calls after we shim the function — see the autouse fixture).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from deployai_tenancy import (
    TENANT_ID_KEY,
    TENANT_SCOPED_KEY,
    IsolationViolation,
    MissingTenantScope,
    TenantScopedSession,
)
from deployai_tenancy.session import current_tenant

_SAMPLE_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncIterator[AsyncEngine]:
    """An in-process async sqlite engine with a ``set_config`` shim.

    ``SET LOCAL app.current_tenant = ...`` is Postgres-specific. We register a
    SQLite user-defined function ``set_config(name, value, is_local)`` that
    returns the value so :class:`TenantScopedSession`'s call succeeds without
    having to stand up Postgres.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _register_funcs(dbapi_conn: object, _: object) -> None:
        def _set_config(_name: str, value: str, _is_local: int) -> str:
            return value

        dbapi_conn.create_function("set_config", 3, _set_config)  # type: ignore[attr-defined]

    try:
        yield engine
    finally:
        await engine.dispose()


async def test_entering_yields_scoped_session(sqlite_engine: AsyncEngine) -> None:
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine) as session:
        assert session.info[TENANT_ID_KEY] == _SAMPLE_TENANT
        assert session.info[TENANT_SCOPED_KEY] is True
        assert current_tenant() == _SAMPLE_TENANT


async def test_enter_with_none_raises(sqlite_engine: AsyncEngine) -> None:
    with pytest.raises(MissingTenantScope, match="required"):
        async with TenantScopedSession(None, sqlite_engine):  # type: ignore[arg-type]
            pass


async def test_enter_with_string_raises(sqlite_engine: AsyncEngine) -> None:
    with pytest.raises(MissingTenantScope, match=r"uuid\.UUID"):
        async with TenantScopedSession("not-a-uuid", sqlite_engine):  # type: ignore[arg-type]
            pass


async def test_context_var_cleared_on_exit(sqlite_engine: AsyncEngine) -> None:
    assert current_tenant() is None
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine):
        assert current_tenant() == _SAMPLE_TENANT
    assert current_tenant() is None


async def test_context_var_cleared_on_exception(sqlite_engine: AsyncEngine) -> None:
    assert current_tenant() is None
    with pytest.raises(RuntimeError, match="boom"):
        async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine):
            raise RuntimeError("boom")
    assert current_tenant() is None


async def test_nested_same_tenant_allowed(sqlite_engine: AsyncEngine) -> None:
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine):
        async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine) as inner:
            assert inner.info[TENANT_ID_KEY] == _SAMPLE_TENANT


async def test_nested_different_tenant_raises(sqlite_engine: AsyncEngine) -> None:
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine):
        with pytest.raises(IsolationViolation, match="active scope"):
            async with TenantScopedSession(_OTHER_TENANT, sqlite_engine):
                pass


async def test_set_local_call_runs(sqlite_engine: AsyncEngine) -> None:
    """Prove the ``set_config`` shim actually gets the stringified UUID."""
    observed: list[tuple[str, str, int]] = []
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine) as session:
        # Re-issue the call inside the scope and capture the return value.
        result = await session.execute(
            text("SELECT set_config(:n, :v, 1)"),
            {"n": "app.current_tenant", "v": str(_SAMPLE_TENANT)},
        )
        observed.append(("app.current_tenant", result.scalar_one(), 1))
    assert observed == [("app.current_tenant", str(_SAMPLE_TENANT), 1)]


async def test_tenant_id_must_be_uuid_instance(sqlite_engine: AsyncEngine) -> None:
    class _FakeUUID:
        def __str__(self) -> str:
            return str(_SAMPLE_TENANT)

    with pytest.raises(MissingTenantScope):
        async with TenantScopedSession(_FakeUUID(), sqlite_engine):  # type: ignore[arg-type]
            pass


async def test_nil_uuid_rejected(sqlite_engine: AsyncEngine) -> None:
    """Defense-in-depth: nil UUID is a reserved sentinel, never a tenant id."""
    nil = uuid.UUID(int=0)
    with pytest.raises(MissingTenantScope, match="nil UUID"):
        async with TenantScopedSession(nil, sqlite_engine):
            pass


async def test_attributes_exposed_on_session(sqlite_engine: AsyncEngine) -> None:
    """AC2 literal: tenant_id + is_tenant_scoped available as attributes."""
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine) as session:
        assert session.tenant_id == _SAMPLE_TENANT  # type: ignore[attr-defined]
        assert session.is_tenant_scoped is True  # type: ignore[attr-defined]


async def test_app_role_guc_epic_2_1(sqlite_engine: AsyncEngine) -> None:
    """Epic 2.1: optional ``app_role`` runs the ``app.current_role`` ``set_config`` path."""
    async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine, app_role="platform_admin") as session:
        assert session.info[TENANT_ID_KEY] == _SAMPLE_TENANT


async def test_invalid_app_role_raises(sqlite_engine: AsyncEngine) -> None:
    with pytest.raises(MissingTenantScope, match="Invalid app_role"):
        async with TenantScopedSession(_SAMPLE_TENANT, sqlite_engine, app_role="not_a_real_role"):
            pass
