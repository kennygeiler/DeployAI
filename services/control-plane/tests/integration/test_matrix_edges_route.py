"""Matrix edge route (integration) — verify dual-emit + tenant isolation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.db import clear_engine_cache
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def session_factory(
    postgres_engine: Engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng: AsyncEngine = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "edge-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "edge-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine, label: str = "edges") -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"),
            {"t": str(tid), "n": label},
        )
    return tid


async def _new_engagement_for(client: AsyncClient, tenant_id: uuid.UUID, name: str = "edges") -> str:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tenant_id}", json={"name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _make_node(
    client: AsyncClient, tenant_id: uuid.UUID, engagement_id: str, *, node_type: str, title: str
) -> uuid.UUID:
    r = await client.post(
        f"/internal/v1/engagements/{engagement_id}/matrix/nodes?tenant_id={tenant_id}",
        json={"node_type": node_type, "title": title},
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def _ledger_rows(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> list[LedgerEvent]:
    async with factory() as session:
        r = await session.execute(
            select(LedgerEvent).where(LedgerEvent.tenant_id == tenant_id).order_by(LedgerEvent.recorded_at)
        )
        return list(r.scalars().all())


async def _affects_for(factory: async_sessionmaker[AsyncSession], event_id: uuid.UUID) -> list[LedgerEventAffects]:
    async with factory() as session:
        r = await session.execute(select(LedgerEventAffects).where(LedgerEventAffects.event_id == event_id))
        return list(r.scalars().all())


@pytest.mark.asyncio
async def test_create_matrix_edge_dual_emits_with_affects(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement_for(e_client, tid)
    risk_id = await _make_node(e_client, tid, eid, node_type="risk", title="Calibration slip")
    system_id = await _make_node(e_client, tid, eid, node_type="system", title="LiDAR ingest")

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "threatens", "from_node_id": str(risk_id), "to_node_id": str(system_id)},
    )
    assert created.status_code == 201, created.text
    edge_id = uuid.UUID(created.json()["id"])

    rows = await _ledger_rows(session_factory, tid)
    edge_create_rows = [r for r in rows if r.source_kind == "matrix_edge_created"]
    assert len(edge_create_rows) == 1
    row = edge_create_rows[0]
    assert row.engagement_id == uuid.UUID(eid)
    assert row.actor_kind == "user"
    assert row.source_ref == edge_id
    assert row.detail.get("edge_type") == "threatens"
    assert row.detail.get("from_node_id") == str(risk_id)
    assert row.detail.get("to_node_id") == str(system_id)

    affects = await _affects_for(session_factory, row.id)
    assert [(a.entity_kind, a.entity_id) for a in affects] == [("matrix_edge", edge_id)]


@pytest.mark.asyncio
async def test_delete_matrix_edge_dual_emits(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement_for(e_client, tid)
    a_id = await _make_node(e_client, tid, eid, node_type="system", title="A")
    b_id = await _make_node(e_client, tid, eid, node_type="system", title="B")

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "depends_on", "from_node_id": str(a_id), "to_node_id": str(b_id)},
    )
    assert created.status_code == 201
    edge_id = uuid.UUID(created.json()["id"])

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/edges/{edge_id}?tenant_id={tid}")
    assert deleted.status_code == 204

    rows = await _ledger_rows(session_factory, tid)
    del_rows = [r for r in rows if r.source_kind == "matrix_edge_deleted"]
    assert len(del_rows) == 1
    del_row = del_rows[0]
    assert del_row.engagement_id == uuid.UUID(eid)
    assert del_row.actor_kind == "user"
    assert del_row.source_ref == edge_id
    assert del_row.detail.get("edge_type") == "depends_on"

    del_affects = await _affects_for(session_factory, del_row.id)
    assert [(a.entity_kind, a.entity_id) for a in del_affects] == [("matrix_edge", edge_id)]


@pytest.mark.asyncio
async def test_create_matrix_edge_invalid_type_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement_for(e_client, tid)
    a_id = await _make_node(e_client, tid, eid, node_type="system", title="A")
    b_id = await _make_node(e_client, tid, eid, node_type="system", title="B")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "gremlin", "from_node_id": str(a_id), "to_node_id": str(b_id)},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_matrix_edge_cross_engagement_node_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """from_node_id/to_node_id must belong to the same engagement."""
    tid = _seed_tenant(postgres_engine)
    eid_a = await _new_engagement_for(e_client, tid, name="A")
    eid_b = await _new_engagement_for(e_client, tid, name="B")
    node_in_a = await _make_node(e_client, tid, eid_a, node_type="system", title="alpha")
    node_in_b = await _make_node(e_client, tid, eid_b, node_type="system", title="beta")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid_a}/matrix/edges?tenant_id={tid}",
        json={
            "edge_type": "depends_on",
            "from_node_id": str(node_in_a),
            "to_node_id": str(node_in_b),
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sibling_tenant_cannot_see_or_delete_edge(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """An edge created under tenant A is not addressable from tenant B."""
    tid_a = _seed_tenant(postgres_engine, label="edges-a")
    tid_b = _seed_tenant(postgres_engine, label="edges-b")
    eid = await _new_engagement_for(e_client, tid_a)
    src = await _make_node(e_client, tid_a, eid, node_type="system", title="src")
    dst = await _make_node(e_client, tid_a, eid, node_type="system", title="dst")

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid_a}",
        json={"edge_type": "depends_on", "from_node_id": str(src), "to_node_id": str(dst)},
    )
    assert created.status_code == 201
    edge_id = uuid.UUID(created.json()["id"])

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid_b}")
    assert listed.status_code == 404

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/edges/{edge_id}?tenant_id={tid_b}")
    assert deleted.status_code == 404


@pytest.mark.asyncio
async def test_sibling_tenant_create_under_other_engagement_404(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """POST to an engagement that does not exist for the caller's tenant returns 404."""
    tid_a = _seed_tenant(postgres_engine, label="edges-a2")
    tid_b = _seed_tenant(postgres_engine, label="edges-b2")
    eid = await _new_engagement_for(e_client, tid_a)
    src = await _make_node(e_client, tid_a, eid, node_type="system", title="src")
    dst = await _make_node(e_client, tid_a, eid, node_type="system", title="dst")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid_b}",
        json={"edge_type": "depends_on", "from_node_id": str(src), "to_node_id": str(dst)},
    )
    assert r.status_code == 404
