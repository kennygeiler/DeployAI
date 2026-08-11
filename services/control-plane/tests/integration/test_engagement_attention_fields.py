"""Integration: U7 needs-attention fields on GET /internal/v1/engagements.

Each list row gains ``needs_attention`` (proposals_pending, escalations_open,
days_since_last_event) and ``attention_score`` — additive fields; the existing
row shape must survive unchanged.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

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
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "attention-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "attention-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'attention-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _seed_engagement(engine: Engine, tid: uuid.UUID, name: str) -> uuid.UUID:
    with engine.begin() as conn:
        eid = conn.execute(
            text("INSERT INTO engagements (tenant_id, name) VALUES (:t, :n) RETURNING id"),
            {"t": str(tid), "n": name},
        ).scalar_one()
    return cast(uuid.UUID, eid)


def _seed_pending_proposals(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, n: int) -> None:
    with engine.begin() as conn:
        ev = conn.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(tenant_id, engagement_id, event_type, occurred_at, payload) "
                "VALUES (:t, :e, 'ingest.meeting_note', now(), CAST(:p AS jsonb)) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "p": json.dumps({"content": {"text": "n"}})},
        ).scalar_one()
        for _ in range(n):
            conn.execute(
                text(
                    "INSERT INTO matrix_proposals "
                    "(tenant_id, engagement_id, source_event_id, proposal_kind, payload, status) "
                    "VALUES (:t, :e, :ev, 'node', CAST(:p AS jsonb), 'pending')"
                ),
                {
                    "t": str(tid),
                    "e": str(eid),
                    "ev": str(ev),
                    "p": json.dumps({"node_type": "risk", "title": "x"}),
                },
            )


def _seed_review_item(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, kind: str, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO review_items (tenant_id, engagement_id, kind, status, payload) "
                "VALUES (:t, :e, :k, :s, '{}'::jsonb)"
            ),
            {"t": str(tid), "e": str(eid), "k": kind, "s": status},
        )


def _seed_ledger_event(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, occurred_at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:t, :e, :ts, 'user', NULL, 'manual_capture', 'note', '{}'::jsonb)"
            ),
            {"t": str(tid), "e": str(eid), "ts": occurred_at},
        )


@pytest.mark.asyncio
async def test_list_rows_carry_attention_fields(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    now = datetime.now(UTC)

    # Busy: 2 pending proposals, 1 open escalation (+ noise that must not
    # count: resolved escalation, open dispute), fresh activity.
    busy = _seed_engagement(postgres_engine, tid, "busy")
    _seed_pending_proposals(postgres_engine, tid, busy, 2)
    _seed_review_item(postgres_engine, tid, busy, "agent_escalation", "open")
    _seed_review_item(postgres_engine, tid, busy, "agent_escalation", "resolved")
    _seed_review_item(postgres_engine, tid, busy, "citation_dispute", "open")
    _seed_ledger_event(postgres_engine, tid, busy, now - timedelta(hours=2))

    # Stale: nothing pending, last event 30 days ago.
    stale = _seed_engagement(postgres_engine, tid, "stale")
    _seed_ledger_event(postgres_engine, tid, stale, now - timedelta(days=30))

    # Fresh: no proposals, no review items, no ledger events at all.
    fresh = _seed_engagement(postgres_engine, tid, "fresh")

    r = await a_client.get(f"/internal/v1/engagements?tenant_id={tid}")
    assert r.status_code == 200, r.text
    rows = {row["name"]: row for row in r.json()}
    assert set(rows) == {"busy", "stale", "fresh"}

    # Existing row shape preserved (additive change only).
    expected_keys = (
        "id",
        "tenant_id",
        "name",
        "customer_account",
        "current_phase",
        "status",
        "created_at",
        "updated_at",
    )
    for row in rows.values():
        for key in expected_keys:
            assert key in row, key

    assert rows["busy"]["needs_attention"] == {
        "proposals_pending": 2,
        "escalations_open": 1,
        "days_since_last_event": 0,
    }
    assert rows["busy"]["attention_score"] == 4  # 2 + 2*1 + 0

    assert rows["stale"]["needs_attention"] == {
        "proposals_pending": 0,
        "escalations_open": 0,
        "days_since_last_event": 30,
    }
    assert rows["stale"]["attention_score"] == 3  # stale bonus only

    assert rows["fresh"]["needs_attention"] == {
        "proposals_pending": 0,
        "escalations_open": 0,
        "days_since_last_event": None,
    }
    assert rows["fresh"]["attention_score"] == 0

    assert str(busy) == rows["busy"]["id"]
    assert str(stale) == rows["stale"]["id"]
    assert str(fresh) == rows["fresh"]["id"]


@pytest.mark.asyncio
async def test_attention_fields_scoped_to_tenant(a_client: AsyncClient, postgres_engine: Engine) -> None:
    """Another tenant's proposals/escalations never bleed into the rows."""
    tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)
    eng_a = _seed_engagement(postgres_engine, tid_a, "mine")
    eng_b = _seed_engagement(postgres_engine, tid_b, "theirs")
    _seed_pending_proposals(postgres_engine, tid_b, eng_b, 3)
    _seed_review_item(postgres_engine, tid_b, eng_b, "agent_escalation", "open")

    r = await a_client.get(f"/internal/v1/engagements?tenant_id={tid_a}")
    assert r.status_code == 200, r.text
    (row,) = r.json()
    assert row["id"] == str(eng_a)
    assert row["needs_attention"]["proposals_pending"] == 0
    assert row["needs_attention"]["escalations_open"] == 0
    assert row["attention_score"] == 0
