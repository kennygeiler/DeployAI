"""Meeting webhook receiver internal route (integration) — Phase C inc 9.2."""

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
async def m_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "meetings-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "meetings-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'meetings-test')"),
            {"t": str(tid)},
        )
    return tid


def _row_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    with engine.begin() as conn:
        r = conn.execute(
            text("SELECT count(*) FROM meeting_webhook_events WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        )
        return int(r.scalar_one())


@pytest.mark.asyncio
async def test_post_webhook_inserts_zoom_event(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    payload = {
        "event": "meeting.ended",
        "payload": {
            "object": {
                "uuid": "zoom-uuid-1",
                "id": 7,
                "topic": "Phase kick-off",
                "start_time": "2026-05-24T16:00:00Z",
                "duration": 30,
                "participants": [{"email": "a@x.com"}, {"email": "b@x.com"}],
                "recording_url": "https://zoom.example/rec/1",
            }
        },
    }
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid}",
        json={"source": "zoom", "payload": payload},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tenant_id"] == str(tid)
    assert body["engagement_id"] is None
    assert body["source"] == "zoom"
    assert body["external_event_id"] == "zoom-uuid-1"
    assert body["payload"] == payload
    assert body["received_at"]
    assert body["processed_at"] is None
    assert body["error"] is None
    assert _row_count(postgres_engine, tid) == 1


@pytest.mark.asyncio
async def test_post_webhook_inserts_manual_paste(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    payload = {
        "source_event_id": "paste-99",
        "title": "Manual transcript",
        "start_ts": "2026-05-24T09:00:00Z",
        "end_ts": "2026-05-24T10:00:00Z",
        "attendees": ["a@x.com"],
    }
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid}",
        json={"source": "manual_paste", "payload": payload},
    )
    assert r.status_code == 201, r.text
    assert r.json()["external_event_id"] == "paste-99"
    assert r.json()["source"] == "manual_paste"


@pytest.mark.asyncio
async def test_post_webhook_attaches_engagement_when_provided(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    e_resp = await m_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Customer A"},
    )
    eid = e_resp.json()["id"]
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid}",
        json={
            "source": "manual_paste",
            "payload": {"title": "Sync"},
            "engagement_id": eid,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["engagement_id"] == eid


@pytest.mark.asyncio
async def test_post_webhook_rejects_unknown_source(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid}",
        json={"source": "carrier_pigeon", "payload": {}},
    )
    assert r.status_code == 422
    assert "invalid source" in r.text


@pytest.mark.asyncio
async def test_post_webhook_unknown_tenant_returns_404(m_client: AsyncClient) -> None:
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={uuid.uuid4()}",
        json={"source": "manual_paste", "payload": {}},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_webhook_rejects_engagement_from_other_tenant(
    m_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    e_resp = await m_client.post(
        f"/internal/v1/engagements?tenant_id={tid_a}",
        json={"name": "tenant-A engagement"},
    )
    eid = e_resp.json()["id"]
    r = await m_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid_b}",
        json={
            "source": "manual_paste",
            "payload": {"title": "x"},
            "engagement_id": eid,
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_webhook_requires_internal_key(postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as raw:
        r = await raw.post(
            f"/internal/v1/meetings/webhook?tenant_id={tid}",
            json={"source": "manual_paste", "payload": {}},
        )
    assert r.status_code == 401
