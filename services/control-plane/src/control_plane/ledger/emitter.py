"""Single entry point for appending rows onto ``ledger_events``.

See ``docs/design/timeline-ledger.md`` §4 — the caller (route handler or
service helper) owns the surrounding transaction. ``emit_ledger_event``
does ``session.add`` + ``flush`` only so a rollback drops the ledger row
in lockstep with whatever state change provoked it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import (
    LedgerEvent,
    LedgerEventAffects,
    LedgerEventCause,
)

ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "email_ingest",
        "meeting_webhook",
        "manual_capture",
        "llm_proposal_created",
        "proposal_accepted",
        "proposal_rejected",
        "matrix_node_created",
        "matrix_node_updated",
        "matrix_node_deleted",
        "matrix_edge_created",
        "matrix_edge_deleted",
        "insight_opened",
        "insight_closed",
        "recommendation_emitted",
        "recommendation_actioned",
        "engagement_phase_change",
        "member_added",
        "member_removed",
        "settings_change",
        "audit_other",
        "oracle_chat_turn",
        "oracle_conversation_started",
    }
)

ALLOWED_AFFECT_KINDS: frozenset[str] = frozenset({"matrix_node", "matrix_edge", "insight", "recommendation"})

_SUMMARY_MIN = 1
_SUMMARY_MAX = 500

# Detail keys we never want to land in the ledger — same posture as the
# audit emit hygiene rule (see timeline-ledger.md §9.2).
_SECRET_KEY_NEEDLES: tuple[str, ...] = (
    "api_key",
    "apikey",
    "signing_secret",
    "client_secret",
    "secret",
    "webhook_url",
    "bearer_token",
    "access_token",
    "refresh_token",
    "password",
    "private_key",
)

AffectsEntry = tuple[str, uuid.UUID]


async def emit_ledger_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    source_ref: uuid.UUID | None,
    summary: str,
    detail: dict[str, Any],
    caused_by: Iterable[uuid.UUID] = (),
    affects: Iterable[AffectsEntry] = (),
) -> LedgerEvent:
    """Append one ledger row plus its cause / affect edges in a single flush.

    Caller commits. Validates ``source_kind`` against the enum from design §3.1
    and strips secret-shaped keys from ``detail`` defensively.
    """
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError(f"invalid source_kind: {source_kind!r}")
    if not isinstance(summary, str) or not (_SUMMARY_MIN <= len(summary) <= _SUMMARY_MAX):
        raise ValueError(f"summary length must be between {_SUMMARY_MIN} and {_SUMMARY_MAX} characters")
    if not isinstance(actor_kind, str) or not actor_kind:
        raise ValueError("actor_kind must be a non-empty string")
    if not isinstance(detail, dict):
        raise ValueError("detail must be a dict")

    sanitised = _scrub_secrets(detail)

    row = LedgerEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=occurred_at,
        actor_kind=actor_kind,
        actor_id=actor_id,
        source_kind=source_kind,
        source_ref=source_ref,
        summary=summary,
        detail=sanitised,
    )
    session.add(row)
    await session.flush()

    for parent_id in caused_by:
        if parent_id == row.id:
            continue  # self-cause is a schema CHECK; skip defensively
        session.add(LedgerEventCause(event_id=row.id, caused_by_id=parent_id))

    for entity_kind, entity_id in affects:
        if entity_kind not in ALLOWED_AFFECT_KINDS:
            raise ValueError(f"invalid affect entity_kind: {entity_kind!r}")
        session.add(LedgerEventAffects(event_id=row.id, entity_kind=entity_kind, entity_id=entity_id))

    if caused_by or affects:
        await session.flush()
    return row


def _scrub_secrets(detail: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``detail`` with secret-shaped keys removed.

    Recurses one level into nested dicts and into lists of dicts so callers
    that nest under ``connection`` / ``config`` don't leak through.
    """
    cleaned: dict[str, Any] = {}
    for key, value in detail.items():
        if _looks_secret(key):
            continue
        if isinstance(value, dict):
            cleaned[key] = _scrub_secrets(value)
        elif isinstance(value, list):
            cleaned[key] = [_scrub_secrets(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _looks_secret(key: str) -> bool:
    needle = key.lower()
    return any(token in needle for token in _SECRET_KEY_NEEDLES)
