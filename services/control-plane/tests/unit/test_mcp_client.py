"""Unit tests for the Wave 2D outbound MCP client.

No Postgres / network — every external dependency is mocked. The
integration test (``tests/integration/test_mcp_client_audit.py``) covers
the real audit emit + DEK round-trip against the postgres container.

Test coverage per the brief:

1. Each guard path raises the right exception AND emits the right audit
   kind BEFORE any HTTP call.
2. Allow-list with ``allowed_tools=None`` permits any tool; with explicit
   list, rejects others.
3. Redaction: a request body containing ``{"slack_signing_secret":
   "abc"}`` ends up audited without the value (re-using the canonical
   ``_scrub_secrets`` from ``control_plane.ledger.emitter``).
4. ``tools/list`` AND ``tools/call`` work against a mocked transport.
5. Transport timeout → :class:`McpTransportError` + audit ``error``
   field set.
6. 5xx response → audit captures ``error_kind=upstream_5xx``; the call
   raises :class:`McpTransportError` so Wave 3G's catch-all converts it
   to a typed :class:`McpToolResult` with ``error_kind="upstream_5xx"``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from control_plane.agents.agent_kenny.mcp_client import (
    McpOutboundClient,
    NoopKillSwitch,
    NoopRateLimiter,
)
from control_plane.agents.agent_kenny.mcp_types import (
    McpOutboundDisabled,
    McpProtocolError,
    McpRateLimited,
    McpToolNotAllowed,
    McpToolResult,
    McpTransportError,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeConfig:
    """Stand-in for :class:`TenantMcpConfig` — only the attributes the
    client actually reads. Avoids constructing the real ORM row (which
    would need a session) for unit tests.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID = field(default_factory=uuid.uuid4)
    connector_kind: str = "slack"
    endpoint: str = "https://mcp.example.com/rpc"
    encrypted_auth_token: bytes | None = b"\x00\x01\x02\x03"
    allowed_tools: list[str] | None = None


@dataclass
class _AuditCapture:
    """Records every emit_ledger_event call so the tests can assert on
    source_kind + scrubbed detail without needing a real DB.
    """

    rows: list[dict[str, Any]] = field(default_factory=list)

    def make_factory(self):
        capture = self

        @asynccontextmanager
        async def factory(tenant_id: uuid.UUID) -> AsyncIterator[Any]:
            session = AsyncMock()
            session.add = MagicMock()
            session.flush = AsyncMock()
            session.commit = AsyncMock()

            # The real emit_ledger_event calls session.add(LedgerEvent(...))
            # then session.flush(). We hijack add() to peel off the
            # LedgerEvent payload so the test can introspect detail.
            def _record_add(row: Any) -> None:
                if hasattr(row, "source_kind"):
                    capture.rows.append(
                        {
                            "source_kind": row.source_kind,
                            "tenant_id": row.tenant_id,
                            "engagement_id": row.engagement_id,
                            "actor_kind": row.actor_kind,
                            "actor_id": row.actor_id,
                            "source_ref": row.source_ref,
                            "summary": row.summary,
                            "detail": row.detail,
                        }
                    )

            session.add.side_effect = _record_add
            yield session

        return factory


async def _dek_passthrough(tenant_id: uuid.UUID, ct: bytes) -> str:
    """Identity DEK resolver — returns the ciphertext bytes as a hex
    string so tests can assert on what landed in the Authorization
    header without needing real pgcrypto.
    """
    return f"tok-{ct.hex()}"


def _mock_http_client(
    handler,
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Build an httpx.AsyncClient backed by a recording MockTransport."""
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    return httpx.AsyncClient(transport=transport), seen


def _build_client(
    *,
    http_handler,
    rate_limiter=None,
    kill_switch=None,
    capture: _AuditCapture | None = None,
) -> tuple[McpOutboundClient, list[httpx.Request], _AuditCapture]:
    capture = capture or _AuditCapture()
    client, seen = _mock_http_client(http_handler)
    out = McpOutboundClient(
        http_client=client,
        dek_resolver=_dek_passthrough,
        rate_limiter=rate_limiter or NoopRateLimiter(),
        kill_switch=kill_switch or NoopKillSwitch(),
        audit_session_factory=capture.make_factory(),
    )
    return out, seen, capture


def _jsonrpc_response(req: httpx.Request, result: dict[str, Any]) -> httpx.Response:
    body = json.loads(req.content.decode("utf-8"))
    envelope = {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": result,
    }
    return httpx.Response(200, json=envelope, request=req)


# ---------------------------------------------------------------------------
# 1 + 2. Guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_blocks_and_audits_before_network() -> None:
    class _AlwaysOff:
        async def is_outbound_disabled(self, tenant_id):
            return True

    seen_calls: list[httpx.Request] = []

    def _should_never_run(req):  # pragma: no cover — asserted by emptiness
        seen_calls.append(req)
        return httpx.Response(500, request=req)

    client, seen, capture = _build_client(
        http_handler=_should_never_run,
        kill_switch=_AlwaysOff(),
    )
    config = _FakeConfig()
    with pytest.raises(McpOutboundDisabled):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={"q": "anything"},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    assert seen == [], "kill switch must prevent network calls"
    assert len(capture.rows) == 1
    row = capture.rows[0]
    assert row["source_kind"] == "mcp_outbound_blocked"
    assert row["detail"]["reason"] == "kill_switch_engaged"
    assert row["detail"]["connector_kind"] == "slack"
    assert row["detail"]["tool_name"] == "search_messages"


@pytest.mark.asyncio
async def test_rate_limit_denial_audits_and_aborts() -> None:
    class _AlwaysDeny:
        async def acquire(self, tenant_id, tool_name):
            return False

        async def release(self, tenant_id, tool_name):
            return None

    def _should_never_run(req):  # pragma: no cover
        return httpx.Response(500, request=req)

    client, seen, capture = _build_client(
        http_handler=_should_never_run,
        rate_limiter=_AlwaysDeny(),
    )
    config = _FakeConfig()
    with pytest.raises(McpRateLimited) as excinfo:
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={"q": "anything"},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    assert excinfo.value.tool_name == "search_messages"
    assert seen == []
    assert len(capture.rows) == 1
    assert capture.rows[0]["source_kind"] == "mcp_outbound_rate_limited"
    assert capture.rows[0]["detail"]["reason"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_allow_list_none_permits_any_tool() -> None:
    def _ok(req):
        return _jsonrpc_response(req, {"content": [{"type": "text", "text": "hi"}]})

    client, seen, capture = _build_client(http_handler=_ok)
    config = _FakeConfig(allowed_tools=None)
    result = await client.call_tool(
        config,
        tool_name="anything_goes",
        args={"x": 1},
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
    )
    assert isinstance(result, McpToolResult)
    assert result.status == "ok"
    assert len(seen) == 1
    # Audit row landed.
    assert any(r["source_kind"] == "mcp_outbound_call" for r in capture.rows)


@pytest.mark.asyncio
async def test_allow_list_rejects_disallowed_tool_and_audits() -> None:
    def _should_never_run(req):  # pragma: no cover
        return httpx.Response(500, request=req)

    client, seen, capture = _build_client(http_handler=_should_never_run)
    config = _FakeConfig(allowed_tools=["search_messages", "list_channels"])
    with pytest.raises(McpToolNotAllowed) as excinfo:
        await client.call_tool(
            config,
            tool_name="dangerous_delete",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    assert excinfo.value.tool_name == "dangerous_delete"
    assert seen == []
    assert len(capture.rows) == 1
    row = capture.rows[0]
    assert row["source_kind"] == "mcp_outbound_denied"
    assert row["detail"]["reason"] == "not_in_allow_list"
    assert row["detail"]["allowed_tools_count"] == 2


# ---------------------------------------------------------------------------
# 3. Redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_body_secret_is_scrubbed_before_audit() -> None:
    def _ok(req):
        return _jsonrpc_response(req, {"content": []})

    client, _seen, capture = _build_client(http_handler=_ok)
    config = _FakeConfig()
    secret_key = "slack_signing_secret"
    await client.call_tool(
        config,
        tool_name="post_message",
        args={"channel": "#general", secret_key: "xoxb-redact-me", "text": "hi"},
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
    )
    audit_rows = [r for r in capture.rows if r["source_kind"] == "mcp_outbound_call"]
    assert len(audit_rows) == 1
    detail = audit_rows[0]["detail"]
    rendered = json.dumps(detail)
    # The secret VALUE must never land in the audit row.
    assert "xoxb-redact-me" not in rendered
    # The KEY itself is stripped by _scrub_secrets — verify the
    # non-secret keys survived so we didn't over-redact.
    args_in_audit = detail["redacted_request"]["arguments"]
    assert args_in_audit["channel"] == "#general"
    assert args_in_audit["text"] == "hi"
    assert secret_key not in args_in_audit


# ---------------------------------------------------------------------------
# 4. tools/list AND tools/call happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_parses_advertised_tools() -> None:
    def _handler(req):
        return _jsonrpc_response(
            req,
            {
                "tools": [
                    {
                        "name": "search_messages",
                        "description": "Search Slack",
                        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
                    },
                    {
                        "name": "list_channels",
                        "description": "List channels",
                        "inputSchema": {"type": "object"},
                    },
                ]
            },
        )

    client, seen, _capture = _build_client(http_handler=_handler)
    specs = await client.list_tools(_FakeConfig())
    assert [s.name for s in specs] == ["search_messages", "list_channels"]
    assert specs[0].input_schema["properties"]["q"]["type"] == "string"
    # Verify auth header carried the resolved token.
    auth = seen[0].headers.get("authorization")
    assert auth and auth.startswith("Bearer tok-")


@pytest.mark.asyncio
async def test_call_tool_returns_content_unmodified() -> None:
    payload = [
        {"type": "text", "text": "raw upstream content — caller renders this as opaque data"},
        {"type": "text", "text": "second block"},
    ]

    def _handler(req):
        return _jsonrpc_response(req, {"content": payload, "isError": False})

    client, _seen, _capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    result = await client.call_tool(
        config,
        tool_name="search_messages",
        args={"q": "foo"},
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
    )
    # Threat model §5.1: client returns content verbatim. Wave 3G is
    # responsible for envelope wrapping; this client must not touch
    # the bytes.
    assert result.status == "ok"
    assert result.content == payload
    assert result.tool_name == "search_messages"


# ---------------------------------------------------------------------------
# 5. Timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transport_timeout_raises_and_audits_error() -> None:
    def _handler(req):
        raise httpx.ConnectTimeout("upstream nap")

    client, _seen, capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    with pytest.raises(McpTransportError):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    call_rows = [r for r in capture.rows if r["source_kind"] == "mcp_outbound_call"]
    assert len(call_rows) == 1
    detail = call_rows[0]["detail"]
    assert detail["status"] == "error"
    assert detail["error"] == "transport_timeout"


# ---------------------------------------------------------------------------
# 6. 5xx upstream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upstream_5xx_audits_with_error_kind() -> None:
    def _handler(req):
        return httpx.Response(503, text="service unavailable", request=req)

    client, _seen, capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    with pytest.raises(McpTransportError):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    call_rows = [r for r in capture.rows if r["source_kind"] == "mcp_outbound_call"]
    assert len(call_rows) == 1
    assert call_rows[0]["detail"]["error"] == "upstream_5xx"
    assert call_rows[0]["detail"]["http_status"] == 503


@pytest.mark.asyncio
async def test_upstream_4xx_audits_with_error_kind() -> None:
    def _handler(req):
        return httpx.Response(401, text="bad token", request=req)

    client, _seen, capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    with pytest.raises(McpTransportError):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    call_rows = [r for r in capture.rows if r["source_kind"] == "mcp_outbound_call"]
    assert call_rows[0]["detail"]["error"] == "upstream_4xx"
    assert call_rows[0]["detail"]["http_status"] == 401


# ---------------------------------------------------------------------------
# Misc behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_encrypted_token_raises_transport_error() -> None:
    def _should_never_run(req):  # pragma: no cover
        return httpx.Response(500, request=req)

    client, seen, _capture = _build_client(http_handler=_should_never_run)
    config = _FakeConfig(encrypted_auth_token=None)
    with pytest.raises(McpTransportError):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    assert seen == []


@pytest.mark.asyncio
async def test_jsonrpc_error_envelope_raises_protocol_error() -> None:
    def _handler(req):
        body = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "error": {"code": -32601, "message": "method not found"},
            },
            request=req,
        )

    client, _seen, capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    with pytest.raises(McpProtocolError):
        await client.call_tool(
            config,
            tool_name="search_messages",
            args={},
            tenant_id=config.tenant_id,
            engagement_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
        )
    call_rows = [r for r in capture.rows if r["source_kind"] == "mcp_outbound_call"]
    assert call_rows[0]["detail"]["error"] == "protocol_error"


@pytest.mark.asyncio
async def test_sse_framed_response_parses_last_data_frame() -> None:
    def _handler(req):
        body = json.loads(req.content)
        # Two data: frames; the final one carries the result.
        envelope = {
            "jsonrpc": "2.0",
            "id": body["id"],
            "result": {"content": [{"type": "text", "text": "ok"}]},
        }
        sse = f'event: progress\ndata: {{"progress": 0.5}}\n\nevent: message\ndata: {json.dumps(envelope)}\n\n'
        return httpx.Response(
            200,
            content=sse.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
            request=req,
        )

    client, _seen, _capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    result = await client.call_tool(
        config,
        tool_name="search_messages",
        args={"q": "hi"},
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
    )
    assert result.status == "ok"
    assert result.content[0]["text"] == "ok"


@pytest.mark.asyncio
async def test_jsonrpc_request_is_2_0_with_method_and_params() -> None:
    captured_body: dict[str, Any] = {}

    def _handler(req):
        captured_body.update(json.loads(req.content))
        return _jsonrpc_response(req, {"content": []})

    client, _seen, _capture = _build_client(http_handler=_handler)
    config = _FakeConfig()
    await client.call_tool(
        config,
        tool_name="search_messages",
        args={"q": "z"},
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
    )
    assert captured_body["jsonrpc"] == "2.0"
    assert captured_body["method"] == "tools/call"
    assert captured_body["params"]["name"] == "search_messages"
    assert captured_body["params"]["arguments"] == {"q": "z"}


@pytest.mark.asyncio
async def test_constructor_rejects_oversized_timeout() -> None:
    """Configurable cap default 30s; hard cap 60s per scope-v2 §6.2 turn budget."""
    import pytest

    capture = _AuditCapture()
    client, _seen = _mock_http_client(lambda req: httpx.Response(200, json={}, request=req))
    with pytest.raises(ValueError):
        McpOutboundClient(
            http_client=client,
            dek_resolver=_dek_passthrough,
            rate_limiter=NoopRateLimiter(),
            kill_switch=NoopKillSwitch(),
            audit_session_factory=capture.make_factory(),
            timeout_s=999.0,
        )
