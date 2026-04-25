"""Epic 5 Story 5-4: deployment phase API."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.phases.machine import DEPLOYMENT_PHASES

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def phase_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "phase-int")
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.headers["X-DeployAI-Internal-Key"] = "phase-int"
            yield c
    finally:
        clear_engine_cache()


@pytest.mark.asyncio
async def test_propose_and_confirm_round_trip(
    phase_client: AsyncClient, postgres_engine: Engine, tenant_id: uuid.UUID
) -> None:
    from sqlalchemy import text

    tid = str(tenant_id)
    with postgres_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'phase t') ON CONFLICT (id) DO NOTHING"),
            {"t": tid},
        )
    r0 = await phase_client.get(f"/internal/v1/tenants/{tid}/deployment-phase")
    assert r0.status_code == 200, r0.text
    j0 = r0.json()
    current = j0["phase"]
    idx = DEPLOYMENT_PHASES.index(str(current)) if str(current) in DEPLOYMENT_PHASES else 0
    to_ph = DEPLOYMENT_PHASES[idx + 1]
    body = {
        "from_phase": current,
        "to_phase": to_ph,
        "evidence_event_ids": [],
        "proposer_agent": "cartographer",
        "reason": "test",
    }
    r1 = await phase_client.post(f"/internal/v1/tenants/{tid}/phase-transitions/propose", json=body)
    assert r1.status_code == 201, r1.text
    pid = r1.json()["id"]
    strategist = str(uuid.uuid4())
    r2 = await phase_client.post(
        f"/internal/v1/tenants/{tid}/phase-transitions/{pid}/confirm",
        headers={"X-Deployai-Strategist-Actor-Id": strategist},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["phase"] == body["to_phase"]
