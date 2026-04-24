"""Story 3-5: extraction queue enforces thread/session units (FR16)."""

from __future__ import annotations

import pytest

from ingest.validators import (
    ExtractionUnitError,
    PerMessageExtractionError,
    per_message_rejection_audit_record,
    validate_extraction_queue_event,
)


def test_reject_per_message_event() -> None:
    with pytest.raises(PerMessageExtractionError, match="per-message"):
        validate_extraction_queue_event(event_type="email.message")

    with pytest.raises(PerMessageExtractionError):
        validate_extraction_queue_event(event_type="graph.draft.message")

    with pytest.raises(ExtractionUnitError, match="empty"):
        validate_extraction_queue_event(event_type="  ")


def test_accept_thread_unit_event() -> None:
    assert validate_extraction_queue_event(event_type="email.thread") == "thread"


def test_accept_session_unit_events() -> None:
    for et in (
        "meeting.transcript",
        "upload.transcript",
        "asr.transcript",
        "calendar.event",
    ):
        assert validate_extraction_queue_event(event_type=et) == "session"


def test_reject_non_extraction_event_types() -> None:
    with pytest.raises(ExtractionUnitError, match="not a known thread"):
        validate_extraction_queue_event(event_type="meeting.held")
    with pytest.raises(ExtractionUnitError, match="not a known thread"):
        validate_extraction_queue_event(event_type="decision.recorded")


def test_per_message_rejection_audit_shape() -> None:
    a = per_message_rejection_audit_record(
        event_type="email.message",
        tenant_id="t1",
        canonical_event_id="e1",
    )
    assert a["audit_event"] == "ingestion.extraction_rejected_per_message_unit"
    assert a["event_type"] == "email.message"
    assert a["tenant_id"] == "t1"
    assert a["canonical_event_id"] == "e1"
    assert "FR16" in (a.get("reason") or "")
