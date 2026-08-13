"""Integration: /internal/v1/engagements/{id}/gap-asks (Wave 5, GA1).

Covers the recompute → filter loop end to end: a seeded gappy engagement
produces the expected asks, dismiss/snooze hide them durably across
recomputes, and an expired snooze resurfaces the ask.
"""

from __future__ import annotations

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
async def g_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "gap-asks-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=180.0)
    client.headers["X-DeployAI-Internal-Key"] = "gap-asks-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


# --- sync seed helpers --------------------------------------------------------


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'gap-asks-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _seed_engagement(engine: Engine, tid: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        eid = conn.execute(
            text("INSERT INTO engagements (tenant_id, name, customer_account) VALUES (:t, :n, :c) RETURNING id"),
            {"t": str(tid), "n": "Harbor Rollout", "c": "Harbor City"},
        ).scalar_one()
    return cast(uuid.UUID, eid)


def _seed_node(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID,
    node_type: str,
    title: str,
    *,
    node_status: str | None = None,
    evidence_event_ids: list[uuid.UUID] | None = None,
    attributes: str = "{}",
) -> uuid.UUID:
    ev_literal = "{" + ",".join(str(e) for e in (evidence_event_ids or [])) + "}"
    with engine.begin() as conn:
        nid = conn.execute(
            text(
                "INSERT INTO matrix_nodes "
                "(tenant_id, engagement_id, node_type, title, status, evidence_event_ids, attributes) "
                "VALUES (:t, :e, :nt, :title, :s, CAST(:ev AS uuid[]), CAST(:a AS jsonb)) RETURNING id"
            ),
            {
                "t": str(tid),
                "e": str(eid),
                "nt": node_type,
                "title": title,
                "s": node_status,
                "ev": ev_literal,
                "a": attributes,
            },
        ).scalar_one()
    return cast(uuid.UUID, nid)


def _seed_edge(
    engine: Engine, tid: uuid.UUID, eid: uuid.UUID, edge_type: str, from_id: uuid.UUID, to_id: uuid.UUID
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_edges (tenant_id, engagement_id, edge_type, from_node_id, to_node_id) "
                "VALUES (:t, :e, :et, :f, :to)"
            ),
            {"t": str(tid), "e": str(eid), "et": edge_type, "f": str(from_id), "to": str(to_id)},
        )


def _seed_event(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, occurred_at: datetime) -> uuid.UUID:
    with engine.begin() as conn:
        ev = conn.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(tenant_id, engagement_id, event_type, occurred_at, payload) "
                "VALUES (:t, :e, 'ingest.meeting_note', :ts, '{}'::jsonb) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "ts": occurred_at},
        ).scalar_one()
    return cast(uuid.UUID, ev)


def _seed_gappy_engagement(engine: Engine, tid: uuid.UUID) -> uuid.UUID:
    """One engagement exercising every rule: unowned commitment, unmitigated
    open risk, evidence-less decision, no sponsor, silent for 20 days."""
    eid = _seed_engagement(engine, tid)
    old_event = _seed_event(engine, tid, eid, datetime.now(UTC) - timedelta(days=20))
    _seed_node(engine, tid, eid, "stakeholder", "Jordan Kim")
    _seed_node(engine, tid, eid, "commitment", "Pilot launch by W24", evidence_event_ids=[old_event])
    _seed_node(engine, tid, eid, "risk", "Calibration slip", node_status="open")
    _seed_node(engine, tid, eid, "decision", "Phase 2 rollout approved")
    return eid


async def _get_asks(client: AsyncClient, tid: uuid.UUID, eid: uuid.UUID) -> list[dict[str, object]]:
    r = await client.get(f"/internal/v1/engagements/{eid}/gap-asks", params={"tenant_id": str(tid)})
    assert r.status_code == 200, r.text
    return cast(list[dict[str, object]], r.json()["asks"])


@pytest.mark.asyncio
async def test_gap_asks_fire_for_gappy_engagement(g_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_gappy_engagement(postgres_engine, tid)

    asks = await _get_asks(g_client, tid, eid)

    rules = {a["rule"] for a in asks}
    assert rules == {
        "commitment_no_owner",
        "commitment_no_recent_evidence",
        "risk_unmitigated",
        "no_sponsor",
        "decision_no_evidence",
        "engagement_silent",
    }
    # High severity sorts first; every ask carries the actionable fields.
    assert asks[0]["severity"] == "high"
    for a in asks:
        assert a["id"] and a["title"] and a["why"]
        assert a["remedy_kind"] in ("capture", "forward", "answer")


@pytest.mark.asyncio
async def test_gap_asks_quiet_for_well_formed_matrix(g_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_engagement(postgres_engine, tid)
    fresh_event = _seed_event(postgres_engine, tid, eid, datetime.now(UTC) - timedelta(days=1))
    sponsor = _seed_node(postgres_engine, tid, eid, "stakeholder", "Dana Vance", attributes='{"is_sponsor": true}')
    commitment = _seed_node(postgres_engine, tid, eid, "commitment", "MSA signed", evidence_event_ids=[fresh_event])
    _seed_edge(postgres_engine, tid, eid, "owed_by", commitment, sponsor)
    system = _seed_node(postgres_engine, tid, eid, "system", "LiDAR ingest")
    risk = _seed_node(postgres_engine, tid, eid, "risk", "Calibration slip", node_status="open")
    _seed_edge(postgres_engine, tid, eid, "blocks", risk, system)
    _seed_node(postgres_engine, tid, eid, "decision", "Go decision", evidence_event_ids=[fresh_event])

    asks = await _get_asks(g_client, tid, eid)

    assert asks == []


@pytest.mark.asyncio
async def test_gap_ask_dismiss_round_trip(g_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_gappy_engagement(postgres_engine, tid)

    asks = await _get_asks(g_client, tid, eid)
    target = next(a for a in asks if a["rule"] == "risk_unmitigated")

    r = await g_client.post(
        f"/internal/v1/engagements/{eid}/gap-asks/{target['id']}/dismiss",
        params={"tenant_id": str(tid)},
        json={"dismissed_by": "ada@example.com"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ask_id"] == target["id"]
    assert body["snooze_until"] is None

    # The recompute yields the same deterministic id, so the dismissal holds.
    after = await _get_asks(g_client, tid, eid)
    assert target["id"] not in {a["id"] for a in after}
    assert len(after) == len(asks) - 1


@pytest.mark.asyncio
async def test_gap_ask_snooze_hides_then_expiry_resurfaces(g_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_gappy_engagement(postgres_engine, tid)

    asks = await _get_asks(g_client, tid, eid)
    target = next(a for a in asks if a["rule"] == "engagement_silent")

    r = await g_client.post(
        f"/internal/v1/engagements/{eid}/gap-asks/{target['id']}/snooze",
        params={"tenant_id": str(tid)},
        json={"days": 7},
    )
    assert r.status_code == 200, r.text
    assert r.json()["snooze_until"] is not None

    hidden = await _get_asks(g_client, tid, eid)
    assert target["id"] not in {a["id"] for a in hidden}

    # Simulate the snooze lapsing; the ask must resurface. Also exercises
    # the dismiss upsert path (same unique row, updated in place).
    with postgres_engine.begin() as conn:
        conn.execute(
            text("UPDATE gap_ask_dismissals SET snooze_until = now() - interval '1 hour' WHERE ask_id = :a"),
            {"a": target["id"]},
        )
    resurfaced = await _get_asks(g_client, tid, eid)
    assert target["id"] in {a["id"] for a in resurfaced}


@pytest.mark.asyncio
async def test_gap_asks_404_for_unknown_engagement(g_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    r = await g_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/gap-asks", params={"tenant_id": str(tid)})
    assert r.status_code == 404
