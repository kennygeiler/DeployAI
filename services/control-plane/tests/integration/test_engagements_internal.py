"""Engagements internal API (integration) — Phase 1."""

from __future__ import annotations

import uuid

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


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'engagements') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "e-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "e-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_create_list_get_engagement(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "NYC DOT LiDAR", "customer_account": "NYC DOT"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "NYC DOT LiDAR"
    assert created["customer_account"] == "NYC DOT"
    assert created["current_phase"] == "P1_pre_engagement"
    assert created["status"] == "active"
    eid = created["id"]

    r2 = await e_client.get(f"/internal/v1/engagements?tenant_id={tid}")
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["id"] == eid

    r3 = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid}")
    assert r3.status_code == 200
    assert r3.json()["id"] == eid


@pytest.mark.asyncio
async def test_engagement_unknown_tenant_404(e_client: AsyncClient) -> None:
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={uuid.uuid4()}",
        json={"name": "ghost"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_engagement_invalid_phase_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "bad phase", "current_phase": "P9_nope"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_engagement_tenant_isolation(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """An engagement created under tenant A is not visible to tenant B."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid_a}",
        json={"name": "tenant A only"},
    )
    assert r.status_code == 201
    eid = r.json()["id"]

    r_list = await e_client.get(f"/internal/v1/engagements?tenant_id={tid_b}")
    assert r_list.status_code == 200
    assert r_list.json() == []

    r_get = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid_b}")
    assert r_get.status_code == 404
