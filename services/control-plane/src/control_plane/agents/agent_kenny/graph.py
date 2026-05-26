"""LangGraph StateGraph wiring for Agent Kenny v2 (scope-v2 §6.1).

This module owns the *topology* — node names, edges, and the conditional
routers used by the runtime. The actual node implementations live under
``agent_kenny/nodes/`` and are wired into the :class:`KennyAgentService`
driver loop in ``service.py``.

The compiled graph is used in two ways:

- A small set of unit tests inspects ``has_tool_calls_router`` and
  ``unverified_router`` to assert routing decisions without exercising the
  LLM or DB.
- The driver loop (``service.run_graph``) walks the same node names in the
  same order. We keep the topology declarative here so a future migration
  to native LangGraph execution (with checkpointer + replay) doesn't have
  to re-derive the edges from imperative code.
"""

from __future__ import annotations

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
        # Security incident — short-circuit to persist with rejection text;
        # the service layer flips state.security_rejected first.
        return NODE_PERSIST
    if report.not_found and state.revision_attempts < MAX_REVISION_ATTEMPTS:
        return NODE_REVISE
    return NODE_ADVERSARIAL


def build_graph() -> Any:
    """Compile a LangGraph StateGraph that mirrors the driver's execution order.

    The compiled graph is held by :class:`KennyAgentService` for introspection
    + future native execution; the running path uses the hand-rolled driver
    so we can pass the active ``AsyncSession`` + ``emit`` sink through.
    """
    from langgraph.graph import END, START, StateGraph

    g: Any = StateGraph(AgentState)

    async def _noop(state: AgentState) -> AgentState:
        return state

    for name in (
        NODE_RETRIEVE,
        NODE_LLM_CALL,
        NODE_DISPATCH_TOOLS,
        NODE_EXTRACT_CITATIONS,
        NODE_VERIFY_CITATIONS,
        NODE_REVISE,
        NODE_ADVERSARIAL,
        NODE_PERSIST,
    ):
        g.add_node(name, _noop)

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
    return g.compile()


__all__ = [
    "NODE_ADVERSARIAL",
    "NODE_DISPATCH_TOOLS",
    "NODE_END",
    "NODE_EXTRACT_CITATIONS",
    "NODE_LLM_CALL",
    "NODE_PERSIST",
    "NODE_RETRIEVE",
    "NODE_REVISE",
    "NODE_VERIFY_CITATIONS",
    "build_graph",
    "has_tool_calls_router",
    "unverified_router",
]
