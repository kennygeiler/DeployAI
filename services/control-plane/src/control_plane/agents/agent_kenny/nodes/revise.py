"""``revise_if_unverified`` — re-prompt the LLM after a bad citation.

Drops the most recent assistant draft, appends a corrective system note
that lists the offending ``[kind:UUID]`` tokens, and bumps
``revision_attempts`` so the runner caps the loop at
:data:`MAX_REVISION_ATTEMPTS` (scope-v2 §6.2 / §7.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from llm_provider_py.types import LLMProvider

from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    AgentState,
)


def should_revise(state: AgentState) -> bool:
    if state.citation_report is None:
        return False
    if state.revision_attempts >= MAX_REVISION_ATTEMPTS:
        return False
    return len(state.citation_report.not_found) > 0


async def revise_if_unverified(
    provider: LLMProvider,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
) -> AgentState:
    """Append a corrective message + re-call the LLM."""
    if not should_revise(state):
        return state
    bad = state.citation_report.not_found if state.citation_report else []
    bad_list = ", ".join(f"[{c.kind}:{c.identifier}]" for c in bad)
    state.messages.append(
        {
            "role": "user",
            "content": (
                "Your previous reply cited identifiers that do not resolve in this "
                f"engagement: {bad_list}. Please rewrite the reply removing these "
                "fabricated citations. Keep any citations that genuinely resolve "
                "to ledger / matrix / insight rows. If you cannot ground a claim "
                "in a verifiable id, drop the claim — do not invent another id."
            ),
        }
    )
    state.revision_attempts += 1
    # Wipe the last draft so the LLM is forced to recompute.
    state.accumulated_text = ""
    state.last_text = ""
    await call_llm_with_tools(provider, state, emit=emit)
    return state


__all__ = ["revise_if_unverified", "should_revise"]
