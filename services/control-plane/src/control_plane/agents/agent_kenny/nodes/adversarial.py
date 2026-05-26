"""``adversarial_review`` — second-pass auditor (scope-v2 §7.3).

The cheap-provider LLM reads the draft reply + the tool results and
returns a terse list of concerns: unstated assumptions, claims not backed
by evidence, overreach. Concerns ALONE do not block the reply; concerns
plus a citation failure trigger revision.
"""

from __future__ import annotations

import json
import re

from llm_provider_py.types import ChatMessage, LLMProvider

from control_plane.agents.agent_kenny.types import AgentState

_LLM_TEMPERATURE = 0.0
_LLM_MAX_OUTPUT_TOKENS = 400
_CONCERN_LINE_RE = re.compile(r"^[\s\-\*•]*([^\n]+?)\s*$")


def _system_prompt() -> str:
    return (
        "You are an auditor reviewing an AI co-pilot's draft reply. Read the "
        "draft and any tool results provided. List concerns as a bulleted list: "
        "unstated assumptions, claims not supported by the evidence, "
        "overconfident generalizations, or factual leaps. Be terse — one line "
        "per concern. If you find nothing concerning, reply with exactly "
        "'NONE'. Do not rewrite the draft."
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


def parse_concerns(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.upper() == "NONE":
        return []
    concerns: list[str] = []
    for line in raw.splitlines():
        m = _CONCERN_LINE_RE.match(line)
        if not m:
            continue
        c = m.group(1).strip()
        if not c or c.upper() == "NONE":
            continue
        concerns.append(c[:300])
    return concerns


async def adversarial_review(provider: LLMProvider, state: AgentState) -> AgentState:
    """Run the second-pass auditor; populate ``state.adversarial_concerns``."""
    messages = _build_messages(state)
    raw = provider.chat_complete(
        messages,
        temperature=_LLM_TEMPERATURE,
        max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
    )
    state.adversarial_concerns = parse_concerns(raw)
    return state


__all__ = ["adversarial_review", "parse_concerns"]
