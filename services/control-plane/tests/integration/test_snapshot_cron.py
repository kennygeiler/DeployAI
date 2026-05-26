"""Integration: nightly matrix snapshot writer + backfill (Phase F3.a)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.domain.matrix_snapshot import MatrixSnapshot
from control_plane.snapshots.cron import backfill_snapshots, write_daily_snapshots

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


def _seed_tenant(eng: Engine, label: str = "snapshot-cron") -> uuid.UUID:
    tid = uuid.uuid4()
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"),
            {"t": str(tid), "n": label},
        )
    return tid


def _seed_engagement(
    eng: Engine,
    tenant_id: uuid.UUID,
    *,
    status: str = "active",
    name: str = "engagement",
) -> uuid.UUID:
    eid = uuid.uuid4()
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, status, current_phase) "
                "VALUES (:e, :t, :n, :s, 'P1_pre_engagement')"
            ),
            {"e": str(eid), "t": str(tenant_id), "n": name, "s": status},
        )
    return eid


def _seed_node(eng: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID, title: str) -> uuid.UUID:
    nid = uuid.uuid4()
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes (id, tenant_id, engagement_id, node_type, title) "
                "VALUES (:n, :t, :e, 'stakeholder', :ti)"
            ),
            {"n": str(nid), "t": str(tenant_id), "e": str(engagement_id), "ti": title},
        )
    return nid


def _seed_edge(
    eng: Engine,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
) -> None:
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_edges (id, tenant_id, engagement_id, edge_type, from_node_id, to_node_id) "
                "VALUES (gen_random_uuid(), :t, :e, 'depends_on', :f, :to_)"
            ),
            {"t": str(tenant_id), "e": str(engagement_id), "f": str(from_id), "to_": str(to_id)},
        )


@pytest.mark.asyncio
async def test_cron_writes_one_snapshot_per_active_engagement(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    e1 = _seed_engagement(postgres_engine, tid, name="active-1")
    e2 = _seed_engagement(postgres_engine, tid, name="active-2")
    _seed_engagement(postgres_engine, tid, status="closed", name="closed")

    n1 = _seed_node(postgres_engine, tid, e1, "Alice")
    n2 = _seed_node(postgres_engine, tid, e1, "Bob")
    _seed_edge(postgres_engine, tid, e1, n1, n2)
    _seed_node(postgres_engine, tid, e2, "Solo")

    async with session_factory() as s:
        written = await write_daily_snapshots(s, tenant_id=tid)
        await s.commit()
    assert written == 2

    async with session_factory() as s:
        rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.tenant_id == tid))).scalars().all()
    assert len(rows) == 2
    by_engagement = {r.engagement_id: r for r in rows}
    assert by_engagement[e1].node_count == 2
    assert by_engagement[e1].edge_count == 1
    assert by_engagement[e2].node_count == 1
    assert by_engagement[e2].edge_count == 0


@pytest.mark.asyncio
async def test_cron_is_idempotent_within_utc_day(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    _seed_node(postgres_engine, tid, eid, "x")

    now = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    later_same_day = datetime(2026, 6, 15, 23, 59, tzinfo=UTC)

    async with session_factory() as s:
        first = await write_daily_snapshots(s, tenant_id=tid, now=now)
        await s.commit()
    async with session_factory() as s:
        second = await write_daily_snapshots(s, tenant_id=tid, now=later_same_day)
        await s.commit()

    assert first == 1
    assert second == 0

    async with session_factory() as s:
        rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.tenant_id == tid))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_backfill_creates_n_daily_rows_when_gap_detected(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    _seed_node(postgres_engine, tid, eid, "x")

    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    async with session_factory() as s:
        written = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=5, now=now)
        await s.commit()
    assert written == 5

    async with session_factory() as s:
        rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.engagement_id == eid))).scalars().all()
    assert len(rows) == 5
    captured_days = sorted({r.captured_at.date() for r in rows})
    expected_days = sorted(
        (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=d)).date() for d in range(5)
    )
    assert captured_days == expected_days

    async with session_factory() as s:
        again = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=5, now=now)
        await s.commit()
    assert again == 0


@pytest.mark.asyncio
async def test_rebuild_replaces_existing_rows(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine, label="rebuild-target")
    other_tid = _seed_tenant(postgres_engine, label="rebuild-other-tenant")
    eid = _seed_engagement(postgres_engine, tid)
    other_eid_same_tenant = _seed_engagement(postgres_engine, tid, name="other-engagement")
    other_tenant_eid = _seed_engagement(postgres_engine, other_tid, name="other-tenant-engagement")
    n1 = _seed_node(postgres_engine, tid, eid, "alpha")
    _seed_node(postgres_engine, tid, other_eid_same_tenant, "sibling")
    _seed_node(postgres_engine, other_tid, other_tenant_eid, "outside")

    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

    async with session_factory() as s:
        first = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=5, now=now)
        await s.commit()
    assert first == 5

    async with session_factory() as s:
        sibling = await backfill_snapshots(s, tenant_id=tid, engagement_id=other_eid_same_tenant, days=5, now=now)
        await s.commit()
    assert sibling == 5

    async with session_factory() as s:
        outside = await backfill_snapshots(s, tenant_id=other_tid, engagement_id=other_tenant_eid, days=5, now=now)
        await s.commit()
    assert outside == 5

    # Out-of-window row (8 days back, well beyond the 5-day rebuild window).
    out_of_window = (now - timedelta(days=8)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Boundary row at exactly `now - days` days back — the loop only fills
    # offset=0..days-1 so the oldest filled day is `now - (days-1)`. The DELETE
    # must NOT collateral-delete a row at exactly `now - days`.
    boundary_out = (now - timedelta(days=5)).replace(hour=0, minute=0, second=0, microsecond=0)
    with postgres_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_snapshots "
                "(id, tenant_id, engagement_id, captured_at, nodes, edges, node_count, edge_count) "
                "VALUES (gen_random_uuid(), :t, :e, :ca, '[]'::jsonb, '[]'::jsonb, 0, 0)"
            ),
            {"t": str(tid), "e": str(eid), "ca": out_of_window.isoformat()},
        )
        c.execute(
            text(
                "INSERT INTO matrix_snapshots "
                "(id, tenant_id, engagement_id, captured_at, nodes, edges, node_count, edge_count) "
                "VALUES (gen_random_uuid(), :t, :e, :ca, '[]'::jsonb, '[]'::jsonb, 0, 0)"
            ),
            {"t": str(tid), "e": str(eid), "ca": boundary_out.isoformat()},
        )

    n2 = _seed_node(postgres_engine, tid, eid, "beta")
    _seed_edge(postgres_engine, tid, eid, n1, n2)

    async with session_factory() as s:
        rebuilt = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=5, rebuild=True, now=now)
        await s.commit()
    assert rebuilt == 5

    async with session_factory() as s:
        target_rows = (
            (
                await s.execute(
                    select(MatrixSnapshot)
                    .where(MatrixSnapshot.engagement_id == eid)
                    .order_by(MatrixSnapshot.captured_at)
                )
            )
            .scalars()
            .all()
        )
    assert len(target_rows) == 7  # 5 rebuilt + 1 boundary + 1 out-of-window
    in_window = [
        r
        for r in target_rows
        if r.captured_at >= now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=4)
    ]
    assert len(in_window) == 5
    assert all(r.node_count == 2 and r.edge_count == 1 for r in in_window)
    out_rows = [r for r in target_rows if r.captured_at == out_of_window]
    assert len(out_rows) == 1
    assert out_rows[0].node_count == 0
    boundary_rows = [r for r in target_rows if r.captured_at == boundary_out]
    assert len(boundary_rows) == 1
    assert boundary_rows[0].node_count == 0

    async with session_factory() as s:
        sibling_rows = (
            (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.engagement_id == other_eid_same_tenant)))
            .scalars()
            .all()
        )
        outside_rows = (
            (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.engagement_id == other_tenant_eid)))
            .scalars()
            .all()
        )
    assert len(sibling_rows) == 5
    assert all(r.node_count == 1 for r in sibling_rows)
    assert len(outside_rows) == 5
    assert all(r.node_count == 1 for r in outside_rows)


@pytest.mark.asyncio
async def test_backfill_without_rebuild_remains_idempotent(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine, label="no-rebuild")
    eid = _seed_engagement(postgres_engine, tid)
    _seed_node(postgres_engine, tid, eid, "alpha")

    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    async with session_factory() as s:
        first = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=3, now=now)
        await s.commit()
    assert first == 3

    _seed_node(postgres_engine, tid, eid, "beta")

    async with session_factory() as s:
        second = await backfill_snapshots(s, tenant_id=tid, engagement_id=eid, days=3, now=now)
        await s.commit()
    assert second == 0

    async with session_factory() as s:
        rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.engagement_id == eid))).scalars().all()
    assert len(rows) == 3
    assert all(r.node_count == 1 for r in rows)


@pytest.mark.asyncio
async def test_cron_tenant_isolation(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid_a = _seed_tenant(postgres_engine, label="tenant-a")
    tid_b = _seed_tenant(postgres_engine, label="tenant-b")
    eid_a = _seed_engagement(postgres_engine, tid_a, name="a-engagement")
    eid_b = _seed_engagement(postgres_engine, tid_b, name="b-engagement")
    _seed_node(postgres_engine, tid_a, eid_a, "a-node")
    _seed_node(postgres_engine, tid_b, eid_b, "b-node")

    async with session_factory() as s:
        written_a = await write_daily_snapshots(s, tenant_id=tid_a)
        await s.commit()
    assert written_a == 1

    async with session_factory() as s:
        a_rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.tenant_id == tid_a))).scalars().all()
        b_rows = (await s.execute(select(MatrixSnapshot).where(MatrixSnapshot.tenant_id == tid_b))).scalars().all()
    assert len(a_rows) == 1
    assert a_rows[0].engagement_id == eid_a
    assert b_rows == []
