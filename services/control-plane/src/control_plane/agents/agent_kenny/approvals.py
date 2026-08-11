"""In-turn approval policy for Agent Kenny tool calls (pilot-refresh D4).

Decides which pending tool calls must pause the turn for a human decision
before executing. The default policy gates external MCP tools whose
upstream tool name looks write-capable (send / create / update / delete
and friends); internal tools are read-only by construction and never
gated. Operators can force additional tools onto the approval list via
``DEPLOYAI_AGENT_APPROVAL_TOOLS`` (comma-separated tool names, matched
exactly against the namespaced name the LLM sees, e.g.
``slack__post_message`` — or ``propose_action`` for an internal tool).

The LangGraph runtime consults this module inside the ``dispatch_tools``
node wrapper and calls ``langgraph.types.interrupt`` with the payload
built by :func:`build_approval_payload`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from control_plane.agents.agent_kenny.mcp_loader import (
    is_external_tool_name,
    split_external_tool_name,
)

APPROVAL_TOOLS_ENV = "DEPLOYAI_AGENT_APPROVAL_TOOLS"

# Verb prefixes that mark an external MCP tool as write-capable. Matched
# against the upstream tool name (the part after ``connector__``), on word
# boundaries produced by splitting on ``_`` / ``-``.
_WRITE_VERBS: frozenset[str] = frozenset(
    {
        "send",
        "post",
        "create",
        "update",
        "delete",
        "remove",
        "write",
        "add",
        "set",
        "upload",
        "publish",
        "comment",
        "reply",
        "invite",
        "archive",
        "close",
        "merge",
        "move",
        "assign",
        "edit",
        "rename",
    }
)

_ARGS_SUMMARY_MAX = 400


def _forced_approval_tools() -> frozenset[str]:
    raw = os.environ.get(APPROVAL_TOOLS_ENV, "")
    return frozenset(t.strip() for t in raw.split(",") if t.strip())


def approval_required_for(tool_name: str) -> bool:
    """True when invoking ``tool_name`` requires a human approval first."""
    if tool_name in _forced_approval_tools():
        return True
    if not is_external_tool_name(tool_name):
        return False
    parts = split_external_tool_name(tool_name)
    if parts is None:
        return False
    _, upstream_tool = parts
    words = upstream_tool.replace("-", "_").lower().split("_")
    return any(w in _WRITE_VERBS for w in words)


def summarize_args(raw_input: dict[str, Any]) -> str:
    """Compact, reviewer-facing rendering of the proposed tool arguments."""
    try:
        rendered = json.dumps(raw_input, default=str, separators=(", ", ": "), sort_keys=True)
    except (TypeError, ValueError):
        rendered = str(raw_input)
    if len(rendered) > _ARGS_SUMMARY_MAX:
        rendered = rendered[:_ARGS_SUMMARY_MAX] + "...(truncated)"
    return rendered


def build_approval_payload(flagged_calls: list[dict[str, Any]]) -> dict[str, str]:
    """Build the ``interrupt()`` payload for one batch of flagged calls.

    One decision covers the whole batch (in practice the LLM proposes one
    write at a time). ``tool`` names the first flagged call;
    ``args_summary`` enumerates every flagged call so the reviewer sees
    the full set they are approving.
    """
    first = flagged_calls[0]
    tool = str(first.get("name", ""))
    if len(flagged_calls) == 1:
        args_summary = summarize_args(dict(first.get("input") or {}))
        question = f"Agent Kenny wants to run {tool}. Allow it?"
    else:
        parts = [f"{c.get('name', '')}({summarize_args(dict(c.get('input') or {}))})" for c in flagged_calls]
        args_summary = "; ".join(parts)
        if len(args_summary) > _ARGS_SUMMARY_MAX:
            args_summary = args_summary[:_ARGS_SUMMARY_MAX] + "...(truncated)"
        question = f"Agent Kenny wants to run {len(flagged_calls)} write-capable tools ({tool}, ...). Allow them?"
    return {"question": question, "tool": tool, "args_summary": args_summary}


__all__ = [
    "APPROVAL_TOOLS_ENV",
    "approval_required_for",
    "build_approval_payload",
    "summarize_args",
]
