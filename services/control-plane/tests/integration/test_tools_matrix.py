"""Integration: matrix read tools (get_matrix_node / neighbors / subgraph).

The k-hop neighbors path picks AGE Cypher when available and falls back
to a recursive CTE otherwise; the integration tests here run the CTE
fallback because the default ``postgres_engine`` testcontainer does not
ship the AGE binary.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.matrix import (
    get_matrix_neighbors,
    get_matrix_node,
    get_matrix_subgraph,
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
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'mx-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'mx-eng', 'P1_pre_engagement', 'active')"
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
) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, '{}'::jsonb, '{}'::uuid[])"
            ),
            {"i": str(nid), "t": str(tenant_id), "e": str(engagement_id), "nt": node_type, "ti": title},
        )
    return nid


def _ins_edge(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    edge_type: str,
    from_node_id: uuid.UUID,
    to_node_id: uuid.UUID,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_edges "
                "  (id, tenant_id, engagement_id, edge_type, from_node_id, to_node_id, "
                "   attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :et, :f, :to, '{}'::jsonb, '{}'::uuid[])"
            ),
            {
                "i": str(eid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "et": edge_type,
                "f": str(from_node_id),
                "to": str(to_node_id),
            },
        )
    return eid


@pytest.mark.asyncio
async def test_get_matrix_node_returns_node_plus_neighbors(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    decision = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="ad-migrate")
    sponsor = _ins_node(
        postgres_engine, tenant_id=tid, engagement_id=eid, node_type="stakeholder", title="exec-sponsor"
    )
    _ins_edge(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        edge_type="sponsors",
        from_node_id=sponsor,
        to_node_id=decision,
    )

    async for session in get_app_db_session():
        result = await get_matrix_node(
            session, tenant_id=tid, engagement_id=eid, node_id=decision, include_neighbors=True
        )
        await session.commit()
        kinds = [r["kind"] for r in result.rows]
        assert "node" in kinds
        assert "neighbor" in kinds
        assert "edge" in kinds
        # neighbor id must be the sponsor node
        neighbor_ids = [r["id"] for r in result.rows if r["kind"] == "neighbor"]
        assert str(sponsor) in neighbor_ids


@pytest.mark.asyncio
async def test_get_matrix_node_missing_returns_empty(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await get_matrix_node(session, tenant_id=tid, engagement_id=eid, node_id=uuid.uuid4())
        await session.commit()
        assert result.rows == []
        assert result.citations == []


@pytest.mark.asyncio
async def test_get_matrix_neighbors_cte_two_hop(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    root = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="stakeholder", title="root")
    mid = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="mid")
    far = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="risk", title="far")
    _ins_edge(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        edge_type="sponsors",
        from_node_id=root,
        to_node_id=mid,
    )
    _ins_edge(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        edge_type="threatens",
        from_node_id=far,
        to_node_id=mid,
    )

    async for session in get_app_db_session():
        result = await get_matrix_neighbors(session, tenant_id=tid, engagement_id=eid, node_id=root, k=2)
        await session.commit()
        ids = {r["id"] for r in result.rows}
        assert str(mid) in ids
        assert str(far) in ids
        assert str(root) not in ids


@pytest.mark.asyncio
async def test_get_matrix_subgraph_filters_by_node_type(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    d1 = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d1")
    d2 = _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d2")
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="risk", title="r1")

    async for session in get_app_db_session():
        result = await get_matrix_subgraph(session, tenant_id=tid, engagement_id=eid, node_types=["decision"], limit=10)
        await session.commit()
        node_rows = [r for r in result.rows if r["kind"] == "node"]
        ids = {r["id"] for r in node_rows}
        assert ids == {str(d1), str(d2)}


@pytest.mark.asyncio
async def test_get_matrix_subgraph_respects_since_filter(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    _ins_node(postgres_engine, tenant_id=tid, engagement_id=eid, node_type="decision", title="d1")
    # ``since`` set far in the future filters everything out.
    far_future = datetime(2099, 1, 1, tzinfo=UTC)

    async for session in get_app_db_session():
        result = await get_matrix_subgraph(session, tenant_id=tid, engagement_id=eid, since=far_future)
        await session.commit()
        assert [r for r in result.rows if r["kind"] == "node"] == []
