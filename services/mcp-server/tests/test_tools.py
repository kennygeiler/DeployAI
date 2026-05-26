"""MCP tool exposure tests (v2 Phase 4)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from mcp_server.db import clear_engine_cache
from mcp_server.main import app
from mcp_server.tools import FORBIDDEN_TOOLS, READ_TOOL_HANDLERS, list_mcp_tools

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


def _rpc(method: str, params: dict[str, object] | None = None, id_: int = 1) -> dict[str, object]:
    body: dict[str, object] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


def test_propose_action_not_exposed() -> None:
    assert "propose_action" in FORBIDDEN_TOOLS
    assert "propose_action" not in READ_TOOL_HANDLERS
    names = {t["name"] for t in list_mcp_tools()}
    assert "propose_action" not in names


def test_all_11_read_tools_exposed() -> None:
    expected = {
        "query_ledger",
        "walk_chain",
        "get_matrix_node",
        "get_matrix_neighbors",
        "get_matrix_subgraph",
        "read_synthesis",
        "get_decision_history",
        "get_open_risks",
        "get_engagement_summary",
        "vector_search",
        "keyword_search",
    }
    actual = {t["name"] for t in list_mcp_tools()}
    assert actual == expected


@pytest.mark.asyncio
async def test_tools_list_returns_specs(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/list"),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    names = {t["name"] for t in body["result"]["tools"]}
    assert "query_ledger" in names
    assert "propose_action" not in names


@pytest.mark.asyncio
async def test_query_ledger_tool_call(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    ev_id = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:i, :t, :e, now(), 'user', NULL, 'manual_capture', 'hello', '{}'::jsonb)"
            ),
            {"i": str(ev_id), "t": str(tid), "e": str(eid)},
        )
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/call", {"name": "query_ledger", "arguments": {"limit": 50}}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    inner = json.loads(body["result"]["content"][0]["text"])
    assert inner["name"] == "query_ledger"
    assert any(row["id"] == str(ev_id) for row in inner["rows"])


@pytest.mark.asyncio
async def test_propose_action_call_is_rejected(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {"name": "propose_action", "arguments": {"description": "x", "priority": "low"}},
        ),
        headers={"Authorization": f"Bearer {raw}"},
    )
    # FastAPI HTTPException(403) surfaces as a real HTTP 403.
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_tool_returns_404(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/call", {"name": "nonsense", "arguments": {}}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_vector_search_returns_deferred_placeholder(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            {"name": "vector_search", "arguments": {"query": "ad migration"}},
        ),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    inner = json.loads(r.json()["result"]["content"][0]["text"])
    assert inner["rows"] == []
    assert inner["detail"] == "vector search deferred to Phase 5.5"


@pytest.mark.asyncio
async def test_tool_call_emits_audit_event(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/call", {"name": "get_engagement_summary", "arguments": {}}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    with postgres_engine.begin() as conn:
        rows = conn.execute(
            text("SELECT summary FROM ledger_events WHERE tenant_id = :t AND source_kind = 'mcp_tool_invocation'"),
            {"t": str(tid)},
        ).all()
    assert any("get_engagement_summary" in r_[0] for r_ in rows)
