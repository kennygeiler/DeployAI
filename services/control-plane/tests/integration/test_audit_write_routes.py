"""Phase C inc 11.5 — POST /internal/v1/audit-events (integration)."""

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
async def a_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "audit-write-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "audit-write-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'audit-write-test')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_post_persists_and_tenant_isolation(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    actor = uuid.uuid4()

    body = {
        "actor_id": str(actor),
        "category": "tenant.webhook.created",
        "summary": "created webhook foo",
        "detail": {"id": str(uuid.uuid4()), "name": "foo"},
    }
    created = await a_client.post(f"/internal/v1/audit-events?tenant_id={tid_a}", json=body)
    assert created.status_code == 201, created.text
    created_row = created.json()
    assert created_row["tenant_id"] == str(tid_a)
    assert created_row["actor_id"] == str(actor)
    assert created_row["category"] == "tenant.webhook.created"
    assert created_row["detail"]["name"] == "foo"

    a_list = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid_a}")
    assert a_list.status_code == 200
    assert len(a_list.json()) == 1

    b_list = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid_b}")
    assert b_list.status_code == 200
    assert b_list.json() == []


@pytest.mark.asyncio
async def test_post_bad_category_returns_422(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    body = {
        "actor_id": str(uuid.uuid4()),
        "category": "Bad Category!!",
        "summary": "nope",
        "detail": {},
    }
    r = await a_client.post(f"/internal/v1/audit-events?tenant_id={tid}", json=body)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_post_unknown_tenant_returns_404(a_client: AsyncClient) -> None:
    body = {
        "actor_id": str(uuid.uuid4()),
        "category": "tenant.webhook.created",
        "summary": "x",
        "detail": {},
    }
    r = await a_client.post(f"/internal/v1/audit-events?tenant_id={uuid.uuid4()}", json=body)
    assert r.status_code == 404
