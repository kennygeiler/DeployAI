"""Story 1.9 — three-layer tenant isolation integration tests.

Uses the shared ``postgres_engine`` container (Story 1.8 conftest) for setup,
then opens a *second* async engine connected as ``deployai_app`` — a non-
superuser role the migration creates — because Postgres superusers carry an
implicit ``BYPASSRLS`` attribute that would short-circuit the whole test.

Covered cases (AC6):
1. Happy-path: scoped session sees its own rows.
2. Cross-tenant READ is filtered silently (zero rows, no error).
3. Cross-tenant WRITE raises (``WITH CHECK`` → InsufficientPrivilege).
4. Raw AsyncSession with no ``SET LOCAL`` sees zero rows (fail-closed).
5. Envelope-encryption round-trip through pgcrypto.
6. ``deployai_app`` role is blocked by RLS without a scope (proves FORCE).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Generator
from typing import cast

import pytest
import pytest_asyncio
from deployai_tenancy import (
    InMemoryDEKProvider,
    TenantScopedSession,
    decrypt_field,
    encrypt_field,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

pytestmark = pytest.mark.integration


TENANT_A = uuid.UUID("00000000-0000-7000-8000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-7000-8000-00000000000b")
_APP_PASSWORD = "deployai-app-test"


@pytest.fixture(scope="module", autouse=True)
def _configure_app_role(postgres_engine: Engine) -> Generator[None]:
    """Flip ``deployai_app`` to LOGIN with a test password so the async engine can connect.

    The migration creates the role as ``NOLOGIN`` by design so that operators
    must explicitly enable login at deploy time (Story 2.4 ops runbook). In
    tests we simulate that step here.
    """
    with postgres_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE deployai_app WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))
    yield


@pytest.fixture
def sync_url(postgres_engine: Engine) -> str:
    """Read the synchronous URL off the container-bound engine."""
    raw = postgres_engine.url.render_as_string(hide_password=False)
    return cast(str, raw)


def _async_url_for(sync_url: str, *, user: str, password: str) -> str:
    """Derive an async psycopg URL from the sync psycopg URL, swapping creds.

    We use ``psycopg`` (v3) for both sync and async because it's already in
    the dev dep stack and handles async natively — no extra driver needed.
    """
    remainder = sync_url.split("@", 1)[1]
    return f"postgresql+psycopg://{user}:{password}@{remainder}"


@pytest_asyncio.fixture
async def app_engine(sync_url: str) -> AsyncIterator[AsyncEngine]:
    """Async engine connected as ``deployai_app`` — subject to RLS."""
    engine = create_async_engine(
        _async_url_for(sync_url, user="deployai_app", password=_APP_PASSWORD),
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _seed_rows(postgres_engine: Engine) -> None:
    """Insert one canonical_memory_event row per tenant as superuser (bypasses RLS).

    The module's ``_clean_tenant_rows`` teardown (shared conftest) TRUNCATEs
    every canonical-memory table between tests so seed counts stay at 1 — the
    count assertions below depend on this.
    """
    with postgres_engine.begin() as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                text(
                    "INSERT INTO canonical_memory_events "
                    "(tenant_id, event_type, occurred_at) "
                    "VALUES (:tid, 'seed', now())"
                ),
                {"tid": str(tenant)},
            )


async def test_scoped_session_sees_own_rows(app_engine: AsyncEngine, postgres_engine: Engine) -> None:
    """AC6.1 — happy path: scoped read returns rows across every canonical table."""
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO identity_nodes "
                "(tenant_id, canonical_name, primary_email_hash) "
                "VALUES (:tid, 'Alice', 'hash-a'), (:tid, 'Alice-dup', 'hash-b')"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO identity_attribute_history "
                "(tenant_id, identity_id, attribute_name, attribute_value, valid_from) "
                "SELECT :tid, id, 'role', 'strategist', now() "
                "FROM identity_nodes WHERE tenant_id = :tid AND primary_email_hash = 'hash-a'"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO identity_supersessions "
                "(tenant_id, superseded_identity_id, canonical_identity_id, reason) "
                "SELECT :tid, "
                "  (SELECT id FROM identity_nodes WHERE primary_email_hash='hash-b' AND tenant_id=:tid), "
                "  (SELECT id FROM identity_nodes WHERE primary_email_hash='hash-a' AND tenant_id=:tid), "
                "  'dedup'"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO solidified_learnings "
                "(tenant_id, belief, evidence_event_ids) "
                "VALUES (:tid, 'gut', ARRAY[]::uuid[])"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO learning_lifecycle_states "
                "(tenant_id, learning_id, state, transitioned_at) "
                "SELECT :tid, id, 'candidate', now() "
                "FROM solidified_learnings WHERE tenant_id = :tid"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO tombstones "
                "(tenant_id, original_node_id, retention_reason, authority_actor_id, destroyed_at, signature) "
                "VALUES (:tid, gen_random_uuid(), 'test', gen_random_uuid(), now(), E'\\\\x00')"
            ),
            {"tid": str(TENANT_A)},
        )
        conn.execute(
            text(
                "INSERT INTO schema_proposals "
                "(tenant_id, proposer_actor_id, proposed_ddl) "
                "VALUES (:tid, gen_random_uuid(), 'ALTER TABLE ...')"
            ),
            {"tid": str(TENANT_A)},
        )

    async with TenantScopedSession(TENANT_A, app_engine) as session:
        for table in (
            "canonical_memory_events",
            "identity_nodes",
            "identity_attribute_history",
            "identity_supersessions",
            "solidified_learnings",
            "learning_lifecycle_states",
            "tombstones",
            "schema_proposals",
        ):
            result = await session.execute(text(f"SELECT count(*) FROM {table}"))
            assert result.scalar_one() > 0, f"{table} returned 0 rows under scope"


async def test_cross_tenant_read_filtered(app_engine: AsyncEngine) -> None:
    async with TenantScopedSession(TENANT_B, app_engine) as session:
        result = await session.execute(
            text("SELECT tenant_id FROM canonical_memory_events WHERE tenant_id = :tid"),
            {"tid": str(TENANT_A)},
        )
        assert result.first() is None


async def test_cross_tenant_write_blocked(app_engine: AsyncEngine) -> None:
    async with TenantScopedSession(TENANT_B, app_engine) as session:
        with pytest.raises(DBAPIError) as excinfo:
            await session.execute(
                text(
                    "INSERT INTO canonical_memory_events "
                    "(tenant_id, event_type, occurred_at) "
                    "VALUES (:tid, 'smuggled', now())"
                ),
                {"tid": str(TENANT_A)},
            )
        # SQLSTATE 42501 = insufficient_privilege. Matching the code rather
        # than the English error text survives locale changes and driver
        # version bumps (review L4).
        sqlstate = getattr(excinfo.value.orig, "sqlstate", None)
        assert sqlstate == "42501", f"expected SQLSTATE 42501; got {sqlstate!r}"


async def test_raw_session_sees_nothing(app_engine: AsyncEngine) -> None:
    """Without ``SET LOCAL``, current_setting() returns NULL → policy fails closed."""
    async with app_engine.begin() as conn:
        result = await conn.execute(text("SELECT count(*) FROM canonical_memory_events"))
        assert result.scalar_one() == 0


async def test_envelope_roundtrip(app_engine: AsyncEngine) -> None:
    provider = InMemoryDEKProvider(environment="test")
    async with TenantScopedSession(TENANT_A, app_engine) as session:
        dek = await provider.get_dek(TENANT_A)
        plaintext = b"sensitive evidence span blob"
        ciphertext = await encrypt_field(session, plaintext=plaintext, dek=dek)
        assert ciphertext != plaintext
        assert len(ciphertext) > len(plaintext)
        recovered = await decrypt_field(session, ciphertext=ciphertext, dek=dek)
        assert recovered == plaintext


async def test_force_rls_on_app_role_without_scope(app_engine: AsyncEngine) -> None:
    """``deployai_app`` has no BYPASSRLS — no scope ⇒ zero rows across all tables."""
    async with app_engine.connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM solidified_learnings"))
        assert result.scalar_one() == 0
        result2 = await conn.execute(text("SELECT count(*) FROM identity_nodes"))
        assert result2.scalar_one() == 0


async def test_set_local_scope_is_transaction_local(app_engine: AsyncEngine) -> None:
    """After the scoped session exits, subsequent raw queries lose the GUC."""
    async with TenantScopedSession(TENANT_A, app_engine) as session:
        result = await session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        assert result.scalar_one() == str(TENANT_A)

    # Fresh connection — no SET LOCAL — GUC empty.
    async with app_engine.connect() as conn:
        result = await conn.execute(text("SELECT current_setting('app.current_tenant', true)"))
        assert result.scalar_one() in (None, "")


async def test_concurrent_scopes_isolated() -> None:
    """Two asyncio tasks in distinct scopes don't leak each other's tenant id."""
    # This is a contextvars-behavior check; no DB needed. Uses sqlite to avoid
    # spinning extra Postgres connections when the concern is pure Python.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
    )

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _funcs(dbapi_conn: object, _: object) -> None:
        def _set_config(_n: str, v: str, _l: int) -> str:
            return v

        dbapi_conn.create_function("set_config", 3, _set_config)  # type: ignore[attr-defined]

    observed: dict[uuid.UUID, uuid.UUID] = {}

    async def worker(tid: uuid.UUID) -> None:
        async with TenantScopedSession(tid, engine) as session:
            await asyncio.sleep(0.01)  # yield to the other worker mid-scope
            observed[tid] = session.info["tenant_id"]

    try:
        await asyncio.gather(worker(TENANT_A), worker(TENANT_B))
    finally:
        await engine.dispose()

    assert observed[TENANT_A] == TENANT_A
    assert observed[TENANT_B] == TENANT_B


def _silence_unused_import() -> AsyncSession | None:  # pragma: no cover
    """Keep ``AsyncSession`` import in the module header so mypy sees it typed."""
    return None
