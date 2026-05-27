"""Integration: Phase 5 Wave 3I — tenant-wide outbound-MCP audit route.

Covers (scope-v2 §9, threat-model §5.4):

1. Auth: missing internal API key → 401.
2. Tenant not found → 404 before any DB read of ledger rows.
3. Happy path: emits a mix of mcp_outbound_call / mcp_config_created /
   mcp_outbound_killswitch_changed ledger rows for one tenant, plus an
   unrelated email_ingest row, and verifies the route returns ONLY the
   MCP-related rows, newest first, capped at the requested limit.
4. Tenant isolation: rows in tenant B are never returned for tenant A.

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False,
    )


def _ins_tenant(engine: Engine, tid: uuid.UUID, *, name: str) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n) ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid), "n": name},
        )


def _ins_ledger(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    summary: str,
    detail: dict[str, object] | None = None,
) -> None:
    """Insert a raw ledger_events row.

    Bypasses ``emit_ledger_event`` so the test stays self-contained — the
    audit route reads from the ``ledger_events`` table directly and
    doesn't care how the row got there.
    """
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO ledger_events
                    (tenant_id, occurred_at, actor_kind, actor_id,
                     source_kind, summary, detail)
                VALUES
                    (:tid, :occ, :ak, :aid, :sk, :sm, CAST(:det AS jsonb))
                """,
            ),
            {
                "tid": str(tenant_id),
                "occ": occurred_at,
                "ak": actor_kind,
                "aid": actor_id,
                "sk": source_kind,
                "sm": summary,
                "det": json.dumps(detail or {}, default=str),
            },
        )


@pytest_asyncio.fixture
async def mcp_audit_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mcp-audit-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "mcp-audit-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_missing_internal_key_returns_401(
    mcp_audit_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="mcp-audit-auth")
    r = await mcp_audit_client.get(
        f"/internal/v1/tenants/{tid}/mcp_audit",
        headers={"X-DeployAI-Internal-Key": ""},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(mcp_audit_client: AsyncClient) -> None:
    r = await mcp_audit_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/mcp_audit")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_returns_only_mcp_kinds_newest_first(
    mcp_audit_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="mcp-audit-happy")

    base = datetime(2026, 5, 20, 10, 0, 0, tzinfo=UTC)
    # 1: unrelated kind — must be filtered out.
    _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        occurred_at=base,
        actor_kind="user",
        actor_id="u-1",
        source_kind="email_ingest",
        summary="unrelated email",
    )
    # 2: oldest MCP call.
    _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        occurred_at=base + timedelta(minutes=1),
        actor_kind="agent",
        actor_id="agent-kenny",
        source_kind="mcp_outbound_call",
        summary="slack.search_messages ok",
        detail={"connector_kind": "slack", "tool": "slack.search_messages", "latency_ms": 142},
    )
    # 3: config change.
    _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        occurred_at=base + timedelta(minutes=2),
        actor_kind="user",
        actor_id="admin-1",
        source_kind="mcp_config_created",
        summary="Slack MCP created",
        detail={"connector_kind": "slack"},
    )
    # 4: killswitch flip — newest, must be first in the response.
    _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        occurred_at=base + timedelta(minutes=3),
        actor_kind="user",
        actor_id="on-call-sre",
        source_kind="mcp_outbound_killswitch_changed",
        summary="kill switch ON",
        detail={"disabled": True},
    )

    r = await mcp_audit_client.get(f"/internal/v1/tenants/{tid}/mcp_audit")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body["rows"]
    assert len(rows) == 3, rows
    kinds = [row["source_kind"] for row in rows]
    assert "email_ingest" not in kinds
    # Newest first.
    assert kinds[0] == "mcp_outbound_killswitch_changed"
    assert kinds[-1] == "mcp_outbound_call"


@pytest.mark.asyncio
async def test_limit_caps_returned_rows(
    mcp_audit_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="mcp-audit-limit")
    base = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    for i in range(5):
        _ins_ledger(
            postgres_engine,
            tenant_id=tid,
            occurred_at=base + timedelta(seconds=i),
            actor_kind="agent",
            actor_id="agent-kenny",
            source_kind="mcp_outbound_call",
            summary=f"call {i}",
            detail={"connector_kind": "slack", "tool": "slack.search_messages"},
        )

    r = await mcp_audit_client.get(f"/internal/v1/tenants/{tid}/mcp_audit?limit=2")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_tenant_isolation(
    mcp_audit_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a, name="mcp-audit-a")
    _ins_tenant(postgres_engine, tid_b, name="mcp-audit-b")
    base = datetime(2026, 5, 18, 0, 0, 0, tzinfo=UTC)
    _ins_ledger(
        postgres_engine,
        tenant_id=tid_a,
        occurred_at=base,
        actor_kind="agent",
        actor_id="agent-kenny",
        source_kind="mcp_outbound_call",
        summary="tenant-A row",
        detail={"connector_kind": "slack", "tool": "slack.search_messages"},
    )
    _ins_ledger(
        postgres_engine,
        tenant_id=tid_b,
        occurred_at=base,
        actor_kind="agent",
        actor_id="agent-kenny",
        source_kind="mcp_outbound_call",
        summary="tenant-B row",
        detail={"connector_kind": "linear", "tool": "linear.list_issues"},
    )

    r = await mcp_audit_client.get(f"/internal/v1/tenants/{tid_a}/mcp_audit")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["summary"] == "tenant-A row"
