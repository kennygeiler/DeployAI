"""Integration: ``read_synthesis`` tool.

Seeds a Kenny-authored ``matrix_insights`` row alongside an Oracle row and
asserts that the default ``agent='kenny'`` filter returns only Kenny's
data with the right citation set.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

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
def seeded(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with postgres_engine.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'syn-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'syn-eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tid)},
        )
    yield {"tenant_id": tid, "engagement_id": eid}


def _ins_insight(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    agent: str,
    insight_type: str = "decision_provenance_summary",
    severity: str = "medium",
    title: str = "x",
    body: str = "body",
    citation_event_ids: list[uuid.UUID] | None = None,
    citation_node_ids: list[uuid.UUID] | None = None,
    dedup_key: str | None = None,
) -> uuid.UUID:
    iid = uuid.uuid4()
    citation_event_ids = citation_event_ids or [uuid.uuid4()]
    citation_node_ids = citation_node_ids or []
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_insights "
                "(id, tenant_id, engagement_id, agent, insight_type, severity, title, body, "
                " citation_node_ids, citation_edge_ids, citation_event_ids, dedup_key, status, "
                " last_refreshed_at, stale) "
                "VALUES (:i, :t, :e, :a, :it, :s, :ti, :b, "
                "  CAST(:cn AS uuid[]), '{}'::uuid[], CAST(:ce AS uuid[]), :dk, 'open', now(), false)"
            ),
            {
                "i": str(iid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "a": agent,
                "it": insight_type,
                "s": severity,
                "ti": title,
                "b": body,
                "cn": "{" + ",".join(str(n) for n in citation_node_ids) + "}",
                "ce": "{" + ",".join(str(n) for n in citation_event_ids) + "}",
                "dk": dedup_key or f"k-{iid}",
            },
        )
    return iid


@pytest.mark.asyncio
async def test_read_synthesis_returns_kenny_rows_only(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    kenny = _ins_insight(postgres_engine, tenant_id=tid, engagement_id=eid, agent="kenny", title="k")
    _ins_insight(postgres_engine, tenant_id=tid, engagement_id=eid, agent="oracle", title="o")

    async for session in get_app_db_session():
        result = await read_synthesis(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert [r["id"] for r in result.rows] == [str(kenny)]
        # Citations include the insight row itself plus the event it cites.
        kinds = {c.kind for c in result.citations}
        assert "insight" in kinds
        assert "event" in kinds


@pytest.mark.asyncio
async def test_read_synthesis_filters_by_node_id(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    target_node = uuid.uuid4()
    target = _ins_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        agent="kenny",
        citation_node_ids=[target_node],
        title="target",
    )
    _ins_insight(postgres_engine, tenant_id=tid, engagement_id=eid, agent="kenny", title="other")

    async for session in get_app_db_session():
        result = await read_synthesis(session, tenant_id=tid, engagement_id=eid, node_id=target_node)
        await session.commit()
        assert [r["id"] for r in result.rows] == [str(target)]


@pytest.mark.asyncio
async def test_read_synthesis_excludes_stale_by_default(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    fresh = _ins_insight(postgres_engine, tenant_id=tid, engagement_id=eid, agent="kenny", title="fresh")
    stale = _ins_insight(postgres_engine, tenant_id=tid, engagement_id=eid, agent="kenny", title="stale")
    with postgres_engine.begin() as c:
        c.execute(text("UPDATE matrix_insights SET stale = true WHERE id = :i"), {"i": str(stale)})

    async for session in get_app_db_session():
        result = await read_synthesis(session, tenant_id=tid, engagement_id=eid)
        await session.commit()
        assert [r["id"] for r in result.rows] == [str(fresh)]
