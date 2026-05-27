"""Integration test for the Wave 2D outbound MCP client (scope-v2 §9.4 row 4.5).

A successful (HTTP-mocked) outbound call writes a real ``ledger_events``
row with the redacted detail, and the DEK round-trip uses the actual
``deployai_tenancy.envelope.encrypt_field`` / ``decrypt_field`` against
the postgres container — not the unit-test passthrough.

Coverage focus:

- The Wave 2D audit chokepoint produces a ``mcp_outbound_call`` source_kind
  row with ``connector_kind``, ``tool_name``, ``http_status``,
  ``latency_ms``, ``response_byte_count``, scrubbed ``redacted_request``,
  ``error=None``.
- The encrypted bearer token survives encrypt → store → fetch → decrypt
  → call, and never appears in plaintext in the persisted ledger row.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
import pytest_asyncio
from deployai_tenancy import TenantScopedSession
from deployai_tenancy.envelope import (
    InMemoryDEKProvider,
    decrypt_field,
    encrypt_field,
)
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from control_plane.agents.agent_kenny.mcp_client import (
    McpOutboundClient,
    NoopKillSwitch,
    NoopRateLimiter,
)
from control_plane.agents.agent_kenny.mcp_types import McpToolResult
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.mcp_outbound import TenantMcpConfig

pytestmark = pytest.mark.integration


def _async_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql+psycopg_async").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def async_engine(postgres_engine: Engine) -> AsyncIterator[AsyncEngine]:
    """Build a separate AsyncEngine pointing at the testcontainer.

    ``postgresql+asyncpg`` is the project default; we use it here so
    ``TenantScopedSession`` works as it would in production.
    """
    raw = postgres_engine.url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    eng = create_async_engine(raw, future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


def _seed_tenant_engagement(eng: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """Create one app_tenant + one engagement; return their ids."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'mcp-outbound-it')"),
            {"t": str(tid)},
        )
        conn.execute(
            text("INSERT INTO engagements (id, tenant_id, name, status) VALUES (:e, :t, 'mcp-outbound-eng', 'active')"),
            {"e": str(eid), "t": str(tid)},
        )
    return tid, eid


@pytest.mark.asyncio
async def test_successful_outbound_call_writes_redacted_ledger_row(
    postgres_engine: Engine,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: encrypt token → call mock upstream → ledger row lands.

    The bearer token plaintext is generated, encrypted with the tenant
    DEK via the real envelope module, persisted to ``tenant_mcp_configs``,
    fetched + decrypted on the call path, and the resulting ledger row
    asserts the secret never leaks while every required detail field is
    populated.
    """
    # InMemoryDEKProvider hard-gates on ENVIRONMENT ∈ {dev,test,ci}.
    monkeypatch.setenv("ENVIRONMENT", "test")

    tid, eid = _seed_tenant_engagement(postgres_engine)
    dek_provider = InMemoryDEKProvider()
    dek_bytes = await dek_provider.get_dek(tid)

    plaintext_token = "xoxb-actual-secret-bearer-token-do-not-leak"

    # 1. Encrypt the token + insert a tenant_mcp_configs row with the
    #    ciphertext. Uses the real envelope.encrypt_field against the
    #    tenant-scoped session.
    config_id: uuid.UUID = uuid.uuid4()
    async with TenantScopedSession(tenant_id=tid, engine=async_engine) as session:
        ciphertext = await encrypt_field(
            session,
            plaintext=plaintext_token.encode("utf-8"),
            dek=dek_bytes,
        )
        config_row = TenantMcpConfig(
            id=config_id,
            tenant_id=tid,
            name="slack-prod",
            connector_kind="slack",
            transport="http_sse",
            endpoint="https://mcp.example.com/rpc",
            encrypted_auth_token=ciphertext,
            allowed_tools=["search_messages"],
            enabled=True,
        )
        session.add(config_row)
        await session.commit()

    # 2. Build a DEK resolver bound to a real TenantScopedSession that
    #    calls envelope.decrypt_field — proving the round trip works
    #    against the same Postgres pgcrypto extension production uses.
    async def _dek_resolver(tenant_id: uuid.UUID, ct: bytes) -> str:
        async with TenantScopedSession(tenant_id=tenant_id, engine=async_engine) as s:
            plaintext_bytes = await decrypt_field(s, ciphertext=ct, dek=dek_bytes)
        return plaintext_bytes.decode("utf-8")

    # 3. Audit session factory yields a real TenantScopedSession so the
    #    emit goes through RLS + the canonical emitter contract.
    @asynccontextmanager
    async def _audit_factory(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        async with TenantScopedSession(tenant_id=tenant_id, engine=async_engine) as s:
            yield s

    # 4. Mock HTTP transport: assert the Authorization header carries
    #    the decrypted bearer, return a vanilla MCP tools/call envelope.
    seen_auth: list[str | None] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        seen_auth.append(req.headers.get("authorization"))
        import json

        body = json.loads(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "content": [{"type": "text", "text": "10 matching messages"}],
                    "isError": False,
                },
            },
            request=req,
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = McpOutboundClient(
            http_client=http_client,
            dek_resolver=_dek_resolver,
            rate_limiter=NoopRateLimiter(),
            kill_switch=NoopKillSwitch(),
            audit_session_factory=_audit_factory,
        )

        # Re-fetch the config row so the call site uses the same shape
        # production would (i.e. a row freshly read from the DB).
        async with TenantScopedSession(tenant_id=tid, engine=async_engine) as s:
            row = (await s.execute(select(TenantMcpConfig).where(TenantMcpConfig.id == config_id))).scalar_one()
            assert row.encrypted_auth_token is not None
            assert row.encrypted_auth_token != plaintext_token.encode("utf-8")

        result = await client.call_tool(
            row,
            tool_name="search_messages",
            args={
                "q": "production incident",
                # Secret-shaped key inside arguments — must not appear
                # in the persisted ledger detail.
                "slack_signing_secret": "must-not-leak",
            },
            tenant_id=tid,
            engagement_id=eid,
            turn_id=uuid.uuid4(),
        )

    assert isinstance(result, McpToolResult)
    assert result.status == "ok"
    assert result.content[0]["text"] == "10 matching messages"

    # The decrypted bearer made it onto the wire.
    assert seen_auth and seen_auth[0] == f"Bearer {plaintext_token}"

    # 5. Read back the ledger row and assert redaction + completeness.
    async with TenantScopedSession(tenant_id=tid, engine=async_engine) as s:
        rows = (
            (
                await s.execute(
                    select(LedgerEvent).where(
                        LedgerEvent.tenant_id == tid,
                        LedgerEvent.source_kind == "mcp_outbound_call",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    ledger = rows[0]
    detail = ledger.detail
    assert detail["connector_kind"] == "slack"
    assert detail["tool_name"] == "search_messages"
    assert detail["status"] == "ok"
    assert detail["http_status"] == 200
    assert detail["error"] is None
    assert detail["response_byte_count"] > 0
    assert detail["latency_ms"] >= 0
    # Redaction round-trip: secret key + value never land in the row.
    import json as _json

    rendered = _json.dumps(detail)
    assert plaintext_token not in rendered
    assert "must-not-leak" not in rendered
    assert "slack_signing_secret" not in rendered
    # Non-secret arg survives — proves we didn't over-redact.
    args_in_audit = detail["redacted_request"]["arguments"]
    assert args_in_audit["q"] == "production incident"
    # source_ref pins the audit row to the config row used.
    assert ledger.source_ref == config_id
    assert ledger.engagement_id == eid
