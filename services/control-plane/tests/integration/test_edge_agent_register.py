"""Epic 11.2 — edge agent registration (integration)."""

from __future__ import annotations

import base64
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


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'edge-agent') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest_asyncio.fixture
async def ea_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ea-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ea-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_register_edge_agent_201_and_get(
    ea_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    did = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    pub = b"\x01" * 32
    b64 = base64.b64encode(pub).decode("ascii")

    r = await ea_client.post(
        "/internal/v1/edge-agents/register",
        json={"tenant_id": str(tid), "device_id": str(did), "public_key_ed25519_b64": b64},
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert "edge_agent_id" in j
    assert "registered_at" in j

    g = await ea_client.get(
        "/internal/v1/edge-agents/by-device",
        params={"tenant_id": str(tid), "device_id": str(did)},
    )
    assert g.status_code == 200, g.text
    gj = g.json()
    assert gj["public_key_ed25519_b64"] == b64
    assert gj["device_id"] == str(did)


@pytest.mark.asyncio
async def test_register_idempotent_same_key(
    ea_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    did = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    pub = b"\x02" * 32
    b64 = base64.b64encode(pub).decode("ascii")
    body = {"tenant_id": str(tid), "device_id": str(did), "public_key_ed25519_b64": b64}

    r1 = await ea_client.post("/internal/v1/edge-agents/register", json=body)
    r2 = await ea_client.post("/internal/v1/edge-agents/register", json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["edge_agent_id"] == r2.json()["edge_agent_id"]


@pytest.mark.asyncio
async def test_register_conflict_different_key(
    ea_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    did = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    await ea_client.post(
        "/internal/v1/edge-agents/register",
        json={
            "tenant_id": str(tid),
            "device_id": str(did),
            "public_key_ed25519_b64": base64.b64encode(b"\x03" * 32).decode("ascii"),
        },
    )
    r = await ea_client.post(
        "/internal/v1/edge-agents/register",
        json={
            "tenant_id": str(tid),
            "device_id": str(did),
            "public_key_ed25519_b64": base64.b64encode(b"\x04" * 32).decode("ascii"),
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_kill_edge_agent_idempotent(
    ea_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    did = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    b64 = base64.b64encode(b"\x05" * 32).decode("ascii")
    reg = await ea_client.post(
        "/internal/v1/edge-agents/register",
        json={"tenant_id": str(tid), "device_id": str(did), "public_key_ed25519_b64": b64},
    )
    assert reg.status_code == 201, reg.text
    eid = reg.json()["edge_agent_id"]

    k1 = await ea_client.post(f"/internal/v1/edge-agents/{eid}/kill")
    assert k1.status_code == 200, k1.text
    j1 = k1.json()
    assert j1["edge_agent_id"] == eid
    assert j1["revoked_at"] is not None

    k2 = await ea_client.post(f"/internal/v1/edge-agents/{eid}/kill")
    assert k2.status_code == 200, k2.text
    assert k2.json()["revoked_at"] == j1["revoked_at"]

    g = await ea_client.get(
        "/internal/v1/edge-agents/by-device",
        params={"tenant_id": str(tid), "device_id": str(did)},
    )
    assert g.status_code == 200, g.text
    assert g.json()["revoked_at"] == j1["revoked_at"]
