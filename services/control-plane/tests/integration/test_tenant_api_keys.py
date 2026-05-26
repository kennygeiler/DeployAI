"""v2 Phase 4 — tenant_api_keys internal-API mint/list/revoke (integration)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def t_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ap-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ap-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant_with_engagement(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'api-keys-test')"),
            {"t": str(tid)},
        )
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase) VALUES (:e, :t, 'mcp-eng', 'P2_active')"
            ),
            {"e": str(eid), "t": str(tid)},
        )
    return tid, eid


@pytest.mark.asyncio
async def test_mint_returns_raw_key_once(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    r = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "bob-desktop", "engagement_id": str(eid)},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["raw_key"].startswith("mcp_live_")
    assert body["api_key"]["name"] == "bob-desktop"
    assert body["api_key"]["engagement_id"] == str(eid)
    assert body["api_key"]["scopes"] == ["read"]
    assert body["api_key"]["revoked_at"] is None

    # subsequent list never echoes the raw key
    listed = await t_client.get(f"/internal/v1/tenant/api-keys?tenant_id={tid}")
    assert listed.status_code == 200
    keys = listed.json()["api_keys"]
    assert len(keys) == 1
    assert "raw_key" not in keys[0]
    assert "hashed_secret" not in keys[0]


@pytest.mark.asyncio
async def test_mint_persists_hashed_secret_not_raw(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    r = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "bob-desktop", "engagement_id": str(eid)},
    )
    assert r.status_code == 201
    raw = r.json()["raw_key"]
    with postgres_engine.begin() as conn:
        row = conn.execute(
            text("SELECT hashed_secret FROM tenant_api_keys WHERE tenant_id = :t AND name = 'bob-desktop'"),
            {"t": str(tid)},
        ).first()
    assert row is not None
    hashed = row[0]
    assert hashed != raw
    assert raw not in hashed
    # scrypt envelope structure
    assert hashed.startswith("scrypt$")


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    minted = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "k1", "engagement_id": str(eid)},
    )
    api_key_id = minted.json()["api_key"]["id"]
    deleted = await t_client.delete(f"/internal/v1/tenant/api-keys/{api_key_id}?tenant_id={tid}")
    assert deleted.status_code == 204
    listed = (await t_client.get(f"/internal/v1/tenant/api-keys?tenant_id={tid}")).json()
    assert listed["api_keys"][0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_mint_rejects_duplicate_name(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    r1 = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "shared", "engagement_id": str(eid)},
    )
    assert r1.status_code == 201
    r2 = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "shared", "engagement_id": str(eid)},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_mint_rejects_unknown_tenant(t_client: AsyncClient, postgres_engine: Engine) -> None:
    _tid, eid = _seed_tenant_with_engagement(postgres_engine)
    r = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={uuid.uuid4()}",
        json={"name": "x", "engagement_id": str(eid)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mint_rejects_engagement_outside_tenant(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, _eid = _seed_tenant_with_engagement(postgres_engine)
    other_tid, other_eid = _seed_tenant_with_engagement(postgres_engine)
    assert tid != other_tid
    r = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "leaky", "engagement_id": str(other_eid)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mint_rejects_unknown_scope(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    r = await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "k", "engagement_id": str(eid), "scopes": ["read", "write"]},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_revoke_404_on_unknown_id(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, _eid = _seed_tenant_with_engagement(postgres_engine)
    r = await t_client.delete(f"/internal/v1/tenant/api-keys/{uuid.uuid4()}?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_minting_emits_ledger_event(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = _seed_tenant_with_engagement(postgres_engine)
    await t_client.post(
        f"/internal/v1/tenant/api-keys?tenant_id={tid}",
        json={"name": "bob-laptop", "engagement_id": str(eid)},
    )
    with postgres_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT summary FROM ledger_events "
                "WHERE tenant_id = :t AND source_kind = 'tenant_api_key_minted' "
                "ORDER BY occurred_at DESC"
            ),
            {"t": str(tid)},
        ).all()
    assert any("bob-laptop" in r[0] for r in rows)


@pytest.mark.asyncio
async def test_unauthorized_without_internal_key(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ap-test-key")
    clear_engine_cache()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/internal/v1/tenant/api-keys?tenant_id={uuid.uuid4()}")
            assert r.status_code == 401
    finally:
        clear_engine_cache()
