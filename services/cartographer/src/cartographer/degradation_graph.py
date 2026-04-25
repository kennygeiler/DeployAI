"""Optional LangGraph with explicit ``agent_error`` terminal (Story 6-8, FR46).

The happy path is a no-op over ``StubState``; the failure path sets
``error: AgentErrorPayload`` and stops. Callers can branch on ``error`` in the final
invoke result instead of raising silently.
"""

from __future__ import annotations

import uuid
from typing import Any, NotRequired, TypedDict, cast

from langgraph.graph import END, START, StateGraph


class AgentErrorPayload(TypedDict):
    error_code: str
    retry_possible: bool
    user_message: str


class DegradedState(TypedDict):
    step: int
    fail: bool
    error: NotRequired[AgentErrorPayload]


def _ok(state: DegradedState) -> DegradedState:
    return {"step": 1, "fail": state.get("fail", False)}


def _fail_or_next(state: DegradedState) -> DegradedState:
    if state.get("fail"):
        return {
            "step": 2,
            "fail": True,
            "error": {
                "error_code": "llm_timeout",
                "retry_possible": True,
                "user_message": "The agent could not finish in time. Retry is available.",
            },
        }
    return {"step": 2, "fail": False}


def _route_after_check(state: DegradedState) -> str:
    if state.get("fail") and "error" in state:
        return "agent_error"
    return "done"


def _terminal_error(state: DegradedState) -> DegradedState:
    # Already populated in _fail_or_next; this node is an explicit fan-in for other graphs.
    return state


def _done(_state: DegradedState) -> DegradedState:
    return {"step": 3, "fail": False}


def build_degradation_graph() -> StateGraph[DegradedState]:
    """``START`` → check → (``agent_error`` | ``done``) → ``END``."""
    g: StateGraph[DegradedState] = StateGraph(DegradedState)
    g.add_node("start_ok", _ok)
    g.add_node("check", _fail_or_next)
    g.add_node("agent_error", cast(Any, _terminal_error))
    g.add_node("done", cast(Any, _done))
    g.add_edge(START, "start_ok")
    g.add_edge("start_ok", "check")
    g.add_conditional_edges(
        "check",
        _route_after_check,
        {
            "agent_error": "agent_error",
            "done": "done",
        },
    )
    g.add_edge("agent_error", END)
    g.add_edge("done", END)
    return g


def new_run_id() -> str:
    return str(uuid.uuid4())
