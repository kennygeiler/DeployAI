"""Integration: POST /internal/v1/admin/seed-scenarios/bluestate.

Path B onboarding wizard demo loader. Verifies the full slice end-to-end
against a fresh testcontainer Postgres: scenario rows land, snapshots
backfill, temporal insights are written, and the 409 conflict path
returns the existing engagement id.
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

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "seed-scenarios-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=120.0)
    client.headers["X-DeployAI-Internal-Key"] = "seed-scenarios-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_bluestate_fresh_seed_populates_full_scenario(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    r = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engagement_id"] == BLUESTATE_ENGAGEMENT_ID
    assert body["source"] == "cp"
    summary = body["summary"]
    assert summary["stakeholder_nodes"] >= 3
    assert summary["decision_nodes"] >= 1
    assert summary["risks"] >= 1
    assert summary["snapshot_count"] >= 1
    assert 4 <= summary["temporal_insight_count"] <= 6

    with postgres_engine.begin() as conn:
        engagement = conn.execute(
            text("SELECT id, tenant_id FROM engagements WHERE id = CAST(:eid AS uuid)"),
            {"eid": BLUESTATE_ENGAGEMENT_ID},
        ).first()
        assert engagement is not None
        assert str(engagement.tenant_id) == str(tid)

        users = conn.execute(
            text("SELECT count(*) FROM app_users WHERE tenant_id = CAST(:tid AS uuid)"),
            {"tid": str(tid)},
        ).scalar()
        # The runner inserts users only under the default seed-app tenant; for
        # an isolated tenant the engagement is created without them. The test
        # mostly cares that the scenario node rows landed under the right
        # tenant_id below.

        node_counts = dict(
            conn.execute(
                text(
                    "SELECT node_type, count(*) FROM matrix_nodes "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid) "
                    "GROUP BY node_type"
                ),
                {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
            ).all()
        )
        assert node_counts.get("stakeholder", 0) >= 3
        assert node_counts.get("decision", 0) >= 1
        assert node_counts.get("system", 0) >= 1
        assert node_counts.get("commitment", 0) >= 1

        edge_count = conn.execute(
            text(
                "SELECT count(*) FROM matrix_edges "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
            ),
            {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
        ).scalar()
        assert (edge_count or 0) >= 1

        ledger_count = conn.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
            ),
            {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
        ).scalar()
        assert (ledger_count or 0) >= 100

        snapshot_count = conn.execute(
            text(
                "SELECT count(*) FROM matrix_snapshots "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
            ),
            {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
        ).scalar()
        assert (snapshot_count or 0) >= 1

        temporal_count = conn.execute(
            text(
                "SELECT count(*) FROM temporal_insights "
                "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"
            ),
            {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
        ).scalar()
        assert 4 <= (temporal_count or 0) <= 6

        evidence_counts = dict(
            conn.execute(
                text(
                    "SELECT node_type, count(*) FROM matrix_nodes "
                    "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid) "
                    "AND array_length(evidence_event_ids, 1) > 0 "
                    "GROUP BY node_type"
                ),
                {"eid": BLUESTATE_ENGAGEMENT_ID, "tid": str(tid)},
            ).all()
        )
        assert evidence_counts.get("stakeholder", 0) >= 1
        assert evidence_counts.get("decision", 0) >= 1
        assert evidence_counts.get("system", 0) >= 1
        assert evidence_counts.get("commitment", 0) >= 1

        # Silence the unused-variable warning when assertions above pass.
        _ = users


@pytest.mark.asyncio
async def test_bluestate_second_call_without_force_returns_409(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    first = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": False},
    )
    assert first.status_code == 200, first.text

    second = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": False},
    )
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["error"] == "already_seeded"
    assert detail["engagement_id"] == BLUESTATE_ENGAGEMENT_ID


@pytest.mark.asyncio
async def test_bluestate_force_reseeds_existing_engagement(s_client: AsyncClient) -> None:
    tid = uuid.uuid4()
    first = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": False},
    )
    assert first.status_code == 200, first.text

    second = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": True},
    )
    assert second.status_code == 200, second.text
    assert second.json()["engagement_id"] == BLUESTATE_ENGAGEMENT_ID
