"""Cross-engagement + cross-tenant isolation tests (v2 Phase 4)."""

from __future__ import annotations

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


def _rpc(method: str, params: dict[str, object] | None = None, id_: int = 1) -> dict[str, object]:
    body: dict[str, object] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.mark.asyncio
async def test_cross_engagement_request_returns_403_no_leak(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a, eid_a = seed_tenant_with_engagement(postgres_engine)
    _, _eid_b = seed_tenant_with_engagement(postgres_engine)
    _, raw_a = insert_api_key(postgres_engine, tenant_id=tid_a, engagement_id=eid_a, name="a")
    # Same tenant, different engagement
    eid_b_same_tenant = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase) "
                "VALUES (:e, :t, 'second engagement', 'P2_active')"
            ),
            {"e": str(eid_b_same_tenant), "t": str(tid_a)},
        )

    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"engagement://{eid_b_same_tenant}"}),
        headers={"Authorization": f"Bearer {raw_a}"},
    )
    assert r.status_code == 403
    body = r.json()
    assert "engagement_id" not in str(body)
    assert "second engagement" not in str(body)


@pytest.mark.asyncio
async def test_cross_tenant_lookup_returns_403(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a, eid_a = seed_tenant_with_engagement(postgres_engine)
    tid_b, eid_b = seed_tenant_with_engagement(postgres_engine)
    _, raw_a = insert_api_key(postgres_engine, tenant_id=tid_a, engagement_id=eid_a, name="a")
    assert tid_a != tid_b
    r = await mcp_client.post(
        "/mcp",
        json=_rpc("resources/read", {"uri": f"engagement://{eid_b}"}),
        headers={"Authorization": f"Bearer {raw_a}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_tool_call_only_sees_own_engagement_rows(mcp_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = seed_tenant_with_engagement(postgres_engine)
    other_tid, eid_b = seed_tenant_with_engagement(postgres_engine)
    _, raw_a = insert_api_key(postgres_engine, tenant_id=tid, engagement_id=eid, name="t")

    # Insert an event in engagement A (tenant A) and one in engagement B (other tenant).
    ev_a = uuid.uuid4()
    ev_b = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:i, :t, :e, now(), 'user', NULL, 'manual_capture', 'engagement-A event', '{}'::jsonb)"
            ),
            {"i": str(ev_a), "t": str(tid), "e": str(eid)},
        )
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, summary, detail) "
                "VALUES (:i, :t, :e, now(), 'user', NULL, 'manual_capture', 'engagement-B event', '{}'::jsonb)"
            ),
            {"i": str(ev_b), "t": str(other_tid), "e": str(eid_b)},
        )

    r = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/call", {"name": "query_ledger", "arguments": {"limit": 50}}),
        headers={"Authorization": f"Bearer {raw_a}"},
    )
    assert r.status_code == 200
    import json as _json

    inner = _json.loads(r.json()["result"]["content"][0]["text"])
    summaries = [row["summary"] for row in inner["rows"]]
    assert "engagement-A event" in summaries
    assert "engagement-B event" not in summaries
