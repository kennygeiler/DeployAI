"""Agent Kenny tool layer (v2 Phase 1, scope-v2 §5).

Twelve pure-function tools every call site of Agent Kenny v2 uses to read
from the engagement substrate, plus one write tool (``propose_action``)
that pushes a human-review item onto ``strategist_action_queue_items``.

Every tool returns a :class:`ToolResult` carrying the rows it surfaced,
the citation UUIDs they cite, a truncation flag, and an optional
``next_cursor`` for paginated tools. Tools never raise on empty results
— they return ``rows=[], citations=[]``. They DO raise :class:`ToolError`
for missing tenant / engagement scoping or malformed inputs.

Each tool module registers itself with :data:`TOOL_REGISTRY` on import so
the LangGraph runtime in Phase 2 can enumerate tools without an explicit
list. The registry value is the Anthropic tool-use JSON-schema shape
(``{"name": ..., "description": ..., "input_schema": {...}}``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

CitationKind = Literal["event", "node", "insight", "turn", "edge"]


@dataclass(frozen=True)
class Citation:
    """One UUID Agent Kenny may cite back, kinded by table of origin."""

    kind: CitationKind
    id: uuid.UUID


@dataclass(frozen=True)
class ToolResult:
    """Return value from every tool call. ``rows`` is JSON-serializable."""

    name: str
    rows: list[dict[str, Any]]
    citations: list[Citation] = field(default_factory=list)
    truncated: bool = False
    next_cursor: str | None = None
    duration_ms: float = 0.0
    detail: str | None = None


class ToolError(ValueError):
    """Raised for malformed input, missing scoping, or cross-tenant misuse.

    Tools NEVER raise on empty result sets — they return ``rows=[]``. This
    exception is reserved for caller-error conditions that should surface to
    the LangGraph runtime so it can either revise the LLM input or fail the
    turn loudly.
    """


@dataclass(frozen=True)
class ToolSpec:
    """One entry in :data:`TOOL_REGISTRY`. Matches Anthropic's tool-use shape."""

    name: str
    description: str
    input_schema: dict[str, Any]


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    """Register a tool with the global registry. Re-registration is a bug."""
    if spec.name in TOOL_REGISTRY:
        raise ValueError(f"tool {spec.name!r} is already registered")
    TOOL_REGISTRY[spec.name] = spec


def _ensure_uuid(value: Any, field_name: str) -> uuid.UUID:
    """Coerce ``value`` into ``uuid.UUID`` or raise :class:`ToolError`."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise ToolError(f"{field_name} is not a valid UUID: {value!r}") from exc
    raise ToolError(f"{field_name} must be a UUID or UUID string, got {type(value).__name__}")


def _require_scope(*, tenant_id: Any, engagement_id: Any) -> tuple[uuid.UUID, uuid.UUID]:
    """Every tool needs both scopes; this is the single validation seam."""
    if tenant_id is None:
        raise ToolError("tenant_id is required")
    if engagement_id is None:
        raise ToolError("engagement_id is required")
    return _ensure_uuid(tenant_id, "tenant_id"), _ensure_uuid(engagement_id, "engagement_id")


# Side-effect imports — each module calls :func:`register_tool` at import time
# so any caller that imports ``control_plane.agents.tools`` gets a fully
# populated :data:`TOOL_REGISTRY`. Keep these at the bottom to avoid cycles.
from control_plane.agents.tools import (  # noqa: E402,F401,I001
    ledger as ledger_tools,
    matrix as matrix_tools,
    synthesis as synthesis_tools,
    analysis,
    search,
    escalate,
)

__all__ = [
    "TOOL_REGISTRY",
    "Citation",
    "CitationKind",
    "ToolError",
    "ToolResult",
    "ToolSpec",
    "register_tool",
]
