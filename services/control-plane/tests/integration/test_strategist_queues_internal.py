"""Strategist durable queues internal API (integration)."""

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


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'queues') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest_asyncio.fixture
async def q_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "q-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "q-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_action_queue_bulk_patch_flow(
    q_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    bulk = {
        "items": [
            {
                "id": "aq-test-1",
                "priority": "P1",
                "phase": "Phase",
                "description": "From integration test",
                "status": "open",
                "claimed_by": None,
                "updated_at": "2026-04-28T12:00:00.000Z",
                "source": "test",
                "evidence_node_ids": ["node-a"],
            },
        ],
    }
    r = await q_client.post(
        f"/internal/v1/strategist/action-queue-items/bulk?tenant_id={tid}",
        json=bulk,
    )
    assert r.status_code == 201, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == "aq-test-1"

    r2 = await q_client.get(f"/internal/v1/strategist/action-queue-items?tenant_id={tid}")
    assert r2.status_code == 200
    assert len(r2.json()) == 1

    r3 = await q_client.patch(
        f"/internal/v1/strategist/action-queue-items/aq-test-1?tenant_id={tid}",
        json={"status": "claimed", "claimed_by": "you"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "claimed"


@pytest.mark.asyncio
async def test_validation_queue_seed_and_patch(
    q_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    r = await q_client.get(f"/internal/v1/strategist/validation-queue-items?tenant_id={tid}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 10
    vid = rows[0]["id"]

    r2 = await q_client.patch(
        f"/internal/v1/strategist/validation-queue-items/{vid}?tenant_id={tid}",
        json={"state": "resolved"},
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "resolved"
