"""LangGraph StateGraph wiring for Agent Kenny v2.

This module owns the *topology* — node names, edges, and the conditional
routers. The node implementations live under ``agent_kenny/nodes/``; the
LangGraph runtime (``runtime.py``, pilot-refresh D2) wraps them into node
callables and passes them in via ``build_graph(nodes=...)`` together with
the Postgres checkpointer, producing the executable graph.

The same compiled topology serves three consumers:

- ``runtime.py`` — the real LangGraph execution path
  (``DEPLOYAI_AGENT_RUNTIME=langgraph``): real node callables + the
  ``AsyncPostgresSaver`` checkpointer.
- The legacy hand-rolled driver in ``service.py`` — walks the same node
  names in the same order imperatively; it shares
  :func:`has_tool_calls_router` / :func:`unverified_router` so routing
  decisions cannot drift between the two runtimes.
- Unit tests — ``build_graph()`` with no arguments compiles the topology
  with inert nodes for introspection without an LLM or DB.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
)

NODE_RETRIEVE = "retrieve"
NODE_LLM_CALL = "llm_call"
NODE_DISPATCH_TOOLS = "dispatch_tools"
NODE_EXTRACT_CITATIONS = "extract_citations"
NODE_VERIFY_CITATIONS = "verify_citations"
NODE_REVISE = "revise"
NODE_ADVERSARIAL = "adversarial"
NODE_PERSIST = "persist"
NODE_END = "__end__"

NODE_NAMES: tuple[str, ...] = (
    NODE_RETRIEVE,
    NODE_LLM_CALL,
    NODE_DISPATCH_TOOLS,
    NODE_EXTRACT_CITATIONS,
    NODE_VERIFY_CITATIONS,
    NODE_REVISE,
    NODE_ADVERSARIAL,
    NODE_PERSIST,
)

NodeFn = Callable[[AgentState], Awaitable[dict[str, Any]]]


def has_tool_calls_router(state: AgentState) -> str:
    """Decide whether to loop back to tool dispatch or continue to citations."""
    if state.tool_calls_made >= MAX_TOOL_CALLS_PER_TURN:
        return NODE_EXTRACT_CITATIONS
    if state.pending_tool_calls:
        return NODE_DISPATCH_TOOLS
    return NODE_EXTRACT_CITATIONS


def unverified_router(state: AgentState) -> str:
    """After citation verification, decide whether to revise or ship."""
    report = state.citation_report
    if report is None:
        return NODE_ADVERSARIAL
    if report.cross_engagement:
        # Security incident — short-circuit to persist; the persist node
        # (or the legacy service layer) flips state.security_rejected and
        # replaces the reply text.
        return NODE_PERSIST
    if report.not_found and state.revision_attempts < MAX_REVISION_ATTEMPTS:
        return NODE_REVISE
    return NODE_ADVERSARIAL


def build_graph(
    nodes: Mapping[str, NodeFn] | None = None,
    *,
    checkpointer: Any = None,
) -> Any:
    """Compile the Agent Kenny StateGraph.

    ``nodes`` maps every name in :data:`NODE_NAMES` to an async callable
    ``(AgentState) -> dict`` (a partial state update). When omitted, inert
    passthrough nodes are used so the topology can be compiled and
    inspected without runtime dependencies (the pre-D2 behaviour, kept for
    unit tests and the legacy driver's introspection handle).

    ``checkpointer`` is threaded into ``compile()`` — the LangGraph
    runtime passes the ``AsyncPostgresSaver`` from ``checkpointer.py`` so
    turns are durable and ``interrupt()`` / ``Command(resume=...)`` work.
    """
    from langgraph.graph import END, START, StateGraph

    g: Any = StateGraph(AgentState)

    async def _noop(state: AgentState) -> dict[str, Any]:
        _ = state
        return {}

    for name in NODE_NAMES:
        fn: NodeFn = nodes[name] if nodes is not None else _noop
        g.add_node(name, fn)

    g.add_edge(START, NODE_RETRIEVE)
    g.add_edge(NODE_RETRIEVE, NODE_LLM_CALL)
    g.add_conditional_edges(
        NODE_LLM_CALL,
        has_tool_calls_router,
        {
            NODE_DISPATCH_TOOLS: NODE_DISPATCH_TOOLS,
            NODE_EXTRACT_CITATIONS: NODE_EXTRACT_CITATIONS,
        },
    )
    g.add_edge(NODE_DISPATCH_TOOLS, NODE_LLM_CALL)
    g.add_edge(NODE_EXTRACT_CITATIONS, NODE_VERIFY_CITATIONS)
    g.add_conditional_edges(
        NODE_VERIFY_CITATIONS,
        unverified_router,
        {
            NODE_REVISE: NODE_REVISE,
            NODE_ADVERSARIAL: NODE_ADVERSARIAL,
            NODE_PERSIST: NODE_PERSIST,
        },
    )
    g.add_edge(NODE_REVISE, NODE_EXTRACT_CITATIONS)
    g.add_edge(NODE_ADVERSARIAL, NODE_PERSIST)
    g.add_edge(NODE_PERSIST, END)
    return g.compile(checkpointer=checkpointer)


__all__ = [
    "NODE_ADVERSARIAL",
    "NODE_DISPATCH_TOOLS",
    "NODE_END",
    "NODE_EXTRACT_CITATIONS",
    "NODE_LLM_CALL",
    "NODE_NAMES",
    "NODE_PERSIST",
    "NODE_RETRIEVE",
    "NODE_REVISE",
    "NODE_VERIFY_CITATIONS",
    "NodeFn",
    "build_graph",
    "has_tool_calls_router",
    "unverified_router",
]
