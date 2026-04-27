"""Epic 9 Story 9.1 — internal meeting presence stub."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def meeting_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "meeting-int")
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.headers["X-DeployAI-Internal-Key"] = "meeting-int"
            yield c
    finally:
        clear_engine_cache()


@pytest.mark.asyncio
async def test_meeting_presence_off_by_default(meeting_client: AsyncClient) -> None:
    r = await meeting_client.get(
        "/internal/v1/strategist/meeting-presence",
        params={"tenant_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["in_meeting"] is False
    assert j["meeting_id"] is None


@pytest.mark.asyncio
async def test_meeting_presence_on_for_stub_tenant(
    meeting_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = "00000000-0000-4000-8000-000000000099"
    monkeypatch.setenv("DEPLOYAI_STUB_IN_MEETING_TENANT_IDS", tid)
    r = await meeting_client.get("/internal/v1/strategist/meeting-presence", params={"tenant_id": tid})
    assert r.status_code == 200
    j = r.json()
    assert j["in_meeting"] is True
    assert j["meeting_id"] is not None
    assert j["oracle_in_meeting_alert_at"] is not None
