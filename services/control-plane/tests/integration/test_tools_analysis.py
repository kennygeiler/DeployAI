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
) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, status, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, :s, '{}'::jsonb, '{}'::uuid[])"
            ),
            {
                "i": str(nid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "nt": node_type,
                "ti": title,
                "s": status,
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
