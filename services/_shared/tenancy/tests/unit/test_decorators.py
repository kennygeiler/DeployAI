"""``@requires_tenant_scope`` rejects raw sessions and preserves signatures."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from deployai_tenancy import MissingTenantScope, requires_tenant_scope
from deployai_tenancy.session import TENANT_SCOPED_KEY


def _make_session(*, scoped: bool) -> AsyncSession:
    """Return an ``AsyncSession`` mock whose ``info`` dict matches ``scoped``."""
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True} if scoped else {}
    return session


async def test_accepts_scoped_session() -> None:
    @requires_tenant_scope
    async def op(session: AsyncSession) -> str:
        return "ok"

    assert await op(_make_session(scoped=True)) == "ok"


async def test_rejects_unscoped_session() -> None:
    @requires_tenant_scope
    async def op(session: AsyncSession) -> str:  # pragma: no cover - never called
        return "ok"

    with pytest.raises(MissingTenantScope, match="TenantScopedSession"):
        await op(_make_session(scoped=False))


async def test_rejects_missing_session_arg() -> None:
    @requires_tenant_scope
    async def op(x: int) -> int:  # pragma: no cover - never called
        return x

    with pytest.raises(MissingTenantScope, match="AsyncSession"):
        await op(42)  # type: ignore[arg-type]


async def test_finds_session_in_kwargs() -> None:
    @requires_tenant_scope
    async def op(*, session: AsyncSession) -> str:
        return "ok"

    assert await op(session=_make_session(scoped=True)) == "ok"


async def test_preserves_signature_and_docstring() -> None:
    @requires_tenant_scope
    async def op(session: AsyncSession, user_id: int) -> str:
        """Some docstring."""
        return f"{user_id}"

    assert op.__name__ == "op"
    assert op.__doc__ == "Some docstring."
    sig = inspect.signature(op)
    assert list(sig.parameters) == ["session", "user_id"]


async def test_bound_method_still_works() -> None:
    class Repo:
        @requires_tenant_scope
        async def fetch(self, session: AsyncSession) -> str:
            return "ok"

    repo = Repo()
    assert await repo.fetch(_make_session(scoped=True)) == "ok"

    with pytest.raises(MissingTenantScope):
        await repo.fetch(_make_session(scoped=False))


async def test_rejects_multiple_sessions_when_any_unscoped() -> None:
    """Every session in the call must be scoped — not just the first one."""

    @requires_tenant_scope
    async def op(scoped: AsyncSession, analytics: AsyncSession) -> str:  # pragma: no cover
        return "ok"

    with pytest.raises(MissingTenantScope):
        await op(_make_session(scoped=True), _make_session(scoped=False))


async def test_rejects_async_generator_functions() -> None:
    """Async generators are explicitly unsupported — fail fast at decoration time."""
    with pytest.raises(TypeError, match="async generator"):

        @requires_tenant_scope
        async def _gen(session: AsyncSession):  # type: ignore[no-untyped-def]  # pragma: no cover
            yield session


async def test_inner_function_awaited() -> None:
    """Ensure the wrapped coroutine is actually awaited (not just returned)."""
    mock_body = AsyncMock(return_value="body-ran")

    @requires_tenant_scope
    async def op(session: AsyncSession) -> str:
        return await mock_body()

    result = await op(_make_session(scoped=True))
    assert result == "body-ran"
    mock_body.assert_awaited_once()
