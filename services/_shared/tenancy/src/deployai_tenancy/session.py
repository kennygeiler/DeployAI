"""``TenantScopedSession`` — the one and only door into canonical memory.

Layer 1 of the NFR23 three-layer defense. Every call into Postgres from
application code MUST be made through a session minted by this context manager.
Layer 2 (RLS policies) then enforces the scope at the database level via the
``app.current_tenant`` GUC. A raw :class:`~sqlalchemy.ext.asyncio.AsyncSession`
without the scope returns zero rows for any SELECT against a canonical-memory
table because the policy ``USING (tenant_id = current_setting('app.current_tenant', true)::uuid)``
evaluates ``NULL = <tenant_id>`` → ``NULL`` → filter out.

Usage:

.. code-block:: python

    async with TenantScopedSession(tenant_id=my_uuid, engine=engine) as session:
        result = await session.execute(select(CanonicalMemoryEvent))

``SET LOCAL`` scopes the GUC to the enclosing transaction, so it evaporates on
exit without an explicit RESET. We use Postgres' ``set_config('name', value,
is_local=true)`` function with a bound parameter rather than concatenating a
literal SQL string — safer even though the value is already UUID-validated.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from deployai_tenancy.errors import IsolationViolation, MissingTenantScope

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Session, SessionTransaction

_APP_ROLES: frozenset[str] = frozenset(
    {
        "platform_admin",
        "customer_admin",
        "deployment_strategist",
        "successor_strategist",
        "customer_records_officer",
        "external_auditor",
    },
)

TENANT_ID_KEY = "tenant_id"
"""Key used in ``session.info`` to stash the active tenant id."""

TENANT_SCOPED_KEY = "is_tenant_scoped"
"""Key used in ``session.info`` flagged ``True`` by :func:`TenantScopedSession` on entry."""

_current_tenant: ContextVar[UUID | None] = ContextVar("deployai_current_tenant", default=None)
"""Process-local current tenant id, used to detect in-process cross-tenant nesting."""


def _validate_tenant_id(tenant_id: UUID | None) -> UUID:
    """Return ``tenant_id`` if it is a non-nil :class:`uuid.UUID`, else raise."""
    if tenant_id is None:
        raise MissingTenantScope("tenant_id is required; got None")
    if not isinstance(tenant_id, UUID):
        raise MissingTenantScope(
            f"tenant_id must be a uuid.UUID instance; got {type(tenant_id).__name__}",
        )
    if tenant_id.int == 0:
        # Defense-in-depth: reject the nil UUID as a reserved sentinel so no
        # accidentally-seeded row with `tenant_id=00000000-...` ever becomes
        # readable via a "default" scope. Story 1.10's fuzz harness attacks
        # this exact boundary.
        raise MissingTenantScope("nil UUID is reserved; pass a real tenant id")
    return tenant_id


def _validate_app_role(app_role: str | None) -> str | None:
    """Return the role string for ``SET LOCAL app.current_role``, or ``None`` to skip."""
    if app_role is None:
        return None
    if app_role not in _APP_ROLES:
        raise MissingTenantScope(f"Invalid app_role for app.current_role GUC: {app_role!r}")
    return app_role


@asynccontextmanager
async def TenantScopedSession(  # noqa: N802 — public API surface, PascalCase matches the
    # context-manager-as-constructor idiom used by :class:`contextlib.asynccontextmanager`.
    tenant_id: UUID,
    engine: AsyncEngine,
    *,
    app_role: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open an :class:`AsyncSession` with the tenant scope injected.

    :param tenant_id: the tenant whose rows the caller may read/write. Must be a
        :class:`uuid.UUID`; a string raises :class:`MissingTenantScope`.
    :param engine: the :class:`AsyncEngine` to bind the session to.
    :param app_role: optional V1 role string stored in ``SET LOCAL app.current_role``
        for Postgres policies (Epic 2.1). Must be a known role or ``None``.

    :raises MissingTenantScope: if ``tenant_id`` is ``None`` or not a UUID.
    :raises IsolationViolation: if an enclosing ``TenantScopedSession`` is
        already active for a *different* tenant id (nesting across tenants is
        forbidden).

    On exit, the transaction commits (or rolls back on exception). ``SET LOCAL``
    scopes the GUC to the transaction, so no explicit RESET is needed.
    """
    validated = _validate_tenant_id(tenant_id)
    role_for_guc = _validate_app_role(app_role)

    enclosing = _current_tenant.get()
    if enclosing is not None and enclosing != validated:
        raise IsolationViolation(
            f"Cannot open TenantScopedSession(tenant_id={validated}) inside an "
            f"active scope for tenant_id={enclosing}. "
            "Exit the outer scope or use the same tenant id.",
        )

    token = _current_tenant.set(validated)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            async with session.begin():
                # `set_config(name, value, is_local)` is the parameterizable
                # equivalent of `SET LOCAL name = value`. is_local=true scopes
                # the GUC to the current transaction.
                await session.execute(
                    text("SELECT set_config('app.current_tenant', :tid, true)"),
                    {"tid": str(validated)},
                )
                if role_for_guc is not None:
                    await session.execute(
                        text("SELECT set_config('app.current_role', :r, true)"),
                        {"r": role_for_guc},
                    )
                session.info[TENANT_ID_KEY] = validated
                session.info[TENANT_SCOPED_KEY] = True
                # AC2 literal: also expose as attributes on the session object
                # for callers that prefer `session.tenant_id` over `session.info[...]`.
                # ``AsyncSession`` does not use ``__slots__`` so this is safe.
                session.tenant_id = validated  # type: ignore[attr-defined]
                session.is_tenant_scoped = True  # type: ignore[attr-defined]
                yield session
    finally:
        _current_tenant.reset(token)


def current_tenant() -> UUID | None:
    """Return the tenant id of the enclosing :func:`TenantScopedSession`, if any."""
    return _current_tenant.get()


@asynccontextmanager
async def TenantScopedRequestSession(  # noqa: N802 — public API surface, PascalCase matches
    # the context-manager-as-constructor idiom used by :func:`TenantScopedSession`.
    tenant_id: UUID,
    maker: async_sessionmaker[AsyncSession],
    *,
    app_role: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a request-scoped :class:`AsyncSession` that survives ``commit()``.

    :func:`TenantScopedSession` wraps the whole scope in one transaction, so a
    caller that calls ``session.commit()`` mid-scope would silently drop the
    ``SET LOCAL`` GUC — every later statement would run *unscoped* and RLS
    would filter it to zero rows. Route handlers commit freely, so they need
    a session where the tenant GUC is re-applied at the start of **every**
    transaction, not just the first.

    This variant attaches an ``after_begin`` listener to the underlying sync
    session: each time a transaction begins on a connection, the listener runs
    ``set_config('app.current_tenant', <tenant>, is_local=true)`` before any
    caller statement executes. Commit → next autobegin → GUC re-applied. The
    same validation, nil-UUID rejection, and cross-tenant nesting guard as
    :func:`TenantScopedSession` apply.

    Unlike :func:`TenantScopedSession`, exiting the scope does **not** commit:
    pending changes are rolled back on close, matching the semantics of a bare
    request-scoped session (callers own their commits).
    """
    validated = _validate_tenant_id(tenant_id)
    role_for_guc = _validate_app_role(app_role)

    enclosing = _current_tenant.get()
    if enclosing is not None and enclosing != validated:
        raise IsolationViolation(
            f"Cannot open TenantScopedRequestSession(tenant_id={validated}) inside an "
            f"active scope for tenant_id={enclosing}. "
            "Exit the outer scope or use the same tenant id.",
        )

    token = _current_tenant.set(validated)
    try:
        async with maker() as session:

            def _apply_guc(
                _session: Session,
                transaction: SessionTransaction,
                connection: Connection,
            ) -> None:
                # SAVEPOINT (nested) transactions inherit the enclosing
                # transaction's GUC; only root transactions need it set.
                if transaction.nested:
                    return
                # Same parameterized set_config posture as TenantScopedSession;
                # executed on the Core connection so it lands inside the
                # freshly-begun transaction, before any caller statement.
                connection.execute(
                    text("SELECT set_config('app.current_tenant', :tid, true)"),
                    {"tid": str(validated)},
                )
                if role_for_guc is not None:
                    connection.execute(
                        text("SELECT set_config('app.current_role', :r, true)"),
                        {"r": role_for_guc},
                    )

            event.listen(session.sync_session, "after_begin", _apply_guc)
            session.info[TENANT_ID_KEY] = validated
            session.info[TENANT_SCOPED_KEY] = True
            session.tenant_id = validated  # type: ignore[attr-defined]
            session.is_tenant_scoped = True  # type: ignore[attr-defined]
            try:
                yield session
            finally:
                event.remove(session.sync_session, "after_begin", _apply_guc)
    finally:
        _current_tenant.reset(token)
