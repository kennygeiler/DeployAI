"""Bearer-token auth tests for the MCP server (v2 Phase 4)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from mcp_server.db import clear_engine_cache
from mcp_server.main import app

from .conftest import insert_api_key, seed_tenant_with_engagement

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def mcp_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    url = postgres_engine.url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mcp-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://mcp") as client:
        yield client
    clear_engine_cache()


def _rpc(method: str, *, id_: int = 1, params: dict[str, object] | None = None) -> dict[str, object]:
    body: dict[str, object] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.mark.asyncio
async def test_missing_bearer_returns_401(mcp_client: AsyncClient) -> None:
    r = await mcp_client.post("/mcp", json=_rpc("initialize"))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_empty_bearer_returns_401(mcp_client: AsyncClient) -> None:
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("initialize"),
        headers={"Authorization": "Bearer "},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_bearer_returns_401(mcp_client: AsyncClient) -> None:
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("initialize"),
        headers={"Authorization": "Bearer mcp_live_deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_bearer_initialize_succeeds(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t1")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("initialize"),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["serverInfo"]["name"] == "deployai-mcp"


@pytest.mark.asyncio
async def test_revoked_key_returns_401(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    api_key_id, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="rev")
    with postgres_engine.begin() as conn:
        conn.execute(
            text("UPDATE tenant_api_keys SET revoked_at = now() WHERE id = :i"),
            {"i": str(api_key_id)},
        )
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("initialize"),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_last_used_at_updated(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    api_key_id, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="usage")
    with postgres_engine.begin() as conn:
        before = conn.execute(
            text("SELECT last_used_at FROM tenant_api_keys WHERE id = :i"),
            {"i": str(api_key_id)},
        ).scalar_one()
    assert before is None
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("initialize"),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    with postgres_engine.begin() as conn:
        after = conn.execute(
            text("SELECT last_used_at FROM tenant_api_keys WHERE id = :i"),
            {"i": str(api_key_id)},
        ).scalar_one()
    assert after is not None


@pytest.mark.asyncio
async def test_health_does_not_require_auth(mcp_client: AsyncClient) -> None:
    r = await mcp_client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "mcp-server"
