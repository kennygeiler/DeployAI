"""``adversarial_review`` — second-pass auditor (scope-v2 §7.3).

The cheap-provider LLM reads the draft reply + the tool results and
returns a terse list of concerns: unstated assumptions, claims not backed
by evidence, overreach. Concerns ALONE do not block the reply; concerns
plus a citation failure trigger revision.

Phase 3: parser produces structured :class:`AdversarialConcern` objects
with a heuristic severity drawn from keywords in the concern text.
"""

from __future__ import annotations

import json
import re

from llm_provider_py.types import ChatMessage, LLMProvider

from control_plane.agents.agent_kenny.types import (
    AdversarialConcern,
    AdversarialSeverity,
    AgentState,
)

_LLM_TEMPERATURE = 0.0
_LLM_MAX_OUTPUT_TOKENS = 400
_CONCERN_LINE_RE = re.compile(r"^[\s\-\*•]*([^\n]+?)\s*$")
_MAX_CONCERN_CHARS = 300

# Keyword → severity heuristic. Order matters: first match wins so the
# stricter labels (blocking) override the softer ones (warning).
_BLOCKING_NEEDLES: tuple[str, ...] = (
    "unsupported",
    "no evidence",
    "fabricat",
    "hallucin",
    "contradic",
)
_WARNING_NEEDLES: tuple[str, ...] = (
    "overreach",
    "overconfident",
    "overgeneral",
    "unstated assumption",
    "assumption",
    "speculat",
    "leap",
    "imprecise",
)


def _system_prompt() -> str:
    return (
        "You are an auditor reviewing an AI co-pilot's draft reply. Read "
        "the draft and the evidence I gathered (the tool results). List "
        "concerns one per line: unstated assumptions, claims not "
        "supported by evidence in the citations, overconfident "
        "generalizations. Be terse. If you find nothing concerning, "
        "reply with exactly 'NONE'. Do not rewrite the draft."
    )


def _build_messages(state: AgentState) -> list[ChatMessage]:
    tool_results: list[str] = []
    for m in state.messages:
        content = m.get("content", "")
        if isinstance(content, str) and "<tool_result" in content:
            tool_results.append(content)
        if len(tool_results) >= 5:
            break
    payload: dict[str, object] = {
        "user_question": state.user_message,
        "draft_reply": state.accumulated_text,
        "tool_results": tool_results,
    }
    body = json.dumps(payload, default=str)
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": body},
    ]


def classify_severity(concern_text: str) -> AdversarialSeverity:
    """Heuristic severity from keyword needles."""
    needle = concern_text.lower()
    for token in _BLOCKING_NEEDLES:
        if token in needle:
            return "blocking"
    for token in _WARNING_NEEDLES:
        if token in needle:
            return "warning"
    return "info"


def parse_concerns(raw: str) -> list[str]:
    """Legacy text-only parser, retained for the persist + ledger paths."""
    objs = parse_concerns_structured(raw)
    return [o.concern_text for o in objs]


def parse_concerns_structured(raw: str) -> list[AdversarialConcern]:
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.upper() == "NONE":
        return []
    out: list[AdversarialConcern] = []
    for line in raw.splitlines():
        m = _CONCERN_LINE_RE.match(line)
        if not m:
            continue
        text = m.group(1).strip()
        if not text or text.upper() == "NONE":
            continue
        truncated = text[:_MAX_CONCERN_CHARS]
        out.append(AdversarialConcern(concern_text=truncated, severity=classify_severity(truncated)))
    return out


async def adversarial_review(provider: LLMProvider, state: AgentState) -> AgentState:
    """Run the second-pass auditor; populate concerns on ``state``.

    ``state.adversarial_concerns`` keeps the simple ``list[str]`` shape
    for the legacy persist + ledger paths; the structured objects live
    under ``state.adversarial_concern_objs`` for the SSE emitter + the
    new ``adversarial_concerns_text`` audit column.
    """
    messages = _build_messages(state)
    raw = provider.chat_complete(
        messages,
        temperature=_LLM_TEMPERATURE,
        max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
    )
    structured = parse_concerns_structured(raw)
    state.adversarial_concern_objs = structured
    state.adversarial_concerns = [o.concern_text for o in structured]
    return state


__all__ = [
    "adversarial_review",
    "classify_severity",
    "parse_concerns",
    "parse_concerns_structured",
]
