"""Integration: POST /internal/v1/admin/seed-scenarios/bluestate-xl.

Workhorse fixture for Agent Kenny v2 testing. Production runs the full
1825-day snapshot backfill; CI overrides to 365 days so the integration
suite stays under the 90s budget.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.scenarios.bluestate import ENGAGEMENT_ID as BLUESTATE_ENGAGEMENT_ID
from control_plane.scenarios.bluestate_xl import (
    ENGAGEMENT_ID as BLUESTATE_XL_ENGAGEMENT_ID,
)
from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "seed-scenarios-xl-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=180.0)
    client.headers["X-DeployAI-Internal-Key"] = "seed-scenarios-xl-test-key"
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


def _approx(actual: int, target: int, tolerance: float = 0.10) -> bool:
    if target <= 0:
        return actual >= 0
    return abs(actual - target) <= max(int(target * tolerance), 5)


@pytest.mark.asyncio
async def test_bluestate_xl_fresh_seed_meets_volume_targets(db_session, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    summary = await apply_bluestate_xl_scenario(
        db_session,
        tenant_id=tid,
        days=365,
    )
    await db_session.commit()

    assert str(summary.engagement_id) == BLUESTATE_XL_ENGAGEMENT_ID

    assert _approx(summary.stakeholder_node_count, 70), summary.stakeholder_node_count
    assert _approx(summary.decision_node_count, 200), summary.decision_node_count
    assert _approx(summary.risk_count, 130), summary.risk_count
    assert _approx(summary.narrative_event_count, 2500), summary.narrative_event_count
    assert _approx(summary.matrix_edge_count, 600), summary.matrix_edge_count
    assert summary.snapshot_count == 365

    with postgres_engine.begin() as conn:
        engagement = conn.execute(
            text("SELECT id, tenant_id FROM engagements WHERE id = CAST(:eid AS uuid)"),
            {"eid": BLUESTATE_XL_ENGAGEMENT_ID},
        ).first()
        assert engagement is not None
        assert str(engagement.tenant_id) == str(tid)


@pytest.mark.asyncio
async def test_bluestate_xl_route_409_when_already_seeded(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    first = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate-xl?tenant_id={tid}",
        json={"force": False},
    )
    assert first.status_code == 200, first.text

    second = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate-xl?tenant_id={tid}",
        json={"force": False},
    )
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["error"] == "already_seeded"
    assert detail["engagement_id"] == BLUESTATE_XL_ENGAGEMENT_ID


@pytest.mark.asyncio
async def test_bluestate_xl_force_reseed_idempotent(db_session) -> None:
    tid = uuid.uuid4()
    first = await apply_bluestate_xl_scenario(db_session, tenant_id=tid, days=30)
    await db_session.commit()

    second = await apply_bluestate_xl_scenario(db_session, tenant_id=tid, days=30)
    await db_session.commit()

    assert str(second.engagement_id) == BLUESTATE_XL_ENGAGEMENT_ID
    assert second.stakeholder_node_count == first.stakeholder_node_count
    assert second.decision_node_count == first.decision_node_count
    assert second.risk_count == first.risk_count
    assert second.matrix_edge_count == first.matrix_edge_count


@pytest.mark.asyncio
async def test_bluestate_xl_isolated_from_small_bluestate(db_session, postgres_engine: Engine) -> None:
    from control_plane.scenarios.bluestate.runner import apply_bluestate_scenario

    tid = uuid.uuid4()
    small = await apply_bluestate_scenario(
        db_session,
        tenant_id=tid,
        skip_snapshots=True,
        skip_analyzers=True,
    )
    await db_session.commit()

    xl = await apply_bluestate_xl_scenario(
        db_session,
        tenant_id=tid,
        days=30,
    )
    await db_session.commit()

    assert str(small.engagement_id) == BLUESTATE_ENGAGEMENT_ID
    assert str(xl.engagement_id) == BLUESTATE_XL_ENGAGEMENT_ID

    with postgres_engine.begin() as conn:
        small_ledger_in_xl = conn.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE engagement_id = CAST(:xl_eid AS uuid) "
                "AND tenant_id = CAST(:tid AS uuid) "
                "AND id IN (SELECT id FROM ledger_events WHERE engagement_id = CAST(:small_eid AS uuid))"
            ),
            {
                "xl_eid": BLUESTATE_XL_ENGAGEMENT_ID,
                "small_eid": BLUESTATE_ENGAGEMENT_ID,
                "tid": str(tid),
            },
        ).scalar()
        assert (small_ledger_in_xl or 0) == 0

        xl_nodes_under_small = conn.execute(
            text(
                "SELECT count(*) FROM matrix_nodes "
                "WHERE engagement_id = CAST(:small_eid AS uuid) AND tenant_id = CAST(:tid AS uuid) "
                "AND id IN (SELECT id FROM matrix_nodes WHERE engagement_id = CAST(:xl_eid AS uuid))"
            ),
            {
                "xl_eid": BLUESTATE_XL_ENGAGEMENT_ID,
                "small_eid": BLUESTATE_ENGAGEMENT_ID,
                "tid": str(tid),
            },
        ).scalar()
        assert (xl_nodes_under_small or 0) == 0
