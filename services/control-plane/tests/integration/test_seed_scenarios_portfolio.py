"""Integration: POST /internal/v1/admin/seed-scenarios/portfolio.

DeployAI Portfolio fixture - 5 sibling engagements x 26 weeks under one
tenant. Primary purpose: cross-engagement isolation tests for Agent Kenny.
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
from control_plane.scenarios.portfolio import (
    PORTFOLIO_ENGAGEMENT_IDS,
    PORTFOLIO_ENGAGEMENTS,
)

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "seed-scenarios-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=180.0)
    client.headers["X-DeployAI-Internal-Key"] = "seed-scenarios-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_portfolio_fresh_seed_populates_all_five_engagements(
    s_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = uuid.uuid4()
    r = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "cp"
    summary = body["summary"]
    assert summary["engagement_count"] == 5
    seeded_ids = {row["engagement_id"] for row in summary["engagements"]}
    assert seeded_ids == set(PORTFOLIO_ENGAGEMENT_IDS)

    for row in summary["engagements"]:
        # Surviving stakeholders after departures (~9-13), ~25 decisions, ~15 risks.
        assert 8 <= row["stakeholder_nodes"] <= 14, row
        assert 22 <= row["decision_nodes"] <= 28, row
        assert 12 <= row["risks"] <= 18, row

    with postgres_engine.begin() as conn:
        for eid in PORTFOLIO_ENGAGEMENT_IDS:
            engagement = conn.execute(
                text("SELECT id, tenant_id FROM engagements WHERE id = CAST(:eid AS uuid)"),
                {"eid": eid},
            ).first()
            assert engagement is not None, eid
            assert str(engagement.tenant_id) == str(tid)

            ledger_count = conn.execute(
                text(
                    "SELECT count(*) FROM ledger_events "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"eid": eid, "tid": str(tid)},
            ).scalar()
            assert (ledger_count or 0) >= 200, (eid, ledger_count)

            edge_count = conn.execute(
                text(
                    "SELECT count(*) FROM matrix_edges "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"eid": eid, "tid": str(tid)},
            ).scalar()
            assert (edge_count or 0) >= 40, (eid, edge_count)


@pytest.mark.asyncio
async def test_portfolio_cross_engagement_isolation(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    r = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": False},
    )
    assert r.status_code == 200, r.text

    northwind_id = PORTFOLIO_ENGAGEMENTS[0].engagement_id
    acme_id = PORTFOLIO_ENGAGEMENTS[1].engagement_id

    with postgres_engine.begin() as conn:
        northwind_node = conn.execute(
            text(
                "SELECT id FROM matrix_nodes "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid) "
                "AND node_type = 'stakeholder' LIMIT 1"
            ),
            {"eid": northwind_id, "tid": str(tid)},
        ).first()
        assert northwind_node is not None

        leaked = conn.execute(
            text(
                "SELECT count(*) FROM matrix_nodes WHERE id = CAST(:nid AS uuid) AND engagement_id = CAST(:eid AS uuid)"
            ),
            {"nid": str(northwind_node.id), "eid": acme_id},
        ).scalar()
        assert (leaked or 0) == 0, "Northwind node leaked into Acme engagement scope"

        northwind_acme_overlap = conn.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid) "
                "AND (summary ILIKE '%Acme Financial%' OR summary ILIKE '%Beacon Healthcare%' "
                "OR summary ILIKE '%Greenfield Energy%' OR summary ILIKE '%Polaris Public%')"
            ),
            {"eid": northwind_id, "tid": str(tid)},
        ).scalar()
        assert (northwind_acme_overlap or 0) == 0, "Northwind ledger references sibling engagement names"

        beacon_id = PORTFOLIO_ENGAGEMENTS[3].engagement_id
        other_tid = uuid.uuid4()
        for eid in (northwind_id, beacon_id):
            wrong_tenant_count = conn.execute(
                text(
                    "SELECT count(*) FROM matrix_nodes "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"eid": eid, "tid": str(other_tid)},
            ).scalar()
            assert (wrong_tenant_count or 0) == 0, (eid, other_tid)

            wrong_tenant_edges = conn.execute(
                text(
                    "SELECT count(*) FROM matrix_edges "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"eid": eid, "tid": str(other_tid)},
            ).scalar()
            assert (wrong_tenant_edges or 0) == 0, (eid, other_tid)

            wrong_tenant_events = conn.execute(
                text(
                    "SELECT count(*) FROM ledger_events "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"eid": eid, "tid": str(other_tid)},
            ).scalar()
            assert (wrong_tenant_events or 0) == 0, (eid, other_tid)


@pytest.mark.asyncio
async def test_portfolio_second_call_without_force_returns_409(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    first = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": False},
    )
    assert first.status_code == 200, first.text

    second = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": False},
    )
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["error"] == "already_seeded"
    assert set(detail["engagement_ids"]) == set(PORTFOLIO_ENGAGEMENT_IDS)


@pytest.mark.asyncio
async def test_portfolio_force_reseeds_existing_engagements(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    first = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": False},
    )
    assert first.status_code == 200, first.text

    second = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/portfolio?tenant_id={tid}",
        json={"force": True},
    )
    assert second.status_code == 200, second.text
    assert second.json()["summary"]["engagement_count"] == 5
