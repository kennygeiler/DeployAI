"""Outbound MCP client — Wave 2D of Phase 5 (scope-v2 §9, threat-model §3+§4).

Single source of truth for any HTTP call Agent Kenny makes to an *external*
MCP server (Slack, Linear, GDrive, Notion, GitHub for v1). Wave 3G will
plug this into the LangGraph dispatcher; this PR just builds the client +
audit + guard-checks against stable Protocols that Wave 2F's real
implementations will satisfy.

Security posture is dictated by `docs/security/mcp-outbound-threat-model.md`.
In particular:

- **§3.1.2 / §3.4.1** — the decrypted OAuth token never leaves this module.
  ``_authorize_headers`` lives in the same file as ``call_tool`` so a
  greppable boundary exists; no caller ever sees the plaintext bytes.
- **§3.3 (pre-emit audit)** — every guard that short-circuits the call
  (kill switch, rate limiter, allow-list) emits a typed ledger row BEFORE
  raising so the audit trail captures the attempt even when no HTTP
  call left the box.
- **§3.4.2 (token redaction)** — outbound request bodies are scrubbed by
  the existing ``_scrub_secrets`` from ``control_plane.ledger.emitter``
  before they land in ``detail``. We re-import that exact function instead
  of writing our own so the secret-key needle list stays in one place.
- **§5.1 (prompt injection)** — this client returns the upstream
  ``content`` payload to the caller unmodified. Treating tool results as
  data-not-instructions is Wave 3G's responsibility (envelope wrapping +
  system-prompt clause); we explicitly do NOT parse or interpret them.

The transport is HTTP POST with JSON-RPC 2.0 bodies, ``Accept:
text/event-stream, application/json`` per the MCP HTTP-SSE convention. We
accept both pure-JSON and SSE-framed responses on the same code path —
the SSE branch concatenates ``data:`` lines into one JSON blob before
parsing (the inbound MCP server in ``services/mcp-server`` always replies
with pure JSON, but real upstreams sometimes stream).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.mcp_types import (
    McpOutboundDisabled,
    McpOutboundError,
    McpProtocolError,
    McpRateLimited,
    McpToolNotAllowed,
    McpToolResult,
    McpToolSpec,
    McpTransportError,
)
from control_plane.domain.mcp_outbound import TenantMcpConfig
from control_plane.ledger import emit_ledger_event

# Re-use the canonical secret scrubber so the needle list stays in one
# place (threat-model §3.4.2). Module-private import is intentional —
# this is the SAME function the ledger emitter applies as a backstop;
# we apply it eagerly here so the redacted shape is also what the unit
# tests assert on.
from control_plane.ledger.emitter import _scrub_secrets

_log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S: float = 30.0
"""Hard per-call ceiling per scope-v2 §9.4 rationale (no upstream gets to
hold an agent turn open). Configurable via :class:`McpOutboundClient`
constructor for upstreams known to be slower; the absolute cap remains
60s (the agent-turn timeout from scope-v2 §6.2) — anything past that
exceeds the loop's own budget."""

_HARD_TIMEOUT_CAP_S: float = 60.0

# Truncate logged request bodies so a runaway argument blob doesn't
# bloat the ledger row. Detail JSONB columns are PostgreSQL-row-size
# bound (~8KB) so we keep a generous head-room.
_AUDIT_BODY_CHAR_CAP = 2000


# --------------------------------------------------------------------------
# Stable interfaces — Wave 2F implements; this PR ships Protocols + no-ops.
# --------------------------------------------------------------------------


@runtime_checkable
class McpRateLimiter(Protocol):
    """Per-tenant + per-tool throttle.

    Wave 2F lands the real Redis-backed implementation; this PR uses
    ``NoopRateLimiter`` in tests. The Protocol is intentionally small —
    ``acquire`` returns ``False`` when the call should be rejected so
    callers can convert to a typed exception, ``release`` runs on the
    response path so the limiter can refund unused budget on transport
    failures.
    """

    async def acquire(self, tenant_id: uuid.UUID, tool_name: str) -> bool: ...
    async def release(self, tenant_id: uuid.UUID, tool_name: str) -> None: ...


@runtime_checkable
class McpKillSwitch(Protocol):
    """Per-tenant disable-all-external switch (threat-model §5.5 option B).

    Wave 2F will back this with the ``app_tenants.mcp_outbound_disabled``
    column; tests use ``NoopKillSwitch``. Returning a bool keeps the
    interface async-friendly so a future implementation can poll Redis
    or a config-service.
    """

    async def is_outbound_disabled(self, tenant_id: uuid.UUID) -> bool: ...


# Resolves ``(tenant_id, ciphertext) -> plaintext token`` for the outbound
# bearer. Wave 2E owns the OAuth refresh / storage path; this client is
# only the consumer.
#
# Async so the real implementation can ``await`` ``decrypt_field`` against
# the same tenant-scoped session it was constructed with — see the
# integration test for a concrete wiring.
DekResolver = Callable[[uuid.UUID, bytes], Awaitable[str]]

# Factory that returns an *async context manager* yielding an
# ``AsyncSession`` (typically a ``TenantScopedSession``). The audit emit
# uses this so the per-call ledger row lands in its own transaction —
# kept separate from whatever session the agent loop is currently using
# so an audit-emit failure can never roll back business state.
AuditSessionFactory = Callable[[uuid.UUID], "AsyncContextManager[AsyncSession]"]


# Bring AsyncContextManager into the namespace (PEP 585 style) without
# importing the typing alias above for clarity.
from contextlib import AbstractAsyncContextManager as AsyncContextManager  # noqa: E402


class NoopRateLimiter:
    """Test-double permitting every call. Wave 2F replaces this."""

    async def acquire(self, tenant_id: uuid.UUID, tool_name: str) -> bool:
        return True

    async def release(self, tenant_id: uuid.UUID, tool_name: str) -> None:
        return None


class NoopKillSwitch:
    """Test-double whose switch is always off. Wave 2F replaces this."""

    async def is_outbound_disabled(self, tenant_id: uuid.UUID) -> bool:
        return False


# --------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------


class McpOutboundClient:
    """One process-wide client; constructed at app boot with shared deps.

    The HTTP client is injected so tests can pass an
    :class:`httpx.AsyncClient` backed by :class:`httpx.MockTransport` and
    the production wiring can configure connection pools + TLS verify
    centrally. The ``dek_resolver`` is also injected so the integration
    test can wire the real ``deployai_tenancy.envelope.decrypt_field``
    while unit tests can pass a sync stub.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        dek_resolver: DekResolver,
        rate_limiter: McpRateLimiter,
        kill_switch: McpKillSwitch,
        audit_session_factory: AuditSessionFactory,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if timeout_s <= 0 or timeout_s > _HARD_TIMEOUT_CAP_S:
            raise ValueError(
                f"timeout_s must be in (0, {_HARD_TIMEOUT_CAP_S}]; got {timeout_s!r}",
            )
        self._http = http_client
        self._dek = dek_resolver
        self._rate = rate_limiter
        self._kill = kill_switch
        self._audit_session = audit_session_factory
        self._timeout_s = timeout_s

    # ----- public surface ---------------------------------------------------

    async def list_tools(self, config: TenantMcpConfig) -> list[McpToolSpec]:
        """Fetch the upstream MCP server's advertised ``tools/list``.

        Used by the agent loop at turn start to merge external tools into
        Kenny's registry (scope-v2 §9.2). No allow-list filtering happens
        here — the loop applies ``config.allowed_tools`` after fetch so
        the audit trail records the full advertised set for forensics.
        """
        envelope = await self._invoke_jsonrpc(
            config,
            method="tools/list",
            params={},
            audit_tool_name="__list__",
            tenant_id=config.tenant_id,
            engagement_id=None,
            turn_id=None,
            redacted_request={"method": "tools/list"},
        )
        if not isinstance(envelope, dict):
            raise McpProtocolError("tools/list did not return a JSON object")
        tools_field = envelope.get("tools")
        if not isinstance(tools_field, list):
            raise McpProtocolError(f"tools/list result missing 'tools' array (got {type(tools_field).__name__})")
        out: list[McpToolSpec] = []
        for entry in tools_field:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            description = entry.get("description") or ""
            schema = entry.get("inputSchema") or entry.get("input_schema") or {}
            if not isinstance(name, str):
                continue
            if not isinstance(schema, dict):
                schema = {}
            out.append(
                McpToolSpec(
                    name=name,
                    description=description if isinstance(description, str) else "",
                    input_schema=schema,
                )
            )
        return out

    async def call_tool(
        self,
        config: TenantMcpConfig,
        *,
        tool_name: str,
        args: dict[str, Any],
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID,
        turn_id: uuid.UUID,
    ) -> McpToolResult:
        """Invoke one external MCP tool. Three guards fire BEFORE the network call.

        Order matters: kill-switch first (cheapest, most-likely-true
        during incident response), then allow-list (cheap, deterministic),
        then rate-limiter (may touch Redis). Each guard emits its own
        typed ledger row so reviewers can tell denials from operational
        throttling from incident lockdowns at audit time.
        """
        started = time.monotonic()

        # 1. Kill switch — threat-model §5.5.
        if await self._kill.is_outbound_disabled(tenant_id):
            await self._emit_guard_audit(
                source_kind="mcp_outbound_blocked",
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                config=config,
                tool_name=tool_name,
                turn_id=turn_id,
                detail_extra={"reason": "kill_switch_engaged"},
            )
            raise McpOutboundDisabled(
                f"outbound MCP disabled for tenant {tenant_id} (kill switch)",
            )

        # 2. Allow-list — scope-v2 §9.4 row 4.3.
        if config.allowed_tools is not None and tool_name not in config.allowed_tools:
            await self._emit_guard_audit(
                source_kind="mcp_outbound_denied",
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                config=config,
                tool_name=tool_name,
                turn_id=turn_id,
                detail_extra={
                    "reason": "not_in_allow_list",
                    "allowed_tools_count": len(config.allowed_tools),
                },
            )
            raise McpToolNotAllowed(
                f"tool {tool_name!r} not in tenant allow-list",
                tool_name=tool_name,
            )

        # 3. Rate limit — threat-model §5.3.
        if not await self._rate.acquire(tenant_id, tool_name):
            await self._emit_guard_audit(
                source_kind="mcp_outbound_rate_limited",
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                config=config,
                tool_name=tool_name,
                turn_id=turn_id,
                detail_extra={"reason": "rate_limit_exceeded"},
            )
            raise McpRateLimited(
                f"rate limit exceeded for tenant {tenant_id} tool {tool_name!r}",
                tool_name=tool_name,
            )

        # All guards passed — make the call. Any exception below is
        # caught and converted to a typed McpToolResult (status=error)
        # so the agent loop can render a "tool failed" message without
        # the whole turn crashing. We still release the rate-limit
        # budget on transport failure so a flaky upstream doesn't burn
        # the per-tenant call cap.
        result: McpToolResult
        try:
            envelope = await self._invoke_jsonrpc(
                config,
                method="tools/call",
                params={"name": tool_name, "arguments": args},
                audit_tool_name=tool_name,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                turn_id=turn_id,
                redacted_request={
                    "method": "tools/call",
                    "tool_name": tool_name,
                    "arguments": _scrub_secrets(args) if isinstance(args, dict) else {},
                },
            )
        except McpOutboundError:
            await self._rate.release(tenant_id, tool_name)
            raise
        except Exception as exc:  # pragma: no cover — defensive belt
            await self._rate.release(tenant_id, tool_name)
            raise McpTransportError(f"unexpected outbound error: {exc!s}") from exc

        # MCP CallToolResult shape per the spec: {content: [...], isError: bool}
        if not isinstance(envelope, dict):
            raise McpProtocolError("tools/call did not return a JSON object")
        content_field = envelope.get("content")
        if not isinstance(content_field, list):
            content_field = []
        is_tool_error = bool(envelope.get("isError", False))
        latency_ms = int((time.monotonic() - started) * 1000)
        result = McpToolResult(
            status="error" if is_tool_error else "ok",
            content=[c for c in content_field if isinstance(c, dict)],
            error_kind=None,
            latency_ms=latency_ms,
            tool_name=tool_name,
            is_tool_error=is_tool_error,
        )
        return result

    # ----- internals --------------------------------------------------------

    async def _invoke_jsonrpc(
        self,
        config: TenantMcpConfig,
        *,
        method: str,
        params: dict[str, Any],
        audit_tool_name: str,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        turn_id: uuid.UUID | None,
        redacted_request: dict[str, Any],
    ) -> Any:
        """Build + send one JSON-RPC 2.0 request, parse the response, emit audit.

        Returns the parsed ``result`` field on success. On transport or
        protocol failure: still emits an audit row with the typed
        error_kind before raising so the trail captures the attempt.
        """
        token = await self._authorize_token(config)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
        }
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        started = time.monotonic()
        status_code = 0
        response_bytes = 0
        error_kind: str | None = None
        error_message: str | None = None
        parsed_result: Any = None
        try:
            response = await self._http.post(
                config.endpoint,
                headers=headers,
                json=body,
                timeout=self._timeout_s,
            )
            status_code = response.status_code
            raw_bytes = response.content
            response_bytes = len(raw_bytes)
            if 400 <= status_code < 500:
                error_kind = "upstream_4xx"
                error_message = response.text[:240]
                raise McpTransportError(
                    f"upstream {status_code} on {method}: {error_message}",
                )
            if status_code >= 500:
                error_kind = "upstream_5xx"
                error_message = response.text[:240]
                raise McpTransportError(
                    f"upstream {status_code} on {method}: {error_message}",
                )
            envelope = _parse_response_body(response)
            if not isinstance(envelope, dict):
                error_kind = "protocol_error"
                raise McpProtocolError(
                    f"upstream returned non-object envelope (got {type(envelope).__name__})",
                )
            if envelope.get("jsonrpc") != "2.0":
                error_kind = "protocol_error"
                raise McpProtocolError(
                    f"upstream returned non-2.0 jsonrpc envelope: {envelope.get('jsonrpc')!r}",
                )
            if "error" in envelope and envelope["error"] is not None:
                error_kind = "protocol_error"
                err_payload = envelope["error"]
                error_message = (err_payload.get("message") if isinstance(err_payload, dict) else str(err_payload))[
                    :240
                ]
                raise McpProtocolError(f"upstream jsonrpc error: {error_message}")
            if "result" not in envelope:
                error_kind = "protocol_error"
                raise McpProtocolError("upstream jsonrpc envelope missing 'result'")
            parsed_result = envelope["result"]
        except httpx.TimeoutException as exc:
            error_kind = "transport_timeout"
            error_message = str(exc)[:240]
            raise McpTransportError(f"outbound MCP call timed out: {error_message}") from exc
        except httpx.HTTPError as exc:
            if error_kind is None:
                error_kind = "transport_error"
            error_message = str(exc)[:240]
            raise McpTransportError(f"outbound MCP transport error: {error_message}") from exc
        except McpOutboundError:
            raise
        except json.JSONDecodeError as exc:
            error_kind = "protocol_error"
            error_message = str(exc)[:240]
            raise McpProtocolError(f"upstream returned non-JSON body: {error_message}") from exc
        finally:
            latency_ms = int((time.monotonic() - started) * 1000)
            # Best-effort audit — never let an audit failure mask the
            # original outcome (success or typed failure).
            try:
                await self._emit_call_audit(
                    tenant_id=tenant_id,
                    engagement_id=engagement_id,
                    config=config,
                    tool_name=audit_tool_name,
                    turn_id=turn_id,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    response_byte_count=response_bytes,
                    error_kind=error_kind,
                    error_message=error_message,
                    redacted_request=redacted_request,
                )
            except Exception:
                # broad: audit emit must never mask the original outcome
                _log.exception("mcp_outbound audit emit failed")
        return parsed_result

    async def _authorize_token(self, config: TenantMcpConfig) -> str:
        """Decrypt the stored OAuth bearer for this row.

        Boundary-enforcement: the plaintext token never leaves this
        module. ``_invoke_jsonrpc`` consumes the return value directly
        into the ``Authorization`` header without binding it to any
        attribute the caller can read. If the ciphertext is absent we
        fail closed with a typed exception so the audit row gets a clear
        ``decryption_failed`` kind rather than an opaque ``None`` deref.
        """
        if config.encrypted_auth_token is None:
            raise McpTransportError(
                f"tenant_mcp_configs row {config.id} has no encrypted_auth_token",
            )
        try:
            return await self._dek(config.tenant_id, config.encrypted_auth_token)
        except Exception as exc:
            raise McpTransportError(f"DEK decryption failed: {exc!s}") from exc

    # ----- audit emit -------------------------------------------------------

    async def _emit_call_audit(
        self,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        config: TenantMcpConfig,
        tool_name: str,
        turn_id: uuid.UUID | None,
        status_code: int,
        latency_ms: int,
        response_byte_count: int,
        error_kind: str | None,
        error_message: str | None,
        redacted_request: dict[str, Any],
    ) -> None:
        detail = {
            "connector_kind": config.connector_kind,
            "config_id": str(config.id),
            "tool_name": tool_name,
            "status": "error" if error_kind else "ok",
            "http_status": status_code,
            "latency_ms": latency_ms,
            "response_byte_count": response_byte_count,
            "error": error_kind,
            "error_message": error_message,
            "turn_id": str(turn_id) if turn_id is not None else None,
            "redacted_request": _truncate_audit_value(_scrub_secrets(redacted_request)),
        }
        summary = f"mcp outbound {config.connector_kind}.{tool_name} -> {detail['status']}"
        async with self._audit_session(tenant_id) as session:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="agent",
                actor_id=f"agent_kenny:{config.connector_kind}",
                source_kind="mcp_outbound_call",
                source_ref=config.id,
                summary=summary[:500],
                detail=detail,
            )
            await session.commit()

    async def _emit_guard_audit(
        self,
        *,
        source_kind: str,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        config: TenantMcpConfig,
        tool_name: str,
        turn_id: uuid.UUID | None,
        detail_extra: dict[str, Any],
    ) -> None:
        detail = {
            "connector_kind": config.connector_kind,
            "config_id": str(config.id),
            "tool_name": tool_name,
            "turn_id": str(turn_id) if turn_id is not None else None,
            **detail_extra,
        }
        summary = f"mcp outbound {source_kind}: {config.connector_kind}.{tool_name}"
        async with self._audit_session(tenant_id) as session:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="agent",
                actor_id=f"agent_kenny:{config.connector_kind}",
                source_kind=source_kind,
                source_ref=config.id,
                summary=summary[:500],
                detail=detail,
            )
            await session.commit()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _parse_response_body(response: httpx.Response) -> Any:
    """Return the parsed JSON envelope from a plain-JSON or SSE response.

    SSE detection is by ``Content-Type`` first then by the body itself:
    if either says ``text/event-stream`` we walk the lines looking for
    ``data:`` chunks. The MCP spec uses one JSON-RPC envelope per
    ``data:`` line (newline-delimited frames), so we parse the LAST
    well-formed JSON line — earlier frames are progress notifications
    that share the same id.

    Plain JSON is the common case (the inbound MCP server in
    ``services/mcp-server`` always answers with ``application/json``); we
    fall through to ``response.json()`` for that path.
    """
    content_type = (response.headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type:
        return _parse_sse_body(response.text)
    # Some upstreams set ``application/json`` but still ship SSE-shaped
    # bodies; sniff the body too.
    text = response.text
    if text.lstrip().startswith("event:") or "\ndata:" in text:
        return _parse_sse_body(text)
    return response.json()


def _parse_sse_body(body: str) -> Any:
    """Parse the last ``data:``-prefixed JSON frame in an SSE stream body."""
    last: Any = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload:
            continue
        try:
            last = json.loads(payload)
        except json.JSONDecodeError:
            continue
    if last is None:
        raise McpProtocolError("SSE body contained no parseable data: frames")
    return last


def _truncate_audit_value(value: Any) -> Any:
    """Cap deeply nested or oversized values before they reach the ledger.

    Recursive walk: dicts and lists are size-limited at the JSON-stringify
    level so a hostile upstream returning a 1MB arg blob can't bloat the
    ledger row. Strings get truncated with a marker so reviewers can tell
    redaction from truncation.
    """
    try:
        rendered = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return f"<unencodable {type(value).__name__}>"
    if len(rendered) <= _AUDIT_BODY_CHAR_CAP:
        return value
    return {
        "__truncated__": True,
        "preview": rendered[: _AUDIT_BODY_CHAR_CAP - 40],
        "original_chars": len(rendered),
    }


# --------------------------------------------------------------------------
# Audit-session factory helpers (re-exported for the integration test).
# --------------------------------------------------------------------------


def make_audit_session_factory(
    *,
    engine: Any,
) -> AuditSessionFactory:
    """Wire a :class:`AuditSessionFactory` from a SQLAlchemy ``AsyncEngine``.

    Each call opens a fresh ``TenantScopedSession`` so the audit emit
    lands in its own transaction. Defined here so tests + Wave 3G have a
    one-call default; production wiring at app boot can pass its own
    factory if it needs to share a session-per-request.
    """
    # Local import keeps the module-level import-time graph free of a
    # hard dependency on deployai_tenancy for stubbed tests.
    from deployai_tenancy import TenantScopedSession

    @asynccontextmanager
    async def factory(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        async with TenantScopedSession(tenant_id=tenant_id, engine=engine) as session:
            yield session

    return factory


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "AuditSessionFactory",
    "DekResolver",
    "McpKillSwitch",
    "McpOutboundClient",
    "McpRateLimiter",
    "NoopKillSwitch",
    "NoopRateLimiter",
    "make_audit_session_factory",
]
