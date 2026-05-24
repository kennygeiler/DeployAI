"""Email paste-import internal route (integration) — Phase C inc 9.1."""

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
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "emails-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "emails-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'emails-test')"),
            {"t": str(tid)},
        )
    return tid


def _row_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    with engine.begin() as conn:
        r = conn.execute(
            text("SELECT count(*) FROM email_ingest_events WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        )
        return int(r.scalar_one())


_SINGLE_MESSAGE = (
    "Message-ID: <abc-1@deploy.ai>\r\n"
    "From: FDE <fde@deploy.ai>\r\n"
    "To: dev@customer.example\r\n"
    "Subject: Kick-off thread\r\n"
    "Date: Sun, 24 May 2026 15:00:00 +0000\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "Hello — picking up where we left off.\r\n"
)


_MBOX_TWO = (
    "From fde@deploy.ai Sun May 24 15:00:00 2026\r\n"
    "Message-ID: <one@deploy.ai>\r\n"
    "From: fde@deploy.ai\r\n"
    "To: a@x.com\r\n"
    "Subject: first\r\n"
    "Date: Sun, 24 May 2026 15:00:00 +0000\r\n"
    "\r\n"
    "first body\r\n"
    "\r\n"
    "From fde@deploy.ai Sun May 24 16:00:00 2026\r\n"
    "Message-ID: <two@deploy.ai>\r\n"
    "From: fde@deploy.ai\r\n"
    "To: b@x.com\r\n"
    "Subject: second\r\n"
    "Date: Sun, 24 May 2026 16:00:00 +0000\r\n"
    "\r\n"
    "second body\r\n"
)


@pytest.mark.asyncio
async def test_post_ingest_inserts_single_imap_paste(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid}",
        json={"source": "imap_paste", "raw": _SINGLE_MESSAGE},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    row = body[0]
    assert row["tenant_id"] == str(tid)
    assert row["engagement_id"] is None
    assert row["source"] == "imap_paste"
    assert row["external_message_id"] == "<abc-1@deploy.ai>"
    assert row["parsed_subject"] == "Kick-off thread"
    assert row["parsed_from"] == "fde@deploy.ai"
    assert row["parsed_to"] == ["dev@customer.example"]
    assert row["parsed_date"] is not None
    assert row["received_at"]
    assert row["processed_at"] is None
    assert row["error"] is None
    assert row["raw_payload"] == _SINGLE_MESSAGE
    assert _row_count(postgres_engine, tid) == 1


@pytest.mark.asyncio
async def test_post_ingest_mbox_inserts_each_message(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid}",
        json={"source": "mbox_paste", "raw": _MBOX_TWO},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    subjects = [row["parsed_subject"] for row in body]
    assert subjects == ["first", "second"]
    ids = [row["external_message_id"] for row in body]
    assert ids == ["<one@deploy.ai>", "<two@deploy.ai>"]
    assert _row_count(postgres_engine, tid) == 2


@pytest.mark.asyncio
async def test_post_ingest_attaches_engagement_when_provided(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    e_resp = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Customer A"},
    )
    eid = e_resp.json()["id"]
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid}",
        json={
            "source": "manual_paste",
            "raw": _SINGLE_MESSAGE,
            "engagement_id": eid,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()[0]["engagement_id"] == eid


@pytest.mark.asyncio
async def test_post_ingest_rejects_unknown_source(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid}",
        json={"source": "carrier_pigeon", "raw": _SINGLE_MESSAGE},
    )
    assert r.status_code == 422
    assert "invalid source" in r.text


@pytest.mark.asyncio
async def test_post_ingest_unknown_tenant_returns_404(e_client: AsyncClient) -> None:
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={uuid.uuid4()}",
        json={"source": "imap_paste", "raw": _SINGLE_MESSAGE},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_ingest_rejects_engagement_from_other_tenant(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    e_resp = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid_a}",
        json={"name": "tenant-A engagement"},
    )
    eid = e_resp.json()["id"]
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid_b}",
        json={
            "source": "imap_paste",
            "raw": _SINGLE_MESSAGE,
            "engagement_id": eid,
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_ingest_requires_internal_key(postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as raw:
        r = await raw.post(
            f"/internal/v1/emails/ingest?tenant_id={tid}",
            json={"source": "imap_paste", "raw": _SINGLE_MESSAGE},
        )
    assert r.status_code == 401
