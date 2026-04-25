"""Epic 4 Story 4-7: internal adjudication queue API."""

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
async def test_adjudication_create_list_patch(adjud_internal_client: AsyncClient, postgres_engine: Engine) -> None:
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

    r3 = await adjud_internal_client.patch(f"/internal/v1/adjudication-queue-items/{iid}", json={"status": "resolved"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "resolved"


_CITATION_META_SAMPLE = {
    "rule_pass": True,
    "judge_pass": False,
    "citation_envelope": {
        "schema_version": "0.1.0",
        "node_id": "550e8400-e29b-41d4-a716-446655440000",
        "graph_epoch": 0,
        "evidence_span": {"start": 0, "end": 5, "source_ref": "urn:transcript#session-1"},
        "retrieval_phase": "oracle",
        "confidence_score": 0.88,
        "signed_timestamp": "2026-04-23T12:00:00.000Z",
    },
    "evidence_body": "Hello",
    "citation_label": "Transcript",
}


@pytest.mark.integration
async def test_adjudication_create_persists_citation_meta(
    adjud_internal_client: AsyncClient, postgres_engine: Engine
) -> None:
    """``meta`` may hold ``citation_envelope`` + web keys (docs/platform/adjudication-queue-meta.md)."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await adjud_internal_client.post(
        "/internal/v1/adjudication-queue-items",
        json={"tenant_id": str(tid), "query_id": "q-cite-1", "meta": _CITATION_META_SAMPLE},
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert r.json()["meta"]["citation_envelope"]["node_id"] == "550e8400-e29b-41d4-a716-446655440000"

    r2 = await adjud_internal_client.get("/internal/v1/adjudication-queue-items?limit=10")
    assert r2.status_code == 200
    row = next(x for x in r2.json() if x["id"] == iid)
    assert row["meta"]["evidence_body"] == "Hello"
    assert row["meta"]["citation_label"] == "Transcript"


@pytest.mark.integration
async def test_adjudication_create_rejects_unknown_tenant(adjud_internal_client: AsyncClient) -> None:
    r = await adjud_internal_client.post(
        "/internal/v1/adjudication-queue-items",
        json={"tenant_id": "00000000-0000-0000-0000-00000000dead", "query_id": "orphan"},
    )
    assert r.status_code == 404, r.text
    assert "tenant" in r.text.lower()
