"""Integration: ledger causal-chain route (Phase F2.a)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.domain.base import Base
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects, LedgerEventCause
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest.fixture(autouse=True)
def _ensure_ledger_tables(postgres_engine: Engine) -> Generator[None]:
    tables = [
        Base.metadata.tables[LedgerEvent.__tablename__],
        Base.metadata.tables[LedgerEventCause.__tablename__],
        Base.metadata.tables[LedgerEventAffects.__tablename__],
    ]
    Base.metadata.create_all(postgres_engine, tables=tables, checkfirst=True)
    with postgres_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_event_causes, ledger_event_affects, ledger_events CASCADE"))
    yield
    with postgres_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_event_causes, ledger_event_affects, ledger_events CASCADE"))


@pytest_asyncio.fixture
async def chain_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "chain-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "chain-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'chain-test')"), {"t": str(tid)})
    return tid


def _seed_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id)},
        )
    return eid


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    source_kind: str = "audit_other",
    actor_kind: str = "user",
    actor_id: str | None = None,
    summary: str = "ev",
    detail: dict[str, object] | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ledger_events
                  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id,
                   source_kind, source_ref, summary, detail)
                VALUES
                  (:id, :tid, :eid, :occ, :ak, :aid, :sk, NULL, :sum, CAST(:d AS jsonb))
                """
            ),
            {
                "id": str(eid),
                "tid": str(tenant_id),
                "eid": str(engagement_id) if engagement_id is not None else None,
                "occ": occurred_at,
                "ak": actor_kind,
                "aid": actor_id,
                "sk": source_kind,
                "sum": summary,
                "d": json.dumps(detail or {}),
            },
        )
    return eid


def _link_cause(engine: Engine, *, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :c)"),
            {"e": str(event_id), "c": str(caused_by_id)},
        )


@pytest.mark.asyncio
async def test_single_node_chain_returns_just_root(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    ev = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        summary="lonely",
    )
    r = await chain_client.get(f"/internal/v1/engagements/{eid}/ledger/{ev}/chain?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["root_event_id"] == str(ev)
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == str(ev)
    assert body["nodes"][0]["depth"] == 0
    assert body["nodes"][0]["truncated"] is False
    assert body["edges"] == []
    assert body["truncated_at_depth"] is None
    assert body["truncated_node_count"] is None


@pytest.mark.asyncio
async def test_multi_level_upstream_walk(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    a = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base, summary="a")
    b = _seed_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=1), summary="b"
    )
    c = _seed_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=2), summary="c"
    )
    d = _seed_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=3), summary="d"
    )
    _link_cause(postgres_engine, event_id=b, caused_by_id=a)
    _link_cause(postgres_engine, event_id=c, caused_by_id=b)
    _link_cause(postgres_engine, event_id=d, caused_by_id=c)

    r = await chain_client.get(
        f"/internal/v1/engagements/{eid}/ledger/{d}/chain?tenant_id={tid}&direction=upstream&max_depth=3"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids_by_depth = {n["depth"]: n["id"] for n in body["nodes"]}
    assert ids_by_depth == {0: str(d), 1: str(c), 2: str(b), 3: str(a)}
    edge_pairs = {(e["from_event_id"], e["to_event_id"]) for e in body["edges"]}
    assert edge_pairs == {(str(d), str(c)), (str(c), str(b)), (str(b), str(a))}
    assert body["truncated_at_depth"] is None
    assert body["truncated_node_count"] is None


@pytest.mark.asyncio
async def test_cycle_returns_finite_nodes(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    a = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base, summary="a")
    b = _seed_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=1), summary="b"
    )
    c = _seed_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=2), summary="c"
    )
    _link_cause(postgres_engine, event_id=b, caused_by_id=a)
    _link_cause(postgres_engine, event_id=c, caused_by_id=b)
    _link_cause(postgres_engine, event_id=a, caused_by_id=c)

    r = await chain_client.get(
        f"/internal/v1/engagements/{eid}/ledger/{a}/chain?tenant_id={tid}&direction=both&max_depth=10"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert node_ids == {str(a), str(b), str(c)}


@pytest.mark.asyncio
async def test_cross_tenant_event_returns_404_no_leakage(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eng_a = _seed_engagement(postgres_engine, tid_a)
    eng_b = _seed_engagement(postgres_engine, tid_b)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    ev_a = _seed_event(postgres_engine, tenant_id=tid_a, engagement_id=eng_a, occurred_at=base, summary="a")
    _seed_event(
        postgres_engine, tenant_id=tid_b, engagement_id=eng_b, occurred_at=base + timedelta(minutes=1), summary="b"
    )

    # Tenant B asking for tenant A's event: 404, no leakage.
    r = await chain_client.get(f"/internal/v1/engagements/{eng_a}/ledger/{ev_a}/chain?tenant_id={tid_b}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_neighbor_excluded(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    """Even if a caused_by edge bridges tenants (hypothetical), neighbor of other tenant MUST NOT appear."""
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eng_a = _seed_engagement(postgres_engine, tid_a)
    eng_b = _seed_engagement(postgres_engine, tid_b)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    root = _seed_event(postgres_engine, tenant_id=tid_a, engagement_id=eng_a, occurred_at=base, summary="root")
    intruder = _seed_event(
        postgres_engine, tenant_id=tid_b, engagement_id=eng_b, occurred_at=base + timedelta(minutes=1), summary="intr"
    )
    _link_cause(postgres_engine, event_id=root, caused_by_id=intruder)

    r = await chain_client.get(f"/internal/v1/engagements/{eng_a}/ledger/{root}/chain?tenant_id={tid_a}")
    assert r.status_code == 200, r.text
    body = r.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert str(intruder) not in node_ids
    assert node_ids == {str(root)}


@pytest.mark.asyncio
async def test_max_depth_cap_populates_truncated_at_depth(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    prev: uuid.UUID | None = None
    chain_ids: list[uuid.UUID] = []
    for i in range(6):
        cur = _seed_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i),
            summary=f"n{i}",
        )
        chain_ids.append(cur)
        if prev is not None:
            _link_cause(postgres_engine, event_id=prev, caused_by_id=cur)
        prev = cur

    root_id = chain_ids[0]
    r = await chain_client.get(
        f"/internal/v1/engagements/{eid}/ledger/{root_id}/chain?tenant_id={tid}&direction=upstream&max_depth=2"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    depths = {n["id"]: n["depth"] for n in body["nodes"]}
    assert max(depths.values()) == 2
    assert body["truncated_at_depth"] == 2
    truncated_nodes = [n for n in body["nodes"] if n["truncated"]]
    assert any(n["depth"] == 2 for n in truncated_nodes)


@pytest.mark.asyncio
async def test_max_nodes_cap_populates_truncated_node_count(chain_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    root = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base, summary="root")
    for i in range(8):
        leaf = _seed_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i + 1),
            summary=f"leaf-{i}",
        )
        _link_cause(postgres_engine, event_id=root, caused_by_id=leaf)

    r = await chain_client.get(
        f"/internal/v1/engagements/{eid}/ledger/{root}/chain?tenant_id={tid}&direction=upstream&max_nodes=4"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["nodes"]) == 4
    assert body["truncated_node_count"] == 5
