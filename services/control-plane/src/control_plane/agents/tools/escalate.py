"""Escalation tool: ``propose_action`` — the only write tool in Phase 1.

Inserts one ``strategist_action_queue_items`` row for human review and
emits a ``propose_action`` ledger event. Caller (LangGraph node) owns the
surrounding transaction — the helper does ``session.add`` + ``flush``
and lets the agent loop decide when to commit.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.tools import (
    Citation,
    ToolError,
    ToolResult,
    ToolSpec,
    _ensure_uuid,
    _require_scope,
    register_tool,
)
from control_plane.agents.tools.audit import emit_tool_invocation, hash_tool_input
from control_plane.domain.strategist_queues import StrategistActionQueueItem
from control_plane.ledger import emit_ledger_event

_ALLOWED_PRIORITIES = ("low", "medium", "high")
_DEFAULT_PHASE = "P2_active"


PROPOSE_ACTION_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "minLength": 1, "maxLength": 2000},
        "priority": {"type": "string", "enum": list(_ALLOWED_PRIORITIES)},
        "phase": {"type": "string"},
        "evidence_node_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
        },
        "evidence_event_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
        },
        "rationale": {"type": "string"},
    },
    "required": ["description", "priority"],
}


async def propose_action(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    description: str,
    priority: str,
    phase: str = _DEFAULT_PHASE,
    evidence_node_ids: list[str] | tuple[str, ...] | None = None,
    evidence_event_ids: list[str] | tuple[str, ...] | None = None,
    rationale: str | None = None,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Insert one action-queue row for human review + emit ``propose_action`` ledger."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not description or not description.strip():
        raise ToolError("description must be non-empty")
    if priority not in _ALLOWED_PRIORITIES:
        raise ToolError(f"priority must be one of {_ALLOWED_PRIORITIES}, got {priority!r}")
    if len(description) > 2000:
        raise ToolError("description must be <= 2000 chars")

    node_ids_str = [str(_ensure_uuid(n, "evidence_node_ids[]")) for n in (evidence_node_ids or [])]
    event_ids_str = [str(_ensure_uuid(e, "evidence_event_ids[]")) for e in (evidence_event_ids or [])]

    now = datetime.now(UTC)
    item_id = f"kenny-{uuid.uuid4()}"
    row = StrategistActionQueueItem(
        id=item_id,
        tenant_id=tid,
        engagement_id=eid,
        priority=priority,
        phase=phase,
        description=description.strip(),
        status="pending",
        claimed_by=None,
        updated_at=now,
        source="agent_kenny",
        evidence_node_ids=node_ids_str,
        resolution_reason=None,
        evidence_event_ids={"event_ids": event_ids_str} if event_ids_str else None,
    )
    session.add(row)
    await session.flush()

    detail: dict[str, Any] = {
        "action_queue_item_id": item_id,
        "priority": priority,
        "phase": phase,
        "evidence_node_ids": node_ids_str,
        "evidence_event_ids": event_ids_str,
    }
    if rationale:
        detail["rationale"] = rationale[:1000]
    if turn_id is not None:
        detail["turn_id"] = str(turn_id)
    ledger_row = await emit_ledger_event(
        session,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=now,
        actor_kind="agent",
        actor_id="kenny",
        source_kind="propose_action",
        source_ref=None,
        summary=f"propose_action: {description.strip()[:200]}",
        detail=detail,
    )

    citations: list[Citation] = [Citation(kind="event", id=ledger_row.id)]
    for nid_str in node_ids_str:
        try:
            citations.append(Citation(kind="node", id=uuid.UUID(nid_str)))
        except ValueError:
            continue
    for eid_str in event_ids_str:
        try:
            citations.append(Citation(kind="event", id=uuid.UUID(eid_str)))
        except ValueError:
            continue

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="propose_action",
            input_hash=hash_tool_input(
                {
                    "description": description,
                    "priority": priority,
                    "phase": phase,
                    "evidence_node_ids": node_ids_str,
                    "evidence_event_ids": event_ids_str,
                    "rationale": rationale,
                }
            ),
            tenant_id=tid,
            engagement_id=eid,
            row_count=1,
            duration_ms=duration_ms,
            turn_id=turn_id,
        )

    return ToolResult(
        name="propose_action",
        rows=[
            {
                "action_queue_item_id": item_id,
                "ledger_event_id": str(ledger_row.id),
                "priority": priority,
                "phase": phase,
                "description": description.strip(),
                "status": "pending",
            }
        ],
        citations=citations,
        truncated=False,
        next_cursor=None,
        duration_ms=duration_ms,
    )


register_tool(
    ToolSpec(
        name="propose_action",
        description=(
            "Push a human-review action onto the strategist action queue. The only "
            "write tool in Agent Kenny's Phase 1 layer."
        ),
        input_schema=PROPOSE_ACTION_INPUT_SCHEMA,
    )
)


__all__ = ["PROPOSE_ACTION_INPUT_SCHEMA", "propose_action"]
