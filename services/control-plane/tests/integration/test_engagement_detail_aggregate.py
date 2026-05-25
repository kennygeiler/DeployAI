"""Engagement-detail aggregate route (integration) — Phase D D3.a.

Collapses the six sequential CP round-trips the BFF used to issue into one
endpoint. See ``docs/perf/engagement-aggregate-query-budget.md``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration

_AGGREGATE_QUERY_BUDGET = 9


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "agg-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "agg-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'aggregate') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, uid: uuid.UUID, tid: uuid.UUID, name: str = "member") -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, :n)"),
            {"u": str(uid), "t": str(tid), "n": name},
        )


def _seed_engagement(engine: Engine, tid: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        eid = conn.execute(
            text("INSERT INTO engagements (tenant_id, name, customer_account) VALUES (:t, :n, :c) RETURNING id"),
            {"t": str(tid), "n": "NYC DOT LiDAR", "c": "NYC DOT"},
        ).scalar_one()
    return cast(uuid.UUID, eid)


def _seed_member(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, uid: uuid.UUID, role: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO engagement_members (tenant_id, engagement_id, user_id, role) VALUES (:t, :e, :u, :r)"),
            {"t": str(tid), "e": str(eid), "u": str(uid), "r": role},
        )


def _seed_node(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, node_type: str, title: str) -> uuid.UUID:
    with engine.begin() as conn:
        nid = conn.execute(
            text(
                "INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title) "
                "VALUES (:t, :e, :nt, :title) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "nt": node_type, "title": title},
        ).scalar_one()
    return cast(uuid.UUID, nid)


def _seed_edge(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID,
    edge_type: str,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_edges (tenant_id, engagement_id, edge_type, from_node_id, to_node_id) "
                "VALUES (:t, :e, :et, :f, :to)"
            ),
            {"t": str(tid), "e": str(eid), "et": edge_type, "f": str(from_id), "to": str(to_id)},
        )


def _seed_event(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, occurred_at: str, text_body: str) -> uuid.UUID:
    with engine.begin() as conn:
        ev = conn.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(tenant_id, engagement_id, event_type, occurred_at, payload) "
                "VALUES (:t, :e, 'ingest.meeting_note', :ts, CAST(:p AS jsonb)) RETURNING id"
            ),
            {
                "t": str(tid),
                "e": str(eid),
                "ts": occurred_at,
                "p": json.dumps({"content": {"text": text_body}}),
            },
        ).scalar_one()
    return cast(uuid.UUID, ev)


def _seed_insight(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID,
    *,
    severity: str,
    title: str,
    dedup_key: str,
) -> uuid.UUID:
    with engine.begin() as conn:
        iid = conn.execute(
            text(
                "INSERT INTO matrix_insights "
                "(tenant_id, engagement_id, agent, insight_type, severity, title, body, dedup_key) "
                "VALUES (:t, :e, 'oracle', 'stale_commitment', :sev, :title, 'b', :dk) "
                "RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "sev": severity, "title": title, "dk": dedup_key},
        ).scalar_one()
    return cast(uuid.UUID, iid)


def _seed_proposal(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, event_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        pid = conn.execute(
            text(
                "INSERT INTO matrix_proposals "
                "(tenant_id, engagement_id, source_event_id, proposal_kind, payload) "
                "VALUES (:t, :e, :ev, 'node', CAST(:p AS jsonb)) RETURNING id"
            ),
            {
                "t": str(tid),
                "e": str(eid),
                "ev": str(event_id),
                "p": json.dumps({"node_type": "risk", "title": "Calibration"}),
            },
        ).scalar_one()
    return cast(uuid.UUID, pid)


def _seed_custom_node_type(engine: Engine, tid: uuid.UUID, name: str, label: str, color: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant_node_types (tenant_id, name, label, color) VALUES (:t, :n, :l, :c)"),
            {"t": str(tid), "n": name, "l": label, "c": color},
        )


@pytest.mark.asyncio
async def test_aggregate_returns_all_six_sections(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    _ins_user(postgres_engine, u1, tid, name="member_one")
    _ins_user(postgres_engine, u2, tid, name="member_two")

    eid = _seed_engagement(postgres_engine, tid)
    _seed_member(postgres_engine, tid, eid, u1, "fde")
    _seed_member(postgres_engine, tid, eid, u2, "deployment_strategist")

    n1 = _seed_node(postgres_engine, tid, eid, "system", "LiDAR ingest")
    n2 = _seed_node(postgres_engine, tid, eid, "decision", "Pick vendor")
    n3 = _seed_node(postgres_engine, tid, eid, "risk", "Calibration drift")
    _seed_edge(postgres_engine, tid, eid, "threatens", n3, n1)
    _seed_edge(postgres_engine, tid, eid, "depends_on", n2, n1)

    _seed_insight(
        postgres_engine,
        tid,
        eid,
        severity="high",
        title="Stale commitment",
        dedup_key=f"oracle:stale_commitment:{eid}:{n1}",
    )

    for i in range(5):
        ev = _seed_event(postgres_engine, tid, eid, f"2026-05-{20 + i}T10:00:00+00:00", f"note {i}")
        if i == 0:
            _seed_proposal(postgres_engine, tid, eid, ev)

    _seed_custom_node_type(postgres_engine, tid, "north_corridor", "North Corridor", "#aa00ff")

    r = await e_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engagement"]["id"] == str(eid)
    assert body["engagement"]["name"] == "NYC DOT LiDAR"
    assert {m["user_id"] for m in body["members"]} == {str(u1), str(u2)}
    assert len(body["matrix_nodes"]) == 3
    assert {n["title"] for n in body["matrix_nodes"]} == {
        "LiDAR ingest",
        "Pick vendor",
        "Calibration drift",
    }
    assert len(body["matrix_edges"]) == 2
    assert {e["edge_type"] for e in body["matrix_edges"]} == {"threatens", "depends_on"}
    assert len(body["matrix_proposals"]) == 1
    assert body["matrix_proposals"][0]["status"] == "pending"
    assert len(body["custom_node_types"]) == 1
    assert body["custom_node_types"][0]["name"] == "north_corridor"
    assert body["custom_node_types"][0]["color"] == "#aa00ff"
    assert len(body["insights"]) == 1
    assert body["insights"][0]["title"] == "Stale commitment"
    assert len(body["recent_activity_events"]) == 5
    # Newest first (descending by occurred_at).
    occurred = [e["occurred_at"] for e in body["recent_activity_events"]]
    assert occurred == sorted(occurred, reverse=True)


@pytest.mark.asyncio
async def test_aggregate_query_count_under_budget(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """The aggregate must run in at most ``_AGGREGATE_QUERY_BUDGET`` statements.

    Today's six independent CP routes consume ~10-11 statements per page-load
    (each runs its own ``_require_engagement`` guard). One round of the
    aggregate replaces all of them; the guard runs once.
    """
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_engagement(postgres_engine, tid)
    u = uuid.uuid4()
    _ins_user(postgres_engine, u, tid)
    _seed_member(postgres_engine, tid, eid, u, "fde")
    n = _seed_node(postgres_engine, tid, eid, "system", "X")
    _seed_event(postgres_engine, tid, eid, "2026-05-20T10:00:00+00:00", "n")
    _seed_proposal(postgres_engine, tid, eid, _seed_event(postgres_engine, tid, eid, "2026-05-21T10:00:00+00:00", "m"))
    _seed_insight(postgres_engine, tid, eid, severity="medium", title="t", dedup_key=f"k:{n}")

    counter = {"n": 0}

    def _count(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        # SELECTs only — the aggregate is read-only; filter out the
        # connection-setup pings (BEGIN / SET / SHOW) so the budget tracks
        # actual data fetches.
        s = statement.lstrip().upper()
        if s.startswith("SELECT"):
            counter["n"] += 1

    event.listen(postgres_engine, "before_cursor_execute", _count)
    try:
        counter["n"] = 0
        r = await e_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid}")
        assert r.status_code == 200, r.text
    finally:
        event.remove(postgres_engine, "before_cursor_execute", _count)

    assert counter["n"] <= _AGGREGATE_QUERY_BUDGET, (
        f"aggregate ran {counter['n']} SELECTs (budget {_AGGREGATE_QUERY_BUDGET})"
    )


@pytest.mark.asyncio
async def test_aggregate_unknown_engagement_404(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/detail?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_cross_tenant_404(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """An engagement owned by tenant A is not visible via tenant B's scope."""
    tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)
    eid = _seed_engagement(postgres_engine, tid_a)

    r = await e_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid_b}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_empty_collections(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """A fresh engagement with no children returns all sections as empty lists."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_engagement(postgres_engine, tid)

    r = await e_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["members"] == []
    assert body["matrix_nodes"] == []
    assert body["matrix_edges"] == []
    assert body["matrix_proposals"] == []
    assert body["custom_node_types"] == []
    assert body["insights"] == []
    assert body["recent_activity_events"] == []


@pytest.mark.asyncio
async def test_aggregate_activity_events_limited_to_50(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """recent_activity_events caps at 50 with newest first."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_engagement(postgres_engine, tid)
    for i in range(60):
        # Increase day-of-month so each event sorts deterministically.
        ts = f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T10:00:00+00:00"
        _seed_event(postgres_engine, tid, eid, ts, f"note {i}")

    r = await e_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recent_activity_events"]) == 50
    occurred = [e["occurred_at"] for e in body["recent_activity_events"]]
    assert occurred == sorted(occurred, reverse=True)
