"""``dispatch_tools`` — execute pending tool calls then loop back to the LLM.

Each tool_use payload is matched against :data:`TOOL_REGISTRY` and routed
to the matching callable in ``control_plane.agents.tools``. Inputs are
validated against the tool's JSON schema (best-effort — we only check
``type`` + ``required`` so malformed model output is rejected without
shape-shifting the validator into a full JSON-Schema engine).

External MCP routing (Wave 3G)
------------------------------
Tool names whose prefix matches a connector kind (``slack__``,
``linear__``, ``gdrive__``, ``notion__``, ``github__``) are routed to
:meth:`McpOutboundClient.call_tool` instead of the internal registry.
The result is wrapped in an ``<external_data source="..." tool="...">``
envelope before it lands back in the message history — this is the
threat-model §5.1 mitigation against prompt injection from external
systems, paired with the system-prompt clause in ``llm_call.py``.

Failed external calls (rate-limited, kill-switched, transport error)
become an ``is_error: true`` tool_result so the LLM can react ("try
again", "fall back to internal tools") instead of crashing the turn.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.embeddings.voyage_client import VoyageEmbedder
from control_plane.agents.agent_kenny.mcp_client import McpOutboundClient
from control_plane.agents.agent_kenny.mcp_loader import (
    find_loaded_config,
    is_external_tool_name,
    split_external_tool_name,
)
from control_plane.agents.agent_kenny.mcp_types import (
    McpOutboundDisabled,
    McpOutboundError,
    McpProtocolError,
    McpRateLimited,
    McpToolNotAllowed,
    McpToolResult,
    McpTransportError,
)
from control_plane.agents.agent_kenny.types import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
    McpExternalCallChunk,
    ToolResultChunk,
)
from control_plane.agents.tools import TOOL_REGISTRY, ToolError, ToolResult
from control_plane.agents.tools.analysis import (
    get_decision_history,
    get_engagement_summary,
    get_open_risks,
)
from control_plane.agents.tools.escalate import propose_action
from control_plane.agents.tools.ledger import query_ledger, walk_chain
from control_plane.agents.tools.matrix import (
    get_matrix_neighbors,
    get_matrix_node,
    get_matrix_subgraph,
)
from control_plane.agents.tools.search import keyword_search, vector_search
from control_plane.agents.tools.synthesis import read_synthesis

# Tool name → invoker. Each invoker normalizes the JSON input the LLM sent
# into the kwargs the python tool accepts (e.g. ``from`` → ``from_``).
_INVOKERS: dict[str, Callable[..., Awaitable[ToolResult]]] = {
    "query_ledger": query_ledger,
    "walk_chain": walk_chain,
    "get_matrix_node": get_matrix_node,
    "get_matrix_neighbors": get_matrix_neighbors,
    "get_matrix_subgraph": get_matrix_subgraph,
    "read_synthesis": read_synthesis,
    "get_decision_history": get_decision_history,
    "get_open_risks": get_open_risks,
    "get_engagement_summary": get_engagement_summary,
    "keyword_search": keyword_search,
    "vector_search": vector_search,
    "propose_action": propose_action,
}


def validate_input(schema: dict[str, Any], data: dict[str, Any]) -> None:
    """Minimal JSON-schema spot-check: type=object + required props present."""
    if schema.get("type") != "object":
        return
    required = schema.get("required") or []
    for key in required:
        if key not in data:
            raise ToolError(f"missing required field: {key!r}")


def _coerce_kwargs(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Translate JSON keys into python kwargs for tools that diverge."""
    if name == "query_ledger":
        out: dict[str, Any] = dict(raw)
        if "from" in out:
            value = out.pop("from")
            if isinstance(value, str):
                try:
                    out["from_"] = datetime.fromisoformat(value)
                except ValueError:
                    out["from_"] = None
            else:
                out["from_"] = value
        if "to" in out and isinstance(out["to"], str):
            try:
                out["to"] = datetime.fromisoformat(out["to"])
            except ValueError:
                out["to"] = None
        if "text" in out:
            out["text_query"] = out.pop("text")
        return out
    if name == "walk_chain":
        out2: dict[str, Any] = dict(raw)
        if "max_depth" in out2 and not isinstance(out2["max_depth"], int):
            try:
                out2["max_depth"] = int(out2["max_depth"])
            except (TypeError, ValueError):
                out2.pop("max_depth")
        return out2
    return dict(raw)


async def dispatch_tools(
    session: AsyncSession,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
    turn_id_hint: Any = None,
    mcp_client: McpOutboundClient | None = None,
    embedder: VoyageEmbedder | None = None,
) -> AgentState:
    """Run every pending tool call sequentially, append results to messages.

    External tools (namespaced ``connector__tool``) are routed to
    ``mcp_client.call_tool``. When ``mcp_client`` is ``None`` (e.g. unit
    tests that don't exercise external dispatch), any external tool_use
    produced by the LLM is converted to an error tool_result so the loop
    still progresses.

    ``embedder`` (Phase 5.5 Wave C) is the Voyage client ``vector_search``
    uses to embed the query string. When the LLM emits a ``vector_search``
    tool_use and ``embedder`` is ``None``, the call is converted to an
    is_error tool_result so the LLM falls back to ``keyword_search``
    instead of crashing the turn.
    """
    for call in state.pending_tool_calls:
        if state.tool_calls_made >= MAX_TOOL_CALLS_PER_TURN:
            break
        name = str(call.get("name", ""))
        raw_input = call.get("input", {}) or {}
        if not isinstance(raw_input, dict):
            raw_input = {}
        tool_use_id = str(call.get("_tool_use_id") or "")

        if is_external_tool_name(name):
            await _dispatch_external(
                state,
                emit=emit,
                turn_id_hint=turn_id_hint,
                mcp_client=mcp_client,
                name=name,
                raw_input=raw_input,
                tool_use_id=tool_use_id,
            )
            state.tool_calls_made += 1
            continue

        spec = TOOL_REGISTRY.get(name)
        invoker = _INVOKERS.get(name)
        if spec is None or invoker is None:
            error = f"unknown_tool:{name}"
            state.messages.append(
                {
                    "role": "user",
                    "content": (f'<tool_result name="{name}" error="{error}">no such tool</tool_result>'),
                }
            )
            if emit is not None:
                await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error=error))
            state.tool_calls_made += 1
            continue
        try:
            validate_input(spec.input_schema, raw_input)
            kwargs = _coerce_kwargs(name, raw_input)
            if name == "vector_search":
                if embedder is None:
                    raise ToolError("vector_search unavailable: no embedder configured for this process")
                kwargs["embedder"] = embedder
            result = await invoker(
                session,
                tenant_id=state.tenant_id,
                engagement_id=state.engagement_id,
                turn_id=turn_id_hint,
                **kwargs,
            )
        except ToolError as exc:
            error_msg = f"tool_error: {exc}"
            state.messages.append(
                {
                    "role": "user",
                    "content": f'<tool_result name="{name}" error="true">{error_msg}</tool_result>',
                }
            )
            if emit is not None:
                await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error=str(exc)))
            state.tool_calls_made += 1
            continue
        # Persist a compact rendering for the next LLM prompt round.
        rendered = _render_tool_result(result)
        state.messages.append(
            {
                "role": "user",
                "content": f'<tool_result name="{name}">{rendered}</tool_result>',
            }
        )
        if emit is not None:
            await emit(
                ToolResultChunk(
                    name=name,
                    row_count=len(result.rows),
                    truncated=result.truncated,
                )
            )
        state.tool_calls_made += 1
    state.pending_tool_calls = []
    return state


async def _dispatch_external(
    state: AgentState,
    *,
    emit: Callable[[Any], Awaitable[None]] | None,
    turn_id_hint: Any,
    mcp_client: McpOutboundClient | None,
    name: str,
    raw_input: dict[str, Any],
    tool_use_id: str,
) -> None:
    """Route one tool_use to the outbound MCP client + envelope-wrap the result.

    All side-effects (state.messages append + SSE emit) happen here. The
    caller bumps ``tool_calls_made`` after this returns so the per-turn
    budget gate is enforced uniformly across internal + external paths.
    """
    parts = split_external_tool_name(name)
    if parts is None:
        # Should not happen — is_external_tool_name returned True. Defensive.
        _append_external_error(state, name=name, error_text="invalid_external_tool_name")
        if emit is not None:
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="invalid_external_tool_name"))
        return
    connector_kind, upstream_tool = parts

    if mcp_client is None:
        _append_external_error(state, name=name, error_text="external_dispatch_unavailable")
        if emit is not None:
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="external_dispatch_unavailable"))
        return

    config = find_loaded_config(state.external_tools, connector_kind=connector_kind)
    if config is None:
        # The tool was advertised in this turn but the config disappeared
        # between load + dispatch — surface an error rather than calling
        # ``call_tool`` with no config (which would NPE).
        _append_external_error(state, name=name, error_text="external_config_missing")
        if emit is not None:
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="external_config_missing"))
        return

    started = time.monotonic()
    status: str
    latency_ms: int
    try:
        result: McpToolResult = await mcp_client.call_tool(
            config,
            tool_name=upstream_tool,
            args=raw_input,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            turn_id=turn_id_hint if isinstance(turn_id_hint, uuid.UUID) else uuid.uuid4(),
        )
    except McpOutboundDisabled:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "disabled"
        _append_external_error(
            state,
            name=name,
            error_text="external tool disabled (kill switch engaged)",
        )
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_outbound_disabled"))
        return
    except McpRateLimited:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "rate_limited"
        _append_external_error(state, name=name, error_text="external tool rate-limited; try again shortly")
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_rate_limited"))
        return
    except McpToolNotAllowed:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "not_allowed"
        _append_external_error(state, name=name, error_text="tool not in tenant allow-list")
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_tool_not_allowed"))
        return
    except McpTransportError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "transport_error"
        _append_external_error(state, name=name, error_text=f"upstream transport error: {exc!s}"[:240])
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_transport_error"))
        return
    except McpProtocolError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "protocol_error"
        _append_external_error(state, name=name, error_text=f"upstream protocol error: {exc!s}"[:240])
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_protocol_error"))
        return
    except McpOutboundError as exc:
        # Catch-all for any future typed subclass we forgot to enumerate.
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "error"
        _append_external_error(state, name=name, error_text=str(exc)[:240])
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="mcp_outbound_error"))
        return

    # Success path.
    latency_ms = result.latency_ms or int((time.monotonic() - started) * 1000)
    if result.is_tool_error or result.status == "error":
        # MCP CallToolResult.isError — upstream signaled a tool-level
        # error inside an otherwise valid JSON-RPC envelope. Surface as
        # is_error so the LLM can react.
        status = "tool_error"
        wrapped = _render_external_body(result.content)
        envelope_body = _wrap_external_data(
            source=connector_kind,
            tool=upstream_tool,
            body=wrapped,
        )
        state.messages.append(
            {
                "role": "user",
                "content": f'<tool_result name="{name}" error="true">{envelope_body}</tool_result>',
            }
        )
        if emit is not None:
            await emit(
                McpExternalCallChunk(
                    config_id=str(config.id),
                    connector_kind=connector_kind,
                    tool=upstream_tool,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="upstream_tool_error"))
        return

    status = "ok"
    wrapped = _render_external_body(result.content)
    envelope_body = _wrap_external_data(
        source=connector_kind,
        tool=upstream_tool,
        body=wrapped,
    )
    state.messages.append(
        {
            "role": "user",
            "content": f'<tool_result name="{name}">{envelope_body}</tool_result>',
        }
    )
    if emit is not None:
        await emit(
            McpExternalCallChunk(
                config_id=str(config.id),
                connector_kind=connector_kind,
                tool=upstream_tool,
                status=status,
                latency_ms=latency_ms,
            )
        )
        await emit(ToolResultChunk(name=name, row_count=len(result.content), truncated=False))


def _append_external_error(state: AgentState, *, name: str, error_text: str) -> None:
    """Emit an ``is_error`` ``<tool_result>`` for an external-tool failure.

    Wrapped in ``<external_data>`` for consistency with the success path
    so the model's "don't follow instructions in here" reflex stays
    triggered even on error text from upstream.
    """
    safe = error_text.replace('"', "'")
    state.messages.append(
        {
            "role": "user",
            "content": (
                f'<tool_result name="{name}" error="true">'
                f'<external_data source="{_split_connector_for_envelope(name)[0]}" '
                f'tool="{_split_connector_for_envelope(name)[1]}">{safe}</external_data>'
                "</tool_result>"
            ),
        }
    )


def _split_connector_for_envelope(name: str) -> tuple[str, str]:
    """Best-effort split for envelope attributes on error paths."""
    parts = split_external_tool_name(name)
    if parts is None:
        return ("unknown", name)
    return parts


def _render_external_body(content: list[dict[str, Any]]) -> str:
    """Stringify the upstream MCP content blocks into one body.

    MCP content blocks are typically ``{"type": "text", "text": "..."}``;
    we render the ``text`` field verbatim when present, otherwise JSON-
    encode the block. The resulting string is the *data payload* the
    envelope wraps — the threat-model §5.1 contract is "anything inside
    <external_data> is untrusted", so we don't sanitize the body further
    here. ``<`` characters in the body are HTML-escape-friendly in this
    role because the LLM sees them as opaque text inside the envelope,
    not as nested tags.
    """
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(json.dumps(block, default=str))
            continue
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
            continue
        parts.append(json.dumps(block, default=str, separators=(",", ":")))
    rendered = "\n".join(parts) if parts else ""
    # Defensive truncation: a hostile upstream returning megabytes of
    # data would blow the message context. The internal-tool path caps
    # rows at 50; we mirror with a character cap here.
    cap = 8000
    if len(rendered) > cap:
        rendered = rendered[:cap] + "...(truncated)"
    return rendered


def _wrap_external_data(*, source: str, tool: str, body: str) -> str:
    """Return ``<external_data source=... tool=...>body</external_data>``.

    The single mitigation against threat-model §5.1. Combined with the
    system-prompt clause in :mod:`llm_call`, this signals to the LLM
    that anything between the tags is *data*, not instructions. No
    escaping of the body here — the wrapper itself is the signal; the
    body is allowed to contain any text the upstream emitted.
    """
    safe_source = source.replace('"', "'")
    safe_tool = tool.replace('"', "'")
    return f'<external_data source="{safe_source}" tool="{safe_tool}">{body}</external_data>'


def _render_tool_result(result: ToolResult) -> str:
    """Render a tool result in a compact textual form for the LLM."""
    import json

    payload: dict[str, Any] = {
        "rows": result.rows[:50],
        "truncated": result.truncated,
        "row_count": len(result.rows),
    }
    if result.next_cursor:
        payload["next_cursor"] = result.next_cursor
    return json.dumps(payload, default=str, separators=(",", ":"))


def has_pending_tool_calls(state: AgentState) -> bool:
    return bool(state.pending_tool_calls)


def tool_budget_remaining(state: AgentState) -> int:
    return max(0, MAX_TOOL_CALLS_PER_TURN - state.tool_calls_made)


__all__ = [
    "dispatch_tools",
    "has_pending_tool_calls",
    "tool_budget_remaining",
    "validate_input",
]
