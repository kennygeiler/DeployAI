"""Extraction queue boundary: FR16 thread- or session-unit only (no per-message units).

``Cartographer`` (Epic 6) may only consume events that pass :func:`validate_extraction_queue_event`.
"""

from __future__ import annotations

from typing import Final, Literal, TypedDict

# Thread-level: one canonical row = full email thread (not per message).
THREAD_LEVEL_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "email.thread",
    }
)

# Session-level: one canonical row = one meeting / session (transcript, upload, single calendar event).
SESSION_LEVEL_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "meeting.transcript",
        "upload.transcript",
        "calendar.event",
    }
)

# Explicit per-message types (rejected; FR16).
_PER_MESSAGE_EXPLICIT: Final[frozenset[str]] = frozenset(
    {
        "email.message",
    }
)

ExtractionUnitKind = Literal["thread", "session"]


class _AuditRecordBase(TypedDict, total=False):
    audit_event: str
    event_type: str
    tenant_id: str | None
    canonical_event_id: str | None
    reason: str


def per_message_rejection_audit_record(
    *,
    event_type: str,
    tenant_id: str | None = None,
    canonical_event_id: str | None = None,
) -> _AuditRecordBase:
    """Structured record for an audit / observability line when a per-message event is rejected."""
    return {
        "audit_event": "ingestion.extraction_rejected_per_message_unit",
        "event_type": event_type,
        "tenant_id": tenant_id,
        "canonical_event_id": canonical_event_id,
        "reason": ("FR16: thread- or session-level units only; per-message events are blocked at extraction boundary"),
    }


class ExtractionUnitError(ValueError):
    """``event_type`` is not a permitted thread- or session-level extraction unit."""


class PerMessageExtractionError(ExtractionUnitError):
    """A per-message (or *message-suffixed) event must not enter the Cartographer extraction queue."""


def _is_per_message_type(event_type: str) -> bool:
    t = (event_type or "").strip()
    if not t:
        return True
    if t in _PER_MESSAGE_EXPLICIT:
        return True
    if t.endswith(".message") and t not in THREAD_LEVEL_EVENT_TYPES:
        return True
    return False


def validate_extraction_queue_event(*, event_type: str) -> ExtractionUnitKind:
    """Return ``'thread'`` or ``'session'`` for a permitted :paramref:`event_type`, else raise.

    Callers publishing to the extraction queue (consumed by Cartographer, Epic 6) must
    run this for every event; per-message email units are architecturally rejected (FR16).
    """
    if not (event_type or "").strip():
        raise ExtractionUnitError("event_type is empty")

    t = (event_type or "").strip()
    if _is_per_message_type(t):
        raise PerMessageExtractionError(
            f"per-message event_type {t!r} is not a valid extraction unit (use email.thread, etc.)"
        )
    if t in THREAD_LEVEL_EVENT_TYPES:
        return "thread"
    if t in SESSION_LEVEL_EVENT_TYPES:
        return "session"
    raise ExtractionUnitError(
        f"event_type {t!r} is not a known thread- or session-level extraction unit; "
        "refuse the generic extraction queue or extend THREAD_LEVEL_EVENT_TYPES / SESSION_LEVEL_EVENT_TYPES",
    )
