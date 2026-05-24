"""Engagement events-by-ids internal API — integration tests."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'events') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_event(
    engine: Engine,
    tenant_id: uuid.UUID,
    engagement_id: str,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, object],
    source_ref: str | None = None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO canonical_memory_events
                  (id, tenant_id, engagement_id, event_type, occurred_at, source_ref, payload)
                VALUES
                  (:id, :t, :e, :et, :occ, :src, CAST(:payload AS jsonb))
                """
            ),
            {
                "id": str(event_id),
                "t": str(tenant_id),
                "e": engagement_id,
                "et": event_type,
                "occ": occurred_at,
                "src": source_ref,
                "payload": json.dumps(payload),
            },
        )
    return event_id


@pytest_asyncio.fixture
async def ev_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ev-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ev-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


async def _new_engagement(client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Events test"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


@pytest.mark.asyncio
async def test_events_returns_requested_rows(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    now = datetime.now(UTC)
    a = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        now - timedelta(days=2),
        {"text": "Email body"},
        source_ref="https://example/em/1",
    )
    b = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.meeting_note",
        now - timedelta(days=1),
        {"content": {"text": "Meeting note body"}},
    )
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={a},{b}")
    assert r.status_code == 200, r.text
    body = r.json()
    events = body["events"]
    assert len(events) == 2
    by_id = {e["id"]: e for e in events}
    assert by_id[str(a)]["summary"] == "Email body"
    assert by_id[str(a)]["source_ref"] == "https://example/em/1"
    assert by_id[str(a)]["event_type"] == "ingest.email"
    assert by_id[str(b)]["summary"] == "Meeting note body"


@pytest.mark.asyncio
async def test_events_empty_ids_returns_empty_list(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids=")
    assert r.status_code == 200, r.text
    assert r.json() == {"events": []}


@pytest.mark.asyncio
async def test_events_unknown_id_silently_dropped(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    a = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": "Known one"},
    )
    missing = uuid.uuid4()
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={a},{missing}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["id"] == str(a)


@pytest.mark.asyncio
async def test_events_scoped_to_engagement_and_tenant(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    r_other = await ev_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Other"})
    other_eid = r_other.json()["id"]
    a_ours = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": "Ours"},
    )
    a_theirs = _ins_event(
        postgres_engine,
        tid,
        other_eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": "Not ours"},
    )
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={a_ours},{a_theirs}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["id"] == str(a_ours)


@pytest.mark.asyncio
async def test_events_too_many_ids_returns_422(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    too_many = ",".join(str(uuid.uuid4()) for _ in range(51))
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={too_many}")
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_events_invalid_uuid_returns_422(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids=not-a-uuid")
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_events_unknown_engagement_404(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await ev_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/events?tenant_id={tid}&ids={uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_events_summary_truncated_to_240_chars(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    long_text = "B" * 1000
    a = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": long_text},
    )
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={a}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert len(events[0]["summary"]) == 240


@pytest.mark.asyncio
async def test_events_payload_fallback_when_no_text(ev_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ev_client, postgres_engine)
    a = _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.field_note",
        datetime.now(UTC) - timedelta(days=1),
        {"meta": {"sender": "ops@example"}},
    )
    r = await ev_client.get(f"/internal/v1/engagements/{eid}/events?tenant_id={tid}&ids={a}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert "sender" in events[0]["summary"]
