"""Outbound MCP client — public types + exception hierarchy (scope-v2 §9.2).

Wave 2D consumers (the agent loop in Wave 3G and the unit tests in this PR)
import the dataclasses + exceptions from here so the runtime module
(:mod:`control_plane.agents.agent_kenny.mcp_client`) can be replaced later
without rippling import paths across the codebase.

The types intentionally mirror the JSON-RPC 2.0 ``tools/list`` and
``tools/call`` payload shapes used by Phase 4's inbound MCP server
(``services/mcp-server/src/mcp_server/main.py``) so the outbound client
emits the same wire format it parses on the inbound side.

The exception hierarchy is shallow and rooted at :class:`McpOutboundError`
so the agent loop can ``except McpOutboundError`` once and dispatch a
generic "external tool failed" message back to the LLM without needing to
re-enumerate every typed failure. The typed subclasses exist so unit tests
can assert which guard fired without parsing error strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

McpToolResultStatus = Literal["ok", "error"]

# Stable error_kind enum returned in :class:`McpToolResult.error_kind`. Wave
# 3G's renderer maps these to user-facing strings; keep the set additive so
# old clients don't break when new kinds land.
McpErrorKind = Literal[
    "transport_timeout",
    "transport_error",
    "upstream_4xx",
    "upstream_5xx",
    "protocol_error",
    "decryption_failed",
]


@dataclass(frozen=True)
class McpToolSpec:
    """One tool advertised by an external MCP server's ``tools/list``.

    ``input_schema`` is the JSON schema the MCP server claims its tool
    accepts; the agent loop forwards it verbatim to the LLM's
    ``tools[]`` payload so Anthropic's tool-use validator can pre-check
    LLM-generated arguments before we ship them over the wire.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpToolResult:
    """Outcome of one ``tools/call``.

    ``content`` is the raw list of content blocks the MCP server returned
    (each block is typically ``{"type": "text", "text": "..."}``). The
    client never interprets these — that's Wave 3G's job (and threat-model
    §5.1 says they must be rendered to the LLM as opaque data inside a
    ``<external_data>`` envelope so the model treats them as inert).
    """

    status: McpToolResultStatus
    content: list[dict[str, Any]]
    error_kind: McpErrorKind | None
    latency_ms: int
    raw_response_byte_count: int = 0
    # When ``status == "error"`` callers may want the upstream error text
    # for the LLM-facing "external tool failed because X" rendering.
    error_message: str | None = None
    # Mirror of the MCP CallToolResult ``isError`` flag when the server
    # returned a JSON-RPC success but flagged a tool-level error. Optional;
    # absent when the response shape did not carry the field.
    is_tool_error: bool = False
    # Used by tests + Wave 3G to inspect which tool produced the result
    # without having to thread the call name back through the loop.
    tool_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Exception hierarchy
# --------------------------------------------------------------------------


class McpOutboundError(Exception):
    """Base class for every outbound-MCP failure raised by the client.

    The agent loop catches this once and dispatches a generic "external
    tool failed" message back to the LLM; tests assert on the typed
    subclasses for guard-specific behaviour.
    """


class McpOutboundDisabled(McpOutboundError):  # noqa: N818 — Wave 2D public contract name
    """The per-tenant kill switch is engaged — no network call was made.

    Threat model §5.5 + scope-v2 §9.4 row 4.6.
    """


class McpRateLimited(McpOutboundError):  # noqa: N818 — Wave 2D public contract name
    """Wave 2F's rate limiter denied the call — no network call was made.

    Threat model §5.3 + scope-v2 §9.4 row 4.4. Tool name + tenant id are
    captured on the exception so the agent loop can render a useful
    "try again in a moment" message and the audit log can attribute the
    denial to the right (tenant, tool) bucket.
    """

    def __init__(self, message: str, *, tool_name: str | None = None) -> None:
        super().__init__(message)
        self.tool_name = tool_name


class McpToolNotAllowed(McpOutboundError):  # noqa: N818 — Wave 2D public contract name
    """Allow-list rejected the tool — no network call was made.

    Threat model §3.6.1 + scope-v2 §9.4 row 4.3. The exception name
    deliberately reads as "the tool the LLM asked for is not on the
    tenant-curated allow-list", distinct from the rate-limit + kill-
    switch denials so the audit trail differentiates the security
    incidents from operational throttling.
    """

    def __init__(self, message: str, *, tool_name: str | None = None) -> None:
        super().__init__(message)
        self.tool_name = tool_name


class McpTransportError(McpOutboundError):
    """The HTTP transport failed (timeout, connect error, TLS error).

    Distinguished from :class:`McpProtocolError` because Wave 3G's retry
    strategy should treat a network blip differently from a malformed
    MCP envelope.
    """


class McpProtocolError(McpOutboundError):
    """The upstream returned bytes that did not parse as JSON-RPC 2.0.

    Includes: not-JSON, missing ``jsonrpc`` field, missing ``result`` /
    ``error``, or a ``tools/list`` response that did not carry an array
    of tool objects.
    """


__all__ = [
    "McpErrorKind",
    "McpOutboundDisabled",
    "McpOutboundError",
    "McpProtocolError",
    "McpRateLimited",
    "McpToolNotAllowed",
    "McpToolResult",
    "McpToolResultStatus",
    "McpToolSpec",
    "McpTransportError",
]
