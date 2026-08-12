"""Integration: pilot-refresh A3a — RLS expansion (migrations 0051 + 0053).

Three layers of proof:

1. Catalog invariant — every ``public`` table that carries a ``tenant_id``
   column has ENABLE + FORCE ROW LEVEL SECURITY and a ``tenant_rls_<table>``
   policy. Discovery-based (like the autouse TRUNCATE fixture) so a future
   migration that adds a tenant table without a policy fails this test.
2. Session-level — under the RLS-subject ``deployai_app`` role,
   ``TenantScopedSession`` for tenant A sees only A's ``ledger_events`` /
   ``matrix_nodes``; a raw unscoped connection sees zero rows.
3. Route-level — with the app engine pointed at the ``deployai_app`` role,
   the converted ledger route serves tenant A's rows to a tenant-A service
   token, rejects a tenant-B token with 403, and hides A's engagement from a
   B-scoped legacy-key request.

Also covers the 0051 trigger: ledger edge rows inserted without a
``tenant_id`` inherit it from the parent event.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from deployai_tenancy import TenantScopedSession
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane.db import clear_engine_cache
from control_plane.domain.app_identity.service_tokens import (
    generate_raw_token,
    hash_service_token,
)
from control_plane.main import app

pytestmark = pytest.mark.integration

_APP_USER = "deployai_app"
_APP_PASSWORD = os.environ.get("FUZZ_APP_PASSWORD") or "deployai-fuzz-test"

# Tables that legitimately carry no tenant policy despite living in public.
_RLS_EXEMPT: frozenset[str] = frozenset(
    {
        "app_tenants",  # the tenant registry itself
        "internal_service_tokens",  # auth infra: looked up before any scope exists
        "webhook_deliveries",  # no tenant_id column yet — documented follow-up
        "eval_runs",  # platform-level ops data (G8): no tenant_id by design — eval
        # runs measure product quality against synthetic fixtures, never
        # tenant data; gated by require_internal at the route layer.
    }
)


def _app_role_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(
        drivername="postgresql+psycopg",
        username=_APP_USER,
        password=_APP_PASSWORD,
    ).render_as_string(hide_password=False)


@pytest.fixture()
def _app_role_login(postgres_engine: Engine) -> Generator[None]:
    """Enable LOGIN on ``deployai_app`` (migration 0002 creates it NOLOGIN)."""
    with postgres_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE {_APP_USER} WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))
    yield


# ---------------------------------------------------------------------------
# 1. Catalog invariant
# ---------------------------------------------------------------------------


def test_every_tenant_table_has_forced_rls_policy(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        tenant_tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
                )
            )
        }
        assert len(tenant_tables) >= 45, "expected the full expanded table set"

        rls_state = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r'"
                )
            )
        }
        policies = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_policies WHERE schemaname = 'public' AND policyname LIKE 'tenant_rls_%'")
            )
        }

    covered = tenant_tables - _RLS_EXEMPT
    missing_rls = sorted(t for t in covered if rls_state.get(t) != (True, True))
    missing_policy = sorted(t for t in covered if t not in policies)
    assert not missing_rls, f"tables with tenant_id but without ENABLE+FORCE RLS: {missing_rls}"
    assert not missing_policy, f"tables with tenant_id but without tenant_rls policy: {missing_policy}"

    # The exempt list must stay honest: an exempted table really has no
    # policy (if someone adds one, drop the exemption here).
    stale_exemptions = sorted(t for t in _RLS_EXEMPT if t in policies)
    assert not stale_exemptions, f"exempted tables now carry a policy: {stale_exemptions}"


# ---------------------------------------------------------------------------
# Seed helpers (superuser — RLS bypass by design)
# ---------------------------------------------------------------------------


def _seed_tenant(engine: Engine, name: str) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": name})
    return tid


def _seed_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'rls-test', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id)},
        )
    return eid


def _seed_ledger_event(engine: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID | None) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary) "
                "VALUES (:i, :t, :e, :o, 'user', 'audit_other', 'rls seed')"
            ),
            {
                "i": str(eid),
                "t": str(tenant_id),
                "e": str(engagement_id) if engagement_id else None,
                "o": datetime.now(UTC),
            },
        )
    return eid


def _seed_matrix_node(engine: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_nodes (id, tenant_id, engagement_id, node_type, title) "
                "VALUES (:i, :t, :e, 'system', 'rls node')"
            ),
            {"i": str(nid), "t": str(tenant_id), "e": str(engagement_id)},
        )
    return nid


def _mint_token(engine: Engine, tenant_id: uuid.UUID, name: str) -> str:
    raw = generate_raw_token()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO internal_service_tokens (tenant_id, name, hashed_key) VALUES (:t, :n, :h)"),
            {"t": str(tenant_id), "n": name, "h": hash_service_token(raw)},
        )
    return raw


# ---------------------------------------------------------------------------
# 2. Session-level RLS proof under the app role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads_under_app_role(
    postgres_engine: Engine,
    _app_role_login: None,
) -> None:
    tenant_a = _seed_tenant(postgres_engine, "rls-a")
    tenant_b = _seed_tenant(postgres_engine, "rls-b")
    eng_a = _seed_engagement(postgres_engine, tenant_a)
    eng_b = _seed_engagement(postgres_engine, tenant_b)
    _seed_ledger_event(postgres_engine, tenant_a, eng_a)
    _seed_ledger_event(postgres_engine, tenant_b, eng_b)
    _seed_matrix_node(postgres_engine, tenant_a, eng_a)
    _seed_matrix_node(postgres_engine, tenant_b, eng_b)

    app_engine = create_async_engine(_app_role_url(postgres_engine))
    try:
        for table in ("ledger_events", "matrix_nodes"):
            # Scoped to A: sees exactly A's row, never B's.
            async with TenantScopedSession(tenant_a, app_engine) as session:
                rows = (await session.execute(text(f"SELECT tenant_id FROM {table}"))).all()
            assert {str(r[0]) for r in rows} == {str(tenant_a)}, table

            # No scope at all: policy evaluates NULL -> zero rows.
            async with app_engine.connect() as conn:
                unscoped = (await conn.execute(text(f"SELECT tenant_id FROM {table}"))).all()
            assert unscoped == [], table
    finally:
        await app_engine.dispose()


def test_ledger_edge_trigger_backfills_tenant(postgres_engine: Engine) -> None:
    tenant = _seed_tenant(postgres_engine, "rls-edges")
    ev1 = _seed_ledger_event(postgres_engine, tenant, None)
    ev2 = _seed_ledger_event(postgres_engine, tenant, None)
    with postgres_engine.begin() as conn:
        # Legacy writer shape: no tenant_id column named at all.
        conn.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:a, :b)"),
            {"a": str(ev1), "b": str(ev2)},
        )
        conn.execute(
            text(
                "INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) "
                "VALUES (:a, 'node', gen_random_uuid())"
            ),
            {"a": str(ev1)},
        )
    with postgres_engine.connect() as conn:
        cause_tid = conn.execute(
            text("SELECT tenant_id FROM ledger_event_causes WHERE event_id = :a"), {"a": str(ev1)}
        ).scalar_one()
        affect_tid = conn.execute(
            text("SELECT tenant_id FROM ledger_event_affects WHERE event_id = :a"), {"a": str(ev1)}
        ).scalar_one()
    assert str(cause_tid) == str(tenant)
    assert str(affect_tid) == str(tenant)


# ---------------------------------------------------------------------------
# 3. Route-level: converted routes through an RLS-subject app engine
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_role_client(
    postgres_engine: Engine,
    _app_role_login: None,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """The FastAPI app wired to Postgres as ``deployai_app`` (RLS-subject)."""
    monkeypatch.setenv("DATABASE_URL", _app_role_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "rls-test-global-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_converted_routes_enforce_tenant_scope(
    postgres_engine: Engine,
    app_role_client: AsyncClient,
) -> None:
    tenant_a = _seed_tenant(postgres_engine, "route-a")
    tenant_b = _seed_tenant(postgres_engine, "route-b")
    eng_a = _seed_engagement(postgres_engine, tenant_a)
    _seed_ledger_event(postgres_engine, tenant_a, eng_a)
    token_a = _mint_token(postgres_engine, tenant_a, "route-a-token")
    token_b = _mint_token(postgres_engine, tenant_b, "route-b-token")

    # Tenant A's token reads A's ledger through the RLS-subject engine.
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": token_a},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["events"]) == 1

    # Tenant B's token may not name tenant A: 403 before any query runs.
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": token_b},
    )
    assert resp.status_code == 403

    # Tenant B's token scoped to B: A's engagement is invisible (RLS + filter).
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_b)},
        headers={"X-DeployAI-Internal-Key": token_b},
    )
    assert resp.status_code == 404

    # Matrix nodes route (same module) under the A token.
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/matrix/nodes",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": token_a},
    )
    assert resp.status_code == 200, resp.text

    # Legacy global key still works (deprecation path), scoped by its param.
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": "rls-test-global-key"},
    )
    assert resp.status_code == 200
    # ... but a legacy-key request scoped to B cannot see A's engagement.
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_b)},
        headers={"X-DeployAI-Internal-Key": "rls-test-global-key"},
    )
    assert resp.status_code == 404

    # Revoked tokens stop authenticating.
    with postgres_engine.begin() as conn:
        conn.execute(
            text("UPDATE internal_service_tokens SET revoked_at = now() WHERE tenant_id = :t"),
            {"t": str(tenant_a)},
        )
    resp = await app_role_client.get(
        f"/internal/v1/engagements/{eng_a}/ledger",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": token_a},
    )
    assert resp.status_code == 401
