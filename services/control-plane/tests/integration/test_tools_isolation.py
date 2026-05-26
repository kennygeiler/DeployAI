"""Cross-engagement isolation: every tool must refuse engagement-B data.

Seeds two engagements under one tenant (cross-engagement leak risk) and
one engagement under a second tenant (cross-tenant leak risk). For every
tool we assert that scoping the call to engagement-A returns rows whose
ids belong only to engagement-A — never to its sibling B or the foreign
tenant's engagement C.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.analysis import (
    get_decision_history,
    get_engagement_summary,
    get_open_risks,
)
from control_plane.agents.tools.escalate import propose_action
from control_plane.agents.tools.ledger import query_ledger, walk_chain
from control_plane.agents.tools.matrix import (
    get_matrix_neighbors,
    get_matrix_node,
    get_matrix_subgraph,
)
from control_plane.agents.tools.search import keyword_search, vector_search
from control_plane.agents.tools.synthesis import read_synthesis
from control_plane.db import clear_engine_cache, get_app_db_session

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def app_session(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    clear_engine_cache()
    try:
        yield None
    finally:
        clear_engine_cache()


@pytest.fixture
def fixture(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    """Two tenants by engagements with overlapping shapes for isolation tests."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    eng_a1 = uuid.uuid4()
    eng_a2 = uuid.uuid4()
    eng_b = uuid.uuid4()
    with postgres_engine.begin() as c:
        for tid, name in ((tid_a, "iso-a"), (tid_b, "iso-b")):
            c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": name})
        for tid, eid, n in (
            (tid_a, eng_a1, "a1"),
            (tid_a, eng_a2, "a2"),
            (tid_b, eng_b, "b"),
        ):
            c.execute(
                text(
                    "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                    "VALUES (:i, :t, :n, 'P1_pre_engagement', 'active')"
                ),
                {"i": str(eid), "t": str(tid), "n": n},
            )

    decision_a1 = _ins_node(
        postgres_engine, tenant_id=tid_a, engagement_id=eng_a1, node_type="decision", title="A1-secret"
    )
    decision_a2 = _ins_node(
        postgres_engine, tenant_id=tid_a, engagement_id=eng_a2, node_type="decision", title="A2-secret"
    )
    decision_b = _ins_node(
        postgres_engine, tenant_id=tid_b, engagement_id=eng_b, node_type="decision", title="B-secret"
    )
    risk_a1 = _ins_risk_insight(
        postgres_engine, tenant_id=tid_a, engagement_id=eng_a1, severity="high", title="A1-risk"
    )
    risk_a2 = _ins_risk_insight(
        postgres_engine, tenant_id=tid_a, engagement_id=eng_a2, severity="high", title="A2-risk"
    )
    risk_b = _ins_risk_insight(postgres_engine, tenant_id=tid_b, engagement_id=eng_b, severity="high", title="B-risk")
    ev_a1 = _ins_event(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eng_a1,
        source_kind="proposal_accepted",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        summary="A1-accept-secret",
        affects_node_id=decision_a1,
    )
    ev_a2 = _ins_event(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eng_a2,
        source_kind="proposal_accepted",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        summary="A2-accept-secret",
        affects_node_id=decision_a2,
    )
    ev_b = _ins_event(
        postgres_engine,
        tenant_id=tid_b,
        engagement_id=eng_b,
        source_kind="proposal_accepted",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        summary="B-accept-secret",
        affects_node_id=decision_b,
    )
    yield {
        "tenant_a": tid_a,
        "tenant_b": tid_b,
        "eng_a1": eng_a1,
        "eng_a2": eng_a2,
        "eng_b": eng_b,
        "decision_a1": decision_a1,
        "decision_a2": decision_a2,
        "decision_b": decision_b,
        "risk_a1": risk_a1,
        "risk_a2": risk_a2,
        "risk_b": risk_b,
        "ev_a1": ev_a1,
        "ev_a2": ev_a2,
        "ev_b": ev_b,
    }


def _ins_node(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    title: str,
) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, '{}'::jsonb, '{}'::uuid[])"
            ),
            {
                "i": str(nid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "nt": node_type,
                "ti": title,
            },
        )
    return nid


def _ins_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    source_kind: str,
    occurred_at: datetime,
    summary: str,
    affects_node_id: uuid.UUID | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events (id, tenant_id, engagement_id, occurred_at, "
                "actor_kind, actor_id, source_kind, source_ref, summary, detail) "
                "VALUES (:id, :t, :e, :occ, 'user', NULL, :sk, NULL, :sum, CAST(:d AS jsonb))"
            ),
            {
                "id": str(eid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "occ": occurred_at,
                "sk": source_kind,
                "sum": summary,
                "d": json.dumps({}),
            },
        )
        if affects_node_id is not None:
            c.execute(
                text(
                    "INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) VALUES (:e, 'matrix_node', :n)"
                ),
                {"e": str(eid), "n": str(affects_node_id)},
            )
    return eid


def _ins_risk_insight(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    severity: str,
    title: str,
) -> uuid.UUID:
    iid = uuid.uuid4()
    cited = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_insights "
                "(id, tenant_id, engagement_id, agent, insight_type, severity, title, body, "
                " citation_node_ids, citation_edge_ids, citation_event_ids, dedup_key, status, "
                " last_refreshed_at, stale) "
                "VALUES (:i, :t, :e, 'kenny', 'risk', :s, :ti, 'body', '{}'::uuid[], '{}'::uuid[], "
                "        CAST(:ce AS uuid[]), :dk, 'open', now(), false)"
            ),
            {
                "i": str(iid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "s": severity,
                "ti": title,
                "ce": "{" + str(cited) + "}",
                "dk": f"r-{iid}",
            },
        )
    return iid


def _forbidden_ids(fixture: dict[str, uuid.UUID]) -> set[str]:
    return {
        str(fixture["decision_a2"]),
        str(fixture["decision_b"]),
        str(fixture["risk_a2"]),
        str(fixture["risk_b"]),
        str(fixture["ev_a2"]),
        str(fixture["ev_b"]),
    }


def _all_str_ids(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in rows:
        for v in r.values():
            if isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
                out.add(v)
            if isinstance(v, list):
                for vv in v:
                    if isinstance(vv, str) and len(vv) == 36 and vv.count("-") == 4:
                        out.add(vv)
    return out


@pytest.mark.asyncio
async def test_query_ledger_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        # scoped to A1 only
        result = await query_ledger(session, tenant_id=fixture["tenant_a"], engagement_id=fixture["eng_a1"], limit=50)
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden), f"leak in query_ledger: {ids & forbidden}"


@pytest.mark.asyncio
async def test_walk_chain_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    """Asking A1 to walk B's event returns empty — no cross-tenant leak."""
    async for session in get_app_db_session():
        result = await walk_chain(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            event_id=fixture["ev_b"],
        )
        await session.commit()
        assert result.rows == []
        assert result.citations == []


@pytest.mark.asyncio
async def test_get_matrix_node_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    """A1 cannot fetch the sibling engagement's decision node."""
    async for session in get_app_db_session():
        result = await get_matrix_node(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            node_id=fixture["decision_a2"],
        )
        await session.commit()
        assert result.rows == []


@pytest.mark.asyncio
async def test_get_matrix_neighbors_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    async for session in get_app_db_session():
        result = await get_matrix_neighbors(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            node_id=fixture["decision_b"],
        )
        await session.commit()
        assert result.rows == []


@pytest.mark.asyncio
async def test_get_matrix_subgraph_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await get_matrix_subgraph(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            limit=100,
        )
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_read_synthesis_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await read_synthesis(session, tenant_id=fixture["tenant_a"], engagement_id=fixture["eng_a1"])
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_get_decision_history_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await get_decision_history(session, tenant_id=fixture["tenant_a"], engagement_id=fixture["eng_a1"])
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_get_open_risks_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await get_open_risks(session, tenant_id=fixture["tenant_a"], engagement_id=fixture["eng_a1"])
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_get_engagement_summary_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await get_engagement_summary(session, tenant_id=fixture["tenant_a"], engagement_id=fixture["eng_a1"])
        await session.commit()
        # recent_event_ids must not include cross-engagement events.
        recent = set(result.rows[0]["recent_event_ids"])
        assert recent.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_keyword_search_isolated(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    """Search for the bare word ``secret`` (present in every engagement's titles)."""
    forbidden = _forbidden_ids(fixture)
    async for session in get_app_db_session():
        result = await keyword_search(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            query="secret",
            limit=50,
        )
        await session.commit()
        ids = _all_str_ids(result.rows)
        assert ids.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_vector_search_isolated_placeholder(app_session: None, fixture: dict[str, uuid.UUID]) -> None:
    """The placeholder never returns rows — but the scope contract still must hold."""
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            query="anything",
        )
        await session.commit()
        assert result.rows == []


@pytest.mark.asyncio
async def test_propose_action_writes_only_to_scoped_engagement(
    app_session: None, postgres_engine: Engine, fixture: dict[str, uuid.UUID]
) -> None:
    """Issuing propose_action into A1 must not leak rows into A2 / B."""
    async for session in get_app_db_session():
        await propose_action(
            session,
            tenant_id=fixture["tenant_a"],
            engagement_id=fixture["eng_a1"],
            description="A1-only action",
            priority="medium",
        )
        await session.commit()

    with postgres_engine.connect() as c:
        a1 = c.execute(
            text("SELECT count(*) FROM strategist_action_queue_items WHERE engagement_id = :e AND tenant_id = :t"),
            {"e": str(fixture["eng_a1"]), "t": str(fixture["tenant_a"])},
        ).scalar_one()
        a2 = c.execute(
            text("SELECT count(*) FROM strategist_action_queue_items WHERE engagement_id = :e AND tenant_id = :t"),
            {"e": str(fixture["eng_a2"]), "t": str(fixture["tenant_a"])},
        ).scalar_one()
        b = c.execute(
            text("SELECT count(*) FROM strategist_action_queue_items WHERE tenant_id = :t"),
            {"t": str(fixture["tenant_b"])},
        ).scalar_one()
        assert a1 == 1
        assert a2 == 0
        assert b == 0
