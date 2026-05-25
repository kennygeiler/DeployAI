"""Single entry point for writing rows to ``strategist_activity_events``.

Phase F1.b: dual-emits onto ``ledger_events`` in the same transaction so
the existing audit-row consumers keep working while the timeline ledger
gets free coverage of every audit event (timeline-ledger.md §4.2).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.strategist_personal import StrategistActivityEvent
from control_plane.infra.metrics import audit_emit_failures_total
from control_plane.ledger import emit_ledger_event

_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_.]{0,79}$")
_SUMMARY_MIN = 1
_SUMMARY_MAX = 500


_CATEGORY_TO_SOURCE_KIND: dict[str, str] = {
    "tenant.webhook.created": "settings_change",
    "tenant.webhook.updated": "settings_change",
    "tenant.webhook.deleted": "settings_change",
    "tenant.webhook.rotated": "settings_change",
    "integration_kill_switch": "settings_change",
    "tenant.llm_config.updated": "settings_change",
    "tenant.prompt.updated": "settings_change",
    "engagement.phase.changed": "engagement_phase_change",
    "engagement.member.added": "member_added",
    "engagement.member.removed": "member_removed",
}

_CATEGORY_PREFIX_TO_SOURCE_KIND: tuple[tuple[str, str], ...] = (
    ("tenant.webhook.", "settings_change"),
    ("tenant.llm_config.", "settings_change"),
    ("tenant.prompt.", "settings_change"),
    ("engagement.member.", "member_added"),
)


def audit_category_to_source_kind(category: str) -> str:
    """Map an audit ``category`` slug to the ledger ``source_kind`` enum.

    Conservative: anything unrecognised falls through to ``audit_other`` so
    the ledger validator never rejects a real audit emit (timeline-ledger.md
    §4.2 — dual-emit must never break the existing audit path).
    """
    if category in _CATEGORY_TO_SOURCE_KIND:
        return _CATEGORY_TO_SOURCE_KIND[category]
    if category.startswith("engagement.member."):
        return "member_removed" if category.endswith(".removed") else "member_added"
    for prefix, kind in _CATEGORY_PREFIX_TO_SOURCE_KIND:
        if category.startswith(prefix):
            return kind
    return "audit_other"


async def emit_audit_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    category: str,
    summary: str,
    detail: dict[str, Any],
    ref_id: uuid.UUID | None = None,
) -> StrategistActivityEvent:
    try:
        if not _CATEGORY_RE.fullmatch(category):
            raise ValueError("category must match ^[a-z][a-z0-9_.]{0,79}$ (got: " + repr(category) + ")")
        if not isinstance(summary, str) or not (_SUMMARY_MIN <= len(summary) <= _SUMMARY_MAX):
            raise ValueError(f"summary length must be between {_SUMMARY_MIN} and {_SUMMARY_MAX} characters")
        if not isinstance(detail, dict):
            raise ValueError("detail must be a dict")

        row = StrategistActivityEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            category=category,
            summary=summary,
            detail=detail,
            ref_id=ref_id,
        )
        session.add(row)
        await session.flush()

        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=None,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id=str(actor_id),
            source_kind=audit_category_to_source_kind(category),
            source_ref=ref_id,
            summary=summary,
            detail={"audit_category": category, **detail},
        )
    except Exception:
        audit_emit_failures_total.inc()
        raise
    return row
