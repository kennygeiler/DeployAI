"""Epic 4 Story 4-7: internal adjudication queue API."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app


def _async_database_url_from_engine(postgres_engine: Engine) -> str:
    u = postgres_engine.url.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def adjud_internal_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "adjud-int-test")
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers["X-DeployAI-Internal-Key"] = "adjud-int-test"
            yield client
    finally:
        clear_engine_cache()


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'adjud test')"), {"t": str(tid)})


@pytest.mark.integration
async def test_adjudication_create_list_patch(
    adjud_internal_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await adjud_internal_client.post(
        "/internal/v1/adjudication-queue-items",
        json={"tenant_id": str(tid), "query_id": "q-replay-1", "meta": {"rule_pass": True, "judge_pass": False}},
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["query_id"] == "q-replay-1"
    iid = j["id"]

    r2 = await adjud_internal_client.get("/internal/v1/adjudication-queue-items?limit=10")
    assert r2.status_code == 200
    rows = r2.json()
    assert any(x["id"] == iid for x in rows)

    r3 = await adjud_internal_client.patch(
        f"/internal/v1/adjudication-queue-items/{iid}", json={"status": "resolved"}
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "resolved"
