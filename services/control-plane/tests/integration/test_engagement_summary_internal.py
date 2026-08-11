"""Integration: GET /internal/v1/engagements/{id}/summary (Wave 2.5, ticket U6).

Three tiers of coverage:

- hand-seeded engagement — exact counts for every field, the risk open/closed
  convention, recent-changes shaping (bucket, humanized title, actor names),
  and the U2 members display_name/email join (summary + /members + /detail).
- BlueState seed — counts line up with the scenario's own summary numbers.
- BlueState-XL seed — sane counts and a loose latency budget on ~4k ledger
  events (the endpoint is the engagement page's first-paint payload).
"""

from __future__ import annotations

import json
import time
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
from control_plane.services.engagement_legibility import RECENT_CHANGE_BUCKETS

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "summary-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=180.0)
    client.headers["X-DeployAI-Internal-Key"] = "summary-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest_asyncio.fixture
async def db_session(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    engine = create_async_engine(_async_url(postgres_engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# --- sync seed helpers --------------------------------------------------------


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'summary-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(
    engine: Engine,
    uid: uuid.UUID,
    tid: uuid.UUID,
    *,
    user_name: str,
    email: str | None = None,
    given_name: str | None = None,
    family_name: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email, given_name, family_name) "
                "VALUES (:u, :t, :n, :e, :g, :f)"
            ),
            {"u": str(uid), "t": str(tid), "n": user_name, "e": email, "g": given_name, "f": family_name},
        )


def _seed_engagement(engine: Engine, tid: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        eid = conn.execute(
            text("INSERT INTO engagements (tenant_id, name, customer_account) VALUES (:t, :n, :c) RETURNING id"),
            {"t": str(tid), "n": "Harbor Rollout", "c": "Harbor City"},
        ).scalar_one()
    return cast(uuid.UUID, eid)


def _seed_member(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, uid: uuid.UUID, role: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO engagement_members (tenant_id, engagement_id, user_id, role) VALUES (:t, :e, :u, :r)"),
            {"t": str(tid), "e": str(eid), "u": str(uid), "r": role},
        )


def _seed_node(
    engine: Engine, tid: uuid.UUID, eid: uuid.UUID, node_type: str, title: str, node_status: str | None = None
) -> uuid.UUID:
    with engine.begin() as conn:
        nid = conn.execute(
            text(
                "INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title, status) "
                "VALUES (:t, :e, :nt, :title, :s) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "nt": node_type, "title": title, "s": node_status},
        ).scalar_one()
    return cast(uuid.UUID, nid)


def _seed_event(engine: Engine, tid: uuid.UUID, eid: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        ev = conn.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(tenant_id, engagement_id, event_type, occurred_at, payload) "
                "VALUES (:t, :e, 'ingest.meeting_note', now(), CAST(:p AS jsonb)) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "p": json.dumps({"content": {"text": "note"}})},
        ).scalar_one()
    return cast(uuid.UUID, ev)


def _seed_proposal(engine: Engine, tid: uuid.UUID, eid: uuid.UUID, event_id: uuid.UUID, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_proposals "
                "(tenant_id, engagement_id, source_event_id, proposal_kind, payload, status) "
                "VALUES (:t, :e, :ev, 'node', CAST(:p AS jsonb), :s)"
            ),
            {
                "t": str(tid),
                "e": str(eid),
                "ev": str(event_id),
                "p": json.dumps({"node_type": "risk", "title": "Drift"}),
                "s": status,
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


def _seed_ledger_event(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID,
    *,
    occurred_at: datetime,
    source_kind: str,
    summary: str,
    actor_kind: str = "user",
    actor_id: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:t, :e, :ts, :ak, :ai, :sk, :su, '{}'::jsonb)"
            ),
            {
                "t": str(tid),
                "e": str(eid),
                "ts": occurred_at,
                "ak": actor_kind,
                "ai": actor_id,
                "sk": source_kind,
                "su": summary,
            },
        )


# --- hand-seeded exact counts -------------------------------------------------


@pytest.mark.asyncio
async def test_summary_exact_counts_and_shapes(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    _ins_user(
        postgres_engine,
        u1,
        tid,
        user_name="ada.lovelace",
        email="ada.lovelace@example.com",
        given_name="Ada",
        family_name="Lovelace",
    )
    _ins_user(postgres_engine, u2, tid, user_name="jo.march@example.com", email="jo.march@example.com")

    eid = _seed_engagement(postgres_engine, tid)
    _seed_member(postgres_engine, tid, eid, u1, "fde")
    _seed_member(postgres_engine, tid, eid, u2, "biz_dev")

    # Nodes: 2 stakeholders, 3 decisions, 1 commitment, 2 open risks (NULL +
    # free-form status), 2 closed risks (terminal statuses).
    _seed_node(postgres_engine, tid, eid, "stakeholder", "Pat Vance")
    _seed_node(postgres_engine, tid, eid, "stakeholder", "Raj Patel")
    _seed_node(postgres_engine, tid, eid, "decision", "Adopt cache")
    _seed_node(postgres_engine, tid, eid, "decision", "Pick vendor")
    _seed_node(postgres_engine, tid, eid, "decision", "Pilot region")
    _seed_node(postgres_engine, tid, eid, "commitment", "Ship report weekly")
    _seed_node(postgres_engine, tid, eid, "risk", "Latency SLA", None)
    _seed_node(postgres_engine, tid, eid, "risk", "Training behind", "investigating")
    _seed_node(postgres_engine, tid, eid, "risk", "Rate limits", "closed")
    _seed_node(postgres_engine, tid, eid, "risk", "PD staleness", "Mitigated")

    # Proposals: 2 pending, 1 accepted.
    ev = _seed_event(postgres_engine, tid, eid)
    _seed_proposal(postgres_engine, tid, eid, ev, "pending")
    _seed_proposal(postgres_engine, tid, eid, ev, "pending")
    _seed_proposal(postgres_engine, tid, eid, ev, "accepted")

    # Review items: 2 open escalations (+1 resolved), 1 open dispute (+1 dismissed).
    _seed_review_item(postgres_engine, tid, eid, "agent_escalation", "open")
    _seed_review_item(postgres_engine, tid, eid, "agent_escalation", "open")
    _seed_review_item(postgres_engine, tid, eid, "agent_escalation", "resolved")
    _seed_review_item(postgres_engine, tid, eid, "citation_dispute", "open")
    _seed_review_item(postgres_engine, tid, eid, "citation_dispute", "dismissed")

    # 12 ledger events so the feed truncates to 10, newest first.
    base = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    for i in range(9):
        _seed_ledger_event(
            postgres_engine,
            tid,
            eid,
            occurred_at=base + timedelta(hours=i),
            source_kind="email_ingest",
            summary=f"filler event {i}",
        )
    _seed_ledger_event(
        postgres_engine,
        tid,
        eid,
        occurred_at=base + timedelta(days=1),
        source_kind="matrix_node_created",
        summary="node created: Adopt cache",
        actor_id=str(u1),
    )
    _seed_ledger_event(
        postgres_engine,
        tid,
        eid,
        occurred_at=base + timedelta(days=1, hours=1),
        source_kind="insight_opened",
        summary="risk opened: latency over SLA",
        actor_id="marcus.rivera@deployai.com",
    )
    _seed_ledger_event(
        postgres_engine,
        tid,
        eid,
        occurred_at=base + timedelta(days=1, hours=2),
        source_kind="proposal_auto_accepted",
        summary="proposal accepted: node",
        actor_kind="system",
        actor_id="auto_accept",
    )

    r = await s_client.get(f"/internal/v1/engagements/{eid}/summary?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["engagement"]["id"] == str(eid)
    assert body["engagement"]["name"] == "Harbor Rollout"
    assert body["engagement"]["customer_account"] == "Harbor City"
    assert body["engagement"]["status"] == "active"
    assert set(body["engagement"].keys()) == {
        "id",
        "name",
        "customer_account",
        "current_phase",
        "status",
        "updated_at",
    }

    assert body["counts"] == {
        "stakeholders": 2,
        "decisions": 3,
        "risks_open": 2,
        "commitments": 1,
        "proposals_pending": 2,
        "escalations_open": 2,
        "disputes_open": 1,
    }

    members = {m["user_id"]: m for m in body["members"]}
    assert set(members) == {str(u1), str(u2)}
    assert members[str(u1)]["display_name"] == "Ada Lovelace"
    assert members[str(u1)]["email"] == "ada.lovelace@example.com"
    assert members[str(u1)]["role"] == "fde"
    assert members[str(u2)]["display_name"] == "jo.march"  # email local-part fallback

    changes = body["recent_changes"]
    assert len(changes) == 10
    occurred = [c["occurred_at"] for c in changes]
    assert occurred == sorted(occurred, reverse=True)
    assert all(c["kind"] in RECENT_CHANGE_BUCKETS for c in changes)

    # Newest three are the shaped ones; check bucket, humanized title, actor.
    assert changes[0]["kind"] == "proposal"
    assert changes[0]["title"] == "proposal accepted: node"  # degenerate remainder kept whole
    assert changes[0]["actor_display_name"] == "System"
    assert changes[1]["kind"] == "risk"
    assert changes[1]["title"] == "latency over SLA"
    assert changes[1]["actor_display_name"] == "marcus.rivera"
    assert changes[2]["kind"] == "other"
    assert changes[2]["title"] == "Adopt cache"
    assert changes[2]["actor_display_name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_summary_unknown_engagement_404(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await s_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/summary?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_summary_cross_tenant_404(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)
    eid = _seed_engagement(postgres_engine, tid_a)
    r = await s_client.get(f"/internal/v1/engagements/{eid}/summary?tenant_id={tid_b}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_summary_empty_engagement_zero_counts(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _seed_engagement(postgres_engine, tid)
    r = await s_client.get(f"/internal/v1/engagements/{eid}/summary?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["members"] == []
    assert body["recent_changes"] == []
    assert all(v == 0 for v in body["counts"].values())


# --- U2: members display_name/email join on /members and /detail --------------


@pytest.mark.asyncio
async def test_members_routes_carry_display_name_and_email(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    u1 = uuid.uuid4()
    _ins_user(
        postgres_engine,
        u1,
        tid,
        user_name="alex.chen",
        email="alex.chen@deployai.com",
        given_name="Alex",
        family_name="Chen",
    )
    eid = _seed_engagement(postgres_engine, tid)
    _seed_member(postgres_engine, tid, eid, u1, "deployment_strategist")

    r_members = await s_client.get(f"/internal/v1/engagements/{eid}/members?tenant_id={tid}")
    assert r_members.status_code == 200, r_members.text
    (member,) = r_members.json()
    # Existing fields preserved (additive change only).
    assert member["user_id"] == str(u1)
    assert member["role"] == "deployment_strategist"
    assert "id" in member and "engagement_id" in member and "created_at" in member
    # New fields.
    assert member["display_name"] == "Alex Chen"
    assert member["email"] == "alex.chen@deployai.com"

    r_detail = await s_client.get(f"/internal/v1/engagements/{eid}/detail?tenant_id={tid}")
    assert r_detail.status_code == 200, r_detail.text
    (detail_member,) = r_detail.json()["members"]
    assert detail_member["display_name"] == "Alex Chen"
    assert detail_member["email"] == "alex.chen@deployai.com"


# --- BlueState seed: counts line up with the scenario summary -----------------


@pytest.mark.asyncio
async def test_summary_bluestate_seed_counts(s_client: AsyncClient, db_session, postgres_engine: Engine) -> None:
    from control_plane.scenarios.bluestate.runner import apply_bluestate_scenario

    tid = uuid.uuid4()
    seeded = await apply_bluestate_scenario(db_session, tenant_id=tid, skip_snapshots=True, skip_analyzers=True)
    await db_session.commit()
    eid = seeded.engagement_id

    r = await s_client.get(f"/internal/v1/engagements/{eid}/summary?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()

    counts = body["counts"]
    assert counts["stakeholders"] == seeded.stakeholder_nodes
    assert counts["stakeholders"] > 0
    assert counts["decisions"] == seeded.decision_nodes
    assert counts["decisions"] > 0
    # BlueState tracks risks as matrix_insights, not risk-typed matrix nodes,
    # so the node-based risks_open count is 0 by construction.
    assert counts["risks_open"] == 0
    assert counts["escalations_open"] == 0
    assert counts["disputes_open"] == 0

    with postgres_engine.begin() as conn:
        expected_commitments = conn.execute(
            text(
                "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:e AS uuid) AND node_type = 'commitment'"
            ),
            {"e": str(eid)},
        ).scalar_one()
        expected_pending = conn.execute(
            text("SELECT count(*) FROM matrix_proposals WHERE engagement_id = CAST(:e AS uuid) AND status = 'pending'"),
            {"e": str(eid)},
        ).scalar_one()
    assert counts["commitments"] == expected_commitments
    assert counts["proposals_pending"] == expected_pending

    members = {m["display_name"] for m in body["members"]}
    assert members == {"Alex Chen", "Jordan Park", "Sam Lee"}

    changes = body["recent_changes"]
    assert len(changes) == 10
    occurred = [c["occurred_at"] for c in changes]
    assert occurred == sorted(occurred, reverse=True)
    assert all(c["kind"] in RECENT_CHANGE_BUCKETS for c in changes)
    assert all(c["title"] for c in changes)
    assert all(c["actor_display_name"] for c in changes)


# --- BlueState-XL seed: sane counts, loose latency budget ---------------------


@pytest.mark.asyncio
async def test_summary_xl_seed_correct_and_fast(s_client: AsyncClient, db_session, postgres_engine: Engine) -> None:
    from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario

    tid = uuid.uuid4()
    seeded = await apply_bluestate_xl_scenario(db_session, tenant_id=tid, days=365, skip_snapshots=True)
    await db_session.commit()
    eid = seeded.engagement_id
    assert seeded.ledger_event_count > 3000  # the XL corpus is the point

    started = time.perf_counter()
    r = await s_client.get(f"/internal/v1/engagements/{eid}/summary?tenant_id={tid}")
    elapsed = time.perf_counter() - started
    assert r.status_code == 200, r.text
    # Target is <100ms; the assert stays loose (<1s) to avoid CI flake.
    assert elapsed < 1.0, f"summary took {elapsed:.3f}s on the XL seed"

    body = r.json()
    counts = body["counts"]
    assert counts["stakeholders"] == seeded.stakeholder_node_count
    assert counts["decisions"] == seeded.decision_node_count
    assert counts["stakeholders"] > 50
    assert counts["decisions"] > 100

    with postgres_engine.begin() as conn:
        expected_commitments = conn.execute(
            text(
                "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:e AS uuid) AND node_type = 'commitment'"
            ),
            {"e": str(eid)},
        ).scalar_one()
    assert counts["commitments"] == expected_commitments

    changes = body["recent_changes"]
    assert len(changes) == 10
    occurred = [c["occurred_at"] for c in changes]
    assert occurred == sorted(occurred, reverse=True)
