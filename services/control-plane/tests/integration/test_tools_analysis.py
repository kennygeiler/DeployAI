"""Integration: ``get_decision_history`` / ``get_open_risks`` / ``get_engagement_summary``."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.analysis import (
    get_decision_history,
    get_engagement_summary,
    get_open_risks,
    list_matrix_nodes_by_type,
)
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
def seeded(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with postgres_engine.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'an-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'an-eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tid)},
        )
    yield {"tenant_id": tid, "engagement_id": eid}


def _ins_node(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    title: str,
    status: str | None = None,
    description: str | None = None,
    evidence_event_ids: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    nid = uuid.uuid4()
    attributes_json = json.dumps({"description": description}) if description else "{}"
    evidence_literal = "{" + ",".join(str(e) for e in evidence_event_ids) + "}" if evidence_event_ids else "{}"
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, status, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, :s, CAST(:a AS jsonb), CAST(:ev AS uuid[]))"
            ),
            {
                "i": str(nid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "nt": node_type,
                "ti": title,
                "s": status,
                "a": attributes_json,
                "ev": evidence_literal,
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
    summary: str = "ev",
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
    cited_event = uuid.uuid4()
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
                "ce": "{" + str(cited_event) + "}",
                "dk": f"r-{iid}",
            },
        )
    return iid


@pytest.mark.asyncio
async def test_get_decision_history_returns_decisions_with_proposal_accepted(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    decision = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d1")
    accept = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="proposal_accepted",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        summary="proposal accepted",
        affects_node_id=decision,
    )
    # Non-decision node is ignored.
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="risk", title="r1")

    async for session in get_app_db_session():
        result = await get_decision_history(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row["id"] == str(decision)
        assert row["accepted_event_id"] == str(accept)


@pytest.mark.asyncio
async def test_get_open_risks_returns_open_risks_only(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    high = _ins_risk_insight(postgres_engine, tenant_id=tid, engagement_id=eid, severity="high", title="h")
    _ins_risk_insight(postgres_engine, tenant_id=tid, engagement_id=eid, severity="low", title="l")

    async for session in get_app_db_session():
        result = await get_open_risks(session, tenant_id=tid, engagement_id=eid, severity="high")
        await session.commit()
        assert [r["id"] for r in result.rows] == [str(high)]


@pytest.mark.asyncio
async def test_get_engagement_summary_aggregates_counts(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d1")
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d2")
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="risk", title="r1")
    _ins_risk_insight(postgres_engine, tenant_id=tid, engagement_id=eid, severity="medium", title="m")
    _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="manual_capture",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        summary="hello",
    )

    async for session in get_app_db_session():
        result = await get_engagement_summary(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row["node_counts_by_type"] == {"decision": 2, "risk": 1}
        assert row["insight_counts_by_type"]["risk"]["open"] == 1
        assert row["total_nodes"] == 3
        assert len(row["recent_event_ids"]) == 1


@pytest.mark.asyncio
async def test_get_engagement_summary_empty_engagement(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await get_engagement_summary(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert result.rows[0]["total_nodes"] == 0
        assert result.rows[0]["total_insights"] == 0
        # ensures helper does not blow up on completely empty data
        _ = timedelta  # appease linter for unused import in case


# ---- Phase 1 follow-up: union risk reads + list_matrix_nodes_by_type -------


@pytest.mark.asyncio
async def test_get_open_risks_returns_node_rows_when_no_insights(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """5 risk nodes seeded, zero insights → 5 rows from the node source."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    node_ids: list[uuid.UUID] = []
    for i in range(5):
        node_ids.append(
            _ins_node(
                postgres_engine,
                tenant_id=tid,
                engagement_id=eid,
                node_type="risk",
                title=f"Raw risk {i}",
                description=f"Detail body for risk {i}",
            )
        )

    async for session in get_app_db_session():
        result = await get_open_risks(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert len(result.rows) == 5
        for row in result.rows:
            assert row["source"] == "node"
            assert row["id"] in {str(nid) for nid in node_ids}
            assert row["title"].startswith("Raw risk")
            assert row["description"].startswith("Detail body")


@pytest.mark.asyncio
async def test_get_open_risks_unions_insights_first_then_nodes(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """3 risk nodes + 2 risk insights → 5 rows, insights ordered first."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    high = _ins_risk_insight(postgres_engine, tenant_id=tid, engagement_id=eid, severity="high", title="h-ins")
    low = _ins_risk_insight(postgres_engine, tenant_id=tid, engagement_id=eid, severity="low", title="l-ins")
    for i in range(3):
        _ins_node(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            node_type="risk",
            title=f"raw-risk-{i}",
            description=f"raw body {i}",
        )

    async for session in get_app_db_session():
        result = await get_open_risks(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert len(result.rows) == 5
        sources = [r["source"] for r in result.rows]
        assert sources[:2] == ["insight", "insight"], sources
        assert sources[2:] == ["node", "node", "node"], sources
        # High severity comes first within the insight bucket.
        assert result.rows[0]["id"] == str(high)
        assert result.rows[1]["id"] == str(low)


@pytest.mark.asyncio
async def test_get_open_risks_citations_include_node_evidence_events(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """Each matrix_node row contributes its evidence_event_ids as citations."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    ev = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="manual_capture",
        occurred_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    _ins_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="risk",
        title="evidence-bearing risk",
        description="see source event",
        evidence_event_ids=[ev],
    )

    async for session in get_app_db_session():
        result = await get_open_risks(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        kinds = {(c.kind, str(c.id)) for c in result.citations}
        assert ("event", str(ev)) in kinds


@pytest.mark.asyncio
async def test_list_matrix_nodes_by_type_stakeholder_only(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """stakeholder filter returns stakeholders only, with description text."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    s1 = _ins_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="stakeholder",
        title="Alice",
        description="Executive sponsor for the deployment.",
    )
    _ins_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="risk",
        title="ignored risk",
    )
    _ins_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="ignored decision",
    )

    async for session in get_app_db_session():
        result = await list_matrix_nodes_by_type(
            session,
            tenant_id=tid,
            engagement_id=eid,
            node_type="stakeholder",
        )
        await session.commit()
        assert len(result.rows) == 1
        assert result.rows[0]["id"] == str(s1)
        assert result.rows[0]["node_type"] == "stakeholder"
        assert "Executive sponsor" in result.rows[0]["description"]


@pytest.mark.asyncio
async def test_list_matrix_nodes_by_type_invalid_type_returns_validation_error(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """Off-catalog node_type with no rows → validation_error surface."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await list_matrix_nodes_by_type(
            session,
            tenant_id=tid,
            engagement_id=eid,
            node_type="not_a_real_type",
        )
        await session.commit()
        assert len(result.rows) == 1
        assert "validation_error" in result.rows[0]
        assert result.detail and "not in the built-in catalog" in result.detail


@pytest.mark.asyncio
async def test_list_matrix_nodes_by_type_honors_limit(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """Seed 15 stakeholder nodes, limit=10 → exactly 10 rows + truncated=True."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    for i in range(15):
        _ins_node(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            node_type="stakeholder",
            title=f"s-{i}",
            description=f"desc-{i}",
        )

    async for session in get_app_db_session():
        result = await list_matrix_nodes_by_type(
            session,
            tenant_id=tid,
            engagement_id=eid,
            node_type="stakeholder",
            limit=10,
        )
        await session.commit()
        # rows is capped at the limit; truncated flag is True.
        assert len(result.rows) == 10
        assert result.truncated is True


@pytest.mark.asyncio
async def test_list_matrix_nodes_by_type_citations_from_evidence_events(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """evidence_event_ids → ``event`` citations on the result."""
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    ev1 = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="manual_capture",
        occurred_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    ev2 = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="manual_capture",
        occurred_at=datetime(2026, 4, 2, tzinfo=UTC),
    )
    n1 = _ins_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="d-with-evidence",
        description="cited",
        evidence_event_ids=[ev1, ev2],
    )

    async for session in get_app_db_session():
        result = await list_matrix_nodes_by_type(
            session,
            tenant_id=tid,
            engagement_id=eid,
            node_type="decision",
        )
        await session.commit()
        kinds = {(c.kind, str(c.id)) for c in result.citations}
        assert ("node", str(n1)) in kinds
        assert ("event", str(ev1)) in kinds
        assert ("event", str(ev2)) in kinds
        assert result.rows[0]["evidence_event_ids"] == [str(ev1), str(ev2)]
