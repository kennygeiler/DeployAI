"""Global event search internal API (integration) — Sprint 4 inc 2."""

from __future__ import annotations

import json
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


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'event-search') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_engagement(engine: Engine, tid: uuid.UUID, *, name: str) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:e, :t, :n, 'discovery', 'active')"
            ),
            {"e": str(eid), "t": str(tid), "n": name},
        )
    return eid


def _ins_event(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID | None,
    *,
    event_type: str,
    payload: dict[str, object],
    occurred_at: str,
) -> uuid.UUID:
    evid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(id, tenant_id, engagement_id, event_type, occurred_at, payload) "
                "VALUES (:i, :t, :e, :et, :oa, CAST(:p AS jsonb))"
            ),
            {
                "i": str(evid),
                "t": str(tid),
                "e": str(eid) if eid else None,
                "et": event_type,
                "oa": occurred_at,
                "p": json.dumps(payload),
            },
        )
    return evid


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "s-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "s-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_empty_query_returns_422(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_short_query_returns_422(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=a")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_no_matches_returns_empty(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid, name="A")
    _ins_event(
        postgres_engine,
        tid,
        eid,
        event_type="ingest.meeting_note",
        payload={"content": {"body": "kickoff with vendor"}},
        occurred_at="2026-05-01T10:00:00Z",
    )
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=zzzzz-not-found")
    assert r.status_code == 200
    assert r.json() == {"results": []}


@pytest.mark.asyncio
async def test_multiple_matches_across_engagements(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid_a = _ins_engagement(postgres_engine, tid, name="A")
    eid_b = _ins_engagement(postgres_engine, tid, name="B")
    _ins_event(
        postgres_engine,
        tid,
        eid_a,
        event_type="ingest.email",
        payload={"content": {"body": "We need a vendor for the LiDAR rollout"}},
        occurred_at="2026-05-01T10:00:00Z",
    )
    _ins_event(
        postgres_engine,
        tid,
        eid_b,
        event_type="ingest.meeting_note",
        payload={"content": {"body": "Discussed LiDAR vendor selection criteria"}},
        occurred_at="2026-05-03T10:00:00Z",
    )
    _ins_event(
        postgres_engine,
        tid,
        eid_a,
        event_type="ingest.field_note",
        payload={"content": {"body": "Unrelated cabling issue"}},
        occurred_at="2026-05-02T10:00:00Z",
    )
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=LiDAR")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 2
    # Newest-first.
    occurred = [hit["occurred_at"] for hit in body["results"]]
    assert occurred == sorted(occurred, reverse=True)
    engagement_ids = {hit["engagement_id"] for hit in body["results"]}
    assert engagement_ids == {str(eid_a), str(eid_b)}
    for hit in body["results"]:
        assert "lidar" in hit["snippet"].lower()


@pytest.mark.asyncio
async def test_case_insensitive(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid, name="A")
    _ins_event(
        postgres_engine,
        tid,
        eid,
        event_type="ingest.email",
        payload={"content": {"body": "Procurement TIMELINE pushed"}},
        occurred_at="2026-05-01T10:00:00Z",
    )
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=timeline")
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


@pytest.mark.asyncio
async def test_limit_honored(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid, name="A")
    for i in range(5):
        _ins_event(
            postgres_engine,
            tid,
            eid,
            event_type="ingest.email",
            payload={"content": {"body": f"meeting {i} with stakeholder"}},
            occurred_at=f"2026-05-0{i + 1}T10:00:00Z",
        )
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=stakeholder&limit=2")
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2


@pytest.mark.asyncio
async def test_tenant_isolation(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)
    eid_a = _ins_engagement(postgres_engine, tid_a, name="A")
    eid_b = _ins_engagement(postgres_engine, tid_b, name="B")
    _ins_event(
        postgres_engine,
        tid_a,
        eid_a,
        event_type="ingest.email",
        payload={"content": {"body": "secret-token-A in tenant A"}},
        occurred_at="2026-05-01T10:00:00Z",
    )
    _ins_event(
        postgres_engine,
        tid_b,
        eid_b,
        event_type="ingest.email",
        payload={"content": {"body": "secret-token-A also in tenant B"}},
        occurred_at="2026-05-01T10:00:00Z",
    )
    r = await s_client.get(f"/internal/v1/tenants/{tid_a}/events/search?q=secret-token-A")
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["engagement_id"] == str(eid_a)


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=something")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_invalid_limit_rejected(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await s_client.get(f"/internal/v1/tenants/{tid}/events/search?q=hello&limit=999")
    assert r.status_code == 422
