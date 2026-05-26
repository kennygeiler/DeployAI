"""MCP resource URI handler tests (v2 Phase 4)."""

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


def _seed_event(engine: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID, summary: str) -> uuid.UUID:
    ev_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:i, :t, :e, now(), 'user', NULL, 'manual_capture', :s, '{}'::jsonb)"
            ),
            {"i": str(ev_id), "t": str(tenant_id), "e": str(engagement_id), "s": summary},
        )
    return ev_id


def _seed_node(engine: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID, title: str) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_nodes "
                "(id, tenant_id, engagement_id, node_type, title, status, attributes) "
                "VALUES (:i, :t, :e, 'stakeholder', :title, 'active', '{}'::jsonb)"
            ),
            {"i": str(nid), "t": str(tenant_id), "e": str(engagement_id), "title": title},
        )
    return nid


def _rpc(method: str, params: dict[str, object] | None = None, id_: int = 1) -> dict[str, object]:
    body: dict[str, object] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.mark.asyncio
async def test_resources_list_returns_templates(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/list"),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    templates = body["result"]["resourceTemplates"]
    names = {t["name"] for t in templates}
    assert names == {"engagement", "node", "event", "chain", "search/event", "search/node"}


@pytest.mark.asyncio
async def test_engagement_resource_returns_summary(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"engagement://{eid}"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    contents = r.json()["result"]["contents"]
    payload = json.loads(contents[0]["text"])
    assert payload["id"] == str(eid)
    assert payload["name"] == "mcp-eng"
    assert payload["current_phase"] == "P2_active"


@pytest.mark.asyncio
async def test_node_resource_returns_node_and_neighbors(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    nid = _seed_node(postgres_engine, tid, eid, "Alice")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"node://{nid}"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200, r.text
    payload = json.loads(r.json()["result"]["contents"][0]["text"])
    assert any(row["id"] == str(nid) for row in payload["rows"])


@pytest.mark.asyncio
async def test_event_resource_returns_event(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    ev = _seed_event(postgres_engine, tid, eid, "first capture")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"event://{ev}"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    payload = json.loads(r.json()["result"]["contents"][0]["text"])
    assert payload["id"] == str(ev)
    assert payload["summary"] == "first capture"


@pytest.mark.asyncio
async def test_search_event_resource_finds_match(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    _seed_event(postgres_engine, tid, eid, "AD migration concern raised")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": "search/event?q=migration&limit=10"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    payload = json.loads(r.json()["result"]["contents"][0]["text"])
    assert any("migration" in row["summary"] for row in payload["rows"])


@pytest.mark.asyncio
async def test_search_node_resource_finds_match(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    _seed_node(postgres_engine, tid, eid, "Bob the executive sponsor")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": "search/node?q=executive&limit=10"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    payload = json.loads(r.json()["result"]["contents"][0]["text"])
    assert any("executive" in row["title"].lower() for row in payload["rows"])


@pytest.mark.asyncio
async def test_unknown_scheme_returns_method_not_found(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": "weird://thing"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_resource_read_emits_audit_event(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    _, raw = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"engagement://{eid}"}),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    with postgres_engine.begin() as conn:
        rows = conn.execute(
            text("SELECT summary FROM ledger_events WHERE tenant_id = :t AND source_kind = 'mcp_resource_read'"),
            {"t": str(tid)},
        ).all()
    assert any(f"engagement://{eid}" in r_[0] for r_ in rows)
