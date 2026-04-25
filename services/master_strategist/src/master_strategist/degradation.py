"""Agent graceful-degradation contract types (FR46, NFR11, NFR73; Story 6-8).

Surfaces (Epic 8+) consume canonical memory / event log entries with this shape when an
agent fails. OpenTelemetry and Prometheus hooks live in :mod:`master_strategist.metrics`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AgentErrorCode = Literal[
    "llm_timeout",
    "llm_error",
    "retrieval_failed",
    "extraction_exception",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class AgentErrorState:
    """Terminal error state for LangGraph or worker surfaces (explicit, non-silent)."""

    error_code: AgentErrorCode
    retry_possible: bool
    user_message: str
    detail: str = ""
    """Non-user-facing detail for logs / traces only."""


def agent_error_to_canonical_payload(err: AgentErrorState) -> dict[str, Any]:
    """JSON-friendly payload for a canonical memory ``agent.error``-style event."""
    return {
        "error_code": err.error_code,
        "retry_possible": err.retry_possible,
        "user_message": err.user_message,
        "has_detail": bool(err.detail),
    }
