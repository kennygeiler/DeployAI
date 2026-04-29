"""Epic 16 — pilot digest/evidence internal surfaces (tenant-scoped file)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.services.pilot_surface_data import clear_pilot_surface_cache

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_SURFACE = REPO_ROOT / "docs" / "pilot" / "examples" / "pilot-surface.example.json"


@pytest_asyncio.fixture
async def pilot_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "pilot-int")
    monkeypatch.setenv("DEPLOYAI_PILOT_SURFACE_DATA_PATH", str(EXAMPLE_SURFACE))
    clear_engine_cache()
    clear_pilot_surface_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.headers["X-DeployAI-Internal-Key"] = "pilot-int"
            yield c
    finally:
        clear_pilot_surface_cache()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_morning_digest_top_for_configured_tenant(pilot_client: AsyncClient) -> None:
    tid = "00000000-0000-4000-8000-000000000001"
    r = await pilot_client.get(
        "/internal/v1/strategist/pilot-surfaces/morning-digest-top",
        params={"tenant_id": tid},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["provenance"] == "pilot_surface_file"
    assert len(j["items"]) == 1
    assert j["items"][0]["id"] == "2d4437ee-9336-441e-ab57-121b81ee57a4"


@pytest.mark.asyncio
async def test_morning_digest_top_404_other_tenant(pilot_client: AsyncClient) -> None:
    r = await pilot_client.get(
        "/internal/v1/strategist/pilot-surfaces/morning-digest-top",
        params={"tenant_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_evidence_node_tenant_isolation(pilot_client: AsyncClient) -> None:
    tid_a = "00000000-0000-4000-8000-000000000001"
    nid = "2d4437ee-9336-441e-ab57-121b81ee57a4"
    r_ok = await pilot_client.get(
        f"/internal/v1/strategist/pilot-surfaces/evidence-node/{nid}",
        params={"tenant_id": tid_a},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["id"] == nid
    r_denied = await pilot_client.get(
        f"/internal/v1/strategist/pilot-surfaces/evidence-node/{nid}",
        params={"tenant_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert r_denied.status_code == 404


@pytest.mark.asyncio
async def test_phase_tracking_for_configured_tenant(pilot_client: AsyncClient) -> None:
    tid = "00000000-0000-4000-8000-000000000001"
    r = await pilot_client.get(
        "/internal/v1/strategist/pilot-surfaces/phase-tracking",
        params={"tenant_id": tid},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["provenance"] == "pilot_surface_file"
    assert len(j["items"]) == 1
    assert j["items"][0]["id"] == "aq-pilot-1"


@pytest.mark.asyncio
async def test_evening_synthesis_for_configured_tenant(pilot_client: AsyncClient) -> None:
    tid = "00000000-0000-4000-8000-000000000001"
    r = await pilot_client.get(
        "/internal/v1/strategist/pilot-surfaces/evening-synthesis",
        params={"tenant_id": tid},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["provenance"] == "pilot_surface_file"
    assert len(j["candidates"]) == 1
    assert len(j["patterns"]) == 1


@pytest.mark.asyncio
async def test_integration_records_empty(pilot_client: AsyncClient) -> None:
    r = await pilot_client.get(
        "/internal/v1/strategist/integration-records",
        params={"tenant_id": "00000000-0000-4000-8000-000000000001"},
    )
    assert r.status_code == 200
    assert r.json()["items"] == []
