"""Engagement timeline internal API (integration) — Sprint 4, increment 1."""

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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'timeline') ON CONFLICT (id) DO NOTHING"),
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
) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO canonical_memory_events
                  (tenant_id, engagement_id, event_type, occurred_at, source_ref, payload)
                VALUES
                  (:t, :e, :et, :occ, :src, CAST(:payload AS jsonb))
                """
            ),
            {
                "t": str(tenant_id),
                "e": engagement_id,
                "et": event_type,
                "occ": occurred_at,
                "src": source_ref,
                "payload": json.dumps(payload),
            },
        )


@pytest_asyncio.fixture
async def tl_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "tl-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "tl-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


async def _new_engagement(client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Timeline test"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


@pytest.mark.asyncio
async def test_timeline_empty_returns_empty_list(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}")
    assert r.status_code == 200, r.text
    assert r.json() == {"events": []}


@pytest.mark.asyncio
async def test_timeline_returns_events_in_chronological_order(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    now = datetime.now(UTC)
    # Insert out of chronological order to prove the route sorts.
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.meeting_note",
        now - timedelta(days=5),
        {"text": "Mid meeting"},
        source_ref="https://example/notes/mid",
    )
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        now - timedelta(days=20),
        {"text": "Old email"},
    )
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.field_note",
        now - timedelta(days=1),
        {"text": "Most recent note"},
    )

    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    events = body["events"]
    assert [e["event_type"] for e in events] == [
        "ingest.email",
        "ingest.meeting_note",
        "ingest.field_note",
    ]
    assert events[0]["summary"] == "Old email"
    assert events[1]["source_ref"] == "https://example/notes/mid"
    assert events[2]["summary"] == "Most recent note"


@pytest.mark.asyncio
async def test_timeline_days_filter_cuts_old_events(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    now = datetime.now(UTC)
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        now - timedelta(days=200),
        {"text": "Way old"},
    )
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        now - timedelta(days=10),
        {"text": "Recent"},
    )

    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}&days=30")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["summary"] == "Recent"


@pytest.mark.asyncio
async def test_timeline_summary_truncated_to_240_chars(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    long_text = "A" * 1000
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": long_text},
    )
    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert len(events[0]["summary"]) == 240


@pytest.mark.asyncio
async def test_timeline_falls_back_to_payload_dump_when_no_text(
    tl_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"meta": {"sender": "ops@example"}},
    )
    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    # JSON dump fallback contains the structural marker.
    assert "sender" in events[0]["summary"]


@pytest.mark.asyncio
async def test_timeline_unknown_engagement_404(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await tl_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/timeline?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_timeline_days_param_rejected_when_above_max(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}&days=999")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_timeline_scoped_to_engagement_and_tenant(tl_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(tl_client, postgres_engine)
    # An event on a different engagement of the same tenant must not appear.
    r_other = await tl_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Other"})
    other_eid = r_other.json()["id"]
    _ins_event(
        postgres_engine,
        tid,
        other_eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": "Belongs to other engagement"},
    )
    _ins_event(
        postgres_engine,
        tid,
        eid,
        "ingest.email",
        datetime.now(UTC) - timedelta(days=1),
        {"text": "Belongs to ours"},
    )
    r = await tl_client.get(f"/internal/v1/engagements/{eid}/timeline?tenant_id={tid}")
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["summary"] == "Belongs to ours"
