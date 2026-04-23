"""``@requires_tenant_scope`` — runtime guard for repository/service functions.

Decorate any async function that accepts an :class:`AsyncSession` as one of its
arguments to assert that the session was minted by
:func:`~deployai_tenancy.session.TenantScopedSession`. If the session is a raw
unscoped one, the decorator raises :class:`~deployai_tenancy.errors.MissingTenantScope`
*before* any SQL is issued.

This is the application-layer half of the NFR23 contract. The database-layer
half (RLS) would also refuse the query, but catching it early produces a clean
stack trace pointing at the caller rather than a generic ``InsufficientPrivilege``
from Postgres.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from deployai_tenancy.errors import MissingTenantScope
from deployai_tenancy.session import TENANT_SCOPED_KEY


def _find_sessions(args: tuple[object, ...], kwargs: dict[str, object]) -> list[AsyncSession]:
    """Return *every* :class:`AsyncSession` present in ``args`` or ``kwargs``.

    Validating all sessions (not just the first) closes the hole where a
    function accepting a primary scoped session plus a secondary unscoped
    session would silently let the secondary through.
    """
    sessions: list[AsyncSession] = []
    for arg in args:
        if isinstance(arg, AsyncSession):
            sessions.append(arg)
    for value in kwargs.values():
        if isinstance(value, AsyncSession):
            sessions.append(value)
    if not sessions:
        raise MissingTenantScope(
            "@requires_tenant_scope expects an AsyncSession in the wrapped function's arguments; none found.",
        )
    return sessions


def requires_tenant_scope[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Assert every session passed to ``func`` was minted by ``TenantScopedSession``.

    Usage:

    .. code-block:: python

        @requires_tenant_scope
        async def list_events(session: AsyncSession) -> list[CanonicalMemoryEvent]:
            result = await session.execute(select(CanonicalMemoryEvent))
            return list(result.scalars())

    :raises MissingTenantScope: if no ``AsyncSession`` is found in the call, or
        if *any* session in the call lacks the ``is_tenant_scoped`` flag.
    :raises TypeError: when decorating an async generator — pgcrypto/tenant
        patterns around generators aren't established yet; fail fast at
        decoration time rather than produce a cryptic await-error at call.
    """
    if inspect.isasyncgenfunction(func):
        raise TypeError(
            "@requires_tenant_scope does not support async generator functions. "
            "Wrap the generator body in a helper coroutine instead.",
        )

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        sessions = _find_sessions(args, kwargs)
        for session in sessions:
            if not session.info.get(TENANT_SCOPED_KEY):
                raise MissingTenantScope(
                    f"Function {func.__qualname__} requires a TenantScopedSession; "
                    "got a raw AsyncSession. Wrap the call in "
                    "`async with TenantScopedSession(tenant_id, engine) as session: ...`",
                )
        return await func(*args, **kwargs)

    return wrapper
