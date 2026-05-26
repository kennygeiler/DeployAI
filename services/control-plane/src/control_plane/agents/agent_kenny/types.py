"""Agent Kenny v2 state + stream types (scope-v2 §6).

The LangGraph state machine threads :class:`AgentState` through every
node. Each node returns a partial dict that LangGraph merges back in.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# scope-v2 §7.1
CITATION_RE = re.compile(
    r"\[(event|node|insight|turn|edge|slack|linear|gdrive|notion|github):"
    r"([0-9a-zA-Z][0-9a-zA-Z._-]{2,80})\]"
)
DB_CITATION_KINDS: frozenset[str] = frozenset({"event", "node", "insight", "turn", "edge"})
EXTERNAL_CITATION_KINDS: frozenset[str] = frozenset({"slack", "linear", "gdrive", "notion", "github"})

# scope-v2 §6.2 budgets.
MAX_TOOL_CALLS_PER_TURN = 8
MAX_REVISION_ATTEMPTS = 2
TURN_HARD_TIMEOUT_S = 60.0

CitationOutcome = Literal["verified", "cross_engagement_leak", "not_found", "external"]


@dataclass(frozen=True)
class ParsedCitation:
    """One ``[kind:identifier]`` parse result from a reply chunk."""

    kind: str
    identifier: str


@dataclass(frozen=True)
class VerifiedCitation:
    """Outcome of one citation lookup."""

    kind: str
    identifier: str
    outcome: CitationOutcome


@dataclass(frozen=True)
class CitationReport:
    """Aggregated citation verification result for one reply."""

    verified: list[VerifiedCitation] = field(default_factory=list)
    cross_engagement: list[VerifiedCitation] = field(default_factory=list)
    not_found: list[VerifiedCitation] = field(default_factory=list)
    external: list[VerifiedCitation] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.verified) + len(self.cross_engagement) + len(self.not_found) + len(self.external)


@dataclass
class AgentState:
    """LangGraph state object threaded through every node.

    Mutable: nodes update in-place when they return a partial dict via the
    LangGraph runtime, but the unit + integration tests also pass this
    around manually for direct calls.
    """

    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    actor_user_id: uuid.UUID
    user_message: str
    started_at: datetime
    conversation_id: uuid.UUID | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    initial_context: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    last_text: str = ""
    accumulated_text: str = ""
    tool_calls_made: int = 0
    revision_attempts: int = 0
    citation_report: CitationReport | None = None
    adversarial_concerns: list[str] = field(default_factory=list)
    final_text: str = ""
    final_turn_id: uuid.UUID | None = None
    final_conversation_id: uuid.UUID | None = None
    final_tokens: int = 0
    security_rejected: bool = False
    error: str | None = None


# Stream chunk discriminated union.
@dataclass(frozen=True)
class ThinkingChunk:
    content: str


@dataclass(frozen=True)
class ToolCallChunk:
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResultChunk:
    name: str
    row_count: int
    truncated: bool
    error: str | None = None


@dataclass(frozen=True)
class DeltaChunk:
    content: str


@dataclass(frozen=True)
class CitationVerifiedChunk:
    kind: str
    identifier: str


@dataclass(frozen=True)
class CitationUnverifiedChunk:
    kind: str
    identifier: str
    outcome: CitationOutcome


@dataclass(frozen=True)
class DoneChunk:
    turn_id: uuid.UUID
    conversation_id: uuid.UUID
    tokens: int
    tool_calls: int
    revision_attempts: int
    adversarial_concerns: int
    final_text: str


@dataclass(frozen=True)
class ErrorChunk:
    error: str


StreamChunk = (
    ThinkingChunk
    | ToolCallChunk
    | ToolResultChunk
    | DeltaChunk
    | CitationVerifiedChunk
    | CitationUnverifiedChunk
    | DoneChunk
    | ErrorChunk
)


def parse_citations(text: str) -> list[ParsedCitation]:
    """Extract all ``[kind:id]`` citations from ``text``.

    Deduplicated by (kind, identifier) preserving first-occurrence order.
    """
    seen: set[tuple[str, str]] = set()
    out: list[ParsedCitation] = []
    for m in CITATION_RE.finditer(text):
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        out.append(ParsedCitation(kind=m.group(1), identifier=m.group(2)))
    return out


def is_uuid_identifier(identifier: str) -> bool:
    try:
        uuid.UUID(identifier)
    except ValueError:
        return False
    return True


def filter_db_citations(citations: Iterable[ParsedCitation]) -> list[ParsedCitation]:
    """Return only the citations whose kind belongs to a DeployAI table."""
    return [c for c in citations if c.kind in DB_CITATION_KINDS]


class BudgetExhaustedError(Exception):
    """Daily LLM budget cannot fund this turn."""


class CrossEngagementLeakError(Exception):
    """Reply cited a UUID from a different engagement — SECURITY incident."""


class ConversationNotFoundError(Exception):
    """Caller referenced a conversation that does not exist for this engagement."""


__all__ = [
    "CITATION_RE",
    "DB_CITATION_KINDS",
    "EXTERNAL_CITATION_KINDS",
    "MAX_REVISION_ATTEMPTS",
    "MAX_TOOL_CALLS_PER_TURN",
    "TURN_HARD_TIMEOUT_S",
    "AgentState",
    "BudgetExhaustedError",
    "CitationOutcome",
    "CitationReport",
    "CitationUnverifiedChunk",
    "CitationVerifiedChunk",
    "ConversationNotFoundError",
    "CrossEngagementLeakError",
    "DeltaChunk",
    "DoneChunk",
    "ErrorChunk",
    "ParsedCitation",
    "StreamChunk",
    "ThinkingChunk",
    "ToolCallChunk",
    "ToolResultChunk",
    "VerifiedCitation",
    "filter_db_citations",
    "is_uuid_identifier",
    "parse_citations",
]
