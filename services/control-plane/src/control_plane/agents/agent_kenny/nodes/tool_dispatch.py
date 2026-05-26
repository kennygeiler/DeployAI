"""``dispatch_tools`` — execute pending tool calls then loop back to the LLM.

Each tool_use payload is matched against :data:`TOOL_REGISTRY` and routed
to the matching callable in ``control_plane.agents.tools``. Inputs are
validated against the tool's JSON schema (best-effort — we only check
``type`` + ``required`` so malformed model output is rejected without
shape-shifting the validator into a full JSON-Schema engine).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.types import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
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
) -> AgentState:
    """Run every pending tool call sequentially, append results to messages."""
    for call in state.pending_tool_calls:
        if state.tool_calls_made >= MAX_TOOL_CALLS_PER_TURN:
            break
        name = str(call.get("name", ""))
        raw_input = call.get("input", {}) or {}
        if not isinstance(raw_input, dict):
            raw_input = {}
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
