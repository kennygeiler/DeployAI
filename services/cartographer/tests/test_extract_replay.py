from __future__ import annotations

import uuid

import pytest

from cartographer.extract import ExtractionBundle, bundle_fingerprint, extract_stub
from cartographer.triage import EventSignals, TriageContext, TriageResult, triage_event


def _passing_triage(event: EventSignals) -> TriageResult:
    ctx = TriageContext(
        phase="P5_scale_execution",
        declared_objectives=("NYC DOT deployment and stakeholder work.",),
        relevance_threshold=0.2,
    )
    return triage_event(ctx, event, tenant_id="t1")


def test_extract_replay_fingerprint_stable() -> None:
    eid = uuid.uuid4()
    event = EventSignals(
        event_id=eid,
        event_keywords=(),
        text_blob="Meeting with NYC DOT about deployment. Jane Smith attended.",
    )
    t = _passing_triage(event)
    a = extract_stub(event, t)
    b = extract_stub(event, t)
    assert bundle_fingerprint(a) == bundle_fingerprint(b)
    assert a.entities == b.entities
    assert isinstance(a, ExtractionBundle)


def test_extract_rejects_triaged_out() -> None:
    eid = uuid.uuid4()
    event = EventSignals(event_id=eid, text_blob="x")
    bad = TriageResult(
        event_id=eid,
        relevance_score=0.0,
        outcome="triaged_out",
        triaged_out=True,
        reason="x",
        would_consume_extraction=False,
        log_fields={},
    )
    with pytest.raises(ValueError, match="triage-passed"):
        extract_stub(event, bad)
