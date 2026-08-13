"""``revise_if_unverified`` — re-prompt the LLM after a bad (or missing) citation.

Drops the most recent assistant draft, appends a corrective system note,
and bumps ``revision_attempts`` so the runner caps the loop at
:data:`MAX_REVISION_ATTEMPTS` (scope-v2 §6.2 / §7.2).

Two triggers, both routed through the shared ``unverified_router`` in
``graph.py`` so the legacy driver and the LangGraph runtime cannot drift:

1. Unverified citations — the reply cited ``[kind:UUID]`` tokens that do
   not resolve in this engagement (the original scope-v2 behaviour).
2. Zero citations — the reply made factual claims with NO citation
   markers at all, even though the turn gathered evidence via successful
   tool calls. Observed live with claude-sonnet-5 (~1 in 10 replies
   carried markers), which left the verified-citation chips invisible.
   Refusals / IDK replies are exempt: negative controls must still
   decline without fabricating citations.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from llm_provider_py.types import LLMProvider

from control_plane.agents.agent_kenny.nodes.llm_call import (
    _parse_tool_result_text,
    call_llm_with_tools,
)
from control_plane.agents.agent_kenny.nodes.tool_dispatch import (
    synthesize_unexecuted_tool_results,
)
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    AgentState,
)
from control_plane.infra.tracing import tracer

# Conservative refusal/IDK heuristic (mirrors the golden runner's
# ``_detect_idk`` patterns — kept independent because production code must
# not import from tests). A reply matching any of these is treated as a
# deliberate decline and is never forced into a citation revision.
_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bi (?:don'?t|do not) know\b", re.IGNORECASE),
    re.compile(r"\bi (?:can'?t|cannot) (?:answer|find|locate|determine)\b", re.IGNORECASE),
    re.compile(r"\bunable to (?:answer|find|determine|locate)\b", re.IGNORECASE),
    re.compile(r"\bno (?:matching|relevant) (?:data|records|evidence|information)\b", re.IGNORECASE),
    re.compile(r"\bnot (?:in|available in) (?:the|this) (?:data|engagement|ledger)\b", re.IGNORECASE),
    re.compile(r"\bno (?:information|data|evidence|records?) (?:about|on|for)\b", re.IGNORECASE),
    re.compile(r"\binsufficient (?:data|evidence|information)\b", re.IGNORECASE),
)

# Internal salvage placeholders (service.py / runtime.py) — never facts,
# never worth a revision round.
_PLACEHOLDER_REPLIES: frozenset[str] = frozenset({"(no response)", "(tool-call cap reached)"})


def looks_like_refusal(text: str) -> bool:
    """True when the reply reads as an IDK / refusal rather than an answer."""
    if not text.strip():
        return True
    return any(p.search(text) for p in _REFUSAL_PATTERNS)


def has_evidence_tool_results(state: AgentState) -> bool:
    """True when this turn produced at least one successful, non-empty tool result.

    Scans the ``<tool_result>`` user-text messages tool_dispatch left in
    ``state.messages``. Error results are skipped. Internal tools render a
    JSON payload (``{"rows": [...], ...}``) — an empty ``rows`` list is not
    evidence. Non-JSON bodies (external ``<external_data>`` envelopes)
    count as evidence when non-empty.
    """
    for msg in state.messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            continue
        for entry in _parse_tool_result_text(content):
            if entry.get("error"):
                continue
            body = (entry.get("body") or "").strip()
            if not body:
                continue
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return True
            if not isinstance(payload, dict):
                return True
            rows = payload.get("rows")
            if isinstance(rows, list) and rows:
                return True
            if payload.get("content"):
                return True
    return False


def needs_zero_citation_revision(state: AgentState) -> bool:
    """Zero-citation trigger: factual reply + tool evidence + no markers.

    All conditions must hold:

    - revision budget remains (``revision_attempts < MAX_REVISION_ATTEMPTS``);
    - citations were extracted + verified and the report is EMPTY
      (``citation_report.total == 0`` — a reply with even one marker,
      verified or not, is handled by the unverified path instead);
    - the reply is non-empty, not an internal salvage placeholder, and
      does not read as an IDK / refusal;
    - the turn made at least one successful evidence-bearing tool call.
    """
    if state.revision_attempts >= MAX_REVISION_ATTEMPTS:
        return False
    report = state.citation_report
    if report is None or report.total > 0:
        return False
    text = state.accumulated_text.strip()
    if not text or text in _PLACEHOLDER_REPLIES:
        return False
    if looks_like_refusal(text):
        return False
    return has_evidence_tool_results(state)


def should_revise(state: AgentState) -> bool:
    if state.citation_report is None:
        return False
    if state.revision_attempts >= MAX_REVISION_ATTEMPTS:
        return False
    if len(state.citation_report.not_found) > 0:
        return True
    return needs_zero_citation_revision(state)


def _corrective_message(state: AgentState) -> str:
    bad = state.citation_report.not_found if state.citation_report else []
    if bad:
        bad_list = ", ".join(f"[{c.kind}:{c.identifier}]" for c in bad)
        return (
            "Your previous reply cited identifiers that do not resolve in this "
            f"engagement: {bad_list}. Please rewrite the reply removing these "
            "fabricated citations. Keep any citations that genuinely resolve "
            "to ledger / matrix / insight rows. If you cannot ground a claim "
            "in a verifiable id, drop the claim — do not invent another id."
        )
    return (
        "Your previous reply made factual claims without any [kind:UUID] "
        "citation markers. Rewrite your answer with [kind:UUID] citations "
        "(e.g. [event:UUID], [node:UUID], [insight:UUID]) taken from the "
        "tool results above; do not add new claims."
    )


async def revise_if_unverified(
    provider: LLMProvider,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
) -> AgentState:
    """Append a corrective message + re-call the LLM."""
    if not should_revise(state):
        return state
    # Span only when a revision actually happens — the early return above
    # keeps no-op passes invisible in the trace.
    with tracer().start_as_current_span("agent_kenny.revise") as span:
        state.messages.append({"role": "user", "content": _corrective_message(state)})
        state.revision_attempts += 1
        span.set_attribute("revision.attempt", state.revision_attempts)
        # Wipe the last draft so the LLM is forced to recompute.
        state.accumulated_text = ""
        state.last_text = ""
        await call_llm_with_tools(provider, state, emit=emit)
        if state.pending_tool_calls:
            # Both drivers route revise -> extract_citations, never back to
            # dispatch — any tool_use blocks the revision call emitted would
            # dangle in state.messages and 400 the next LLM call. Answer them
            # with is_error tool_results and drain the intents.
            await synthesize_unexecuted_tool_results(
                state,
                state.pending_tool_calls,
                emit,
                reason="tool calls are not available while revising; rewrite the reply with what you already have",
                error_code="tool_call_unavailable_in_revision",
            )
            state.pending_tool_calls = []
    return state


__all__ = [
    "has_evidence_tool_results",
    "looks_like_refusal",
    "needs_zero_citation_revision",
    "revise_if_unverified",
    "should_revise",
]
