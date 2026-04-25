"""Branch coverage for extract.py (chunking, stub heuristics, persist, dedupe)."""

from __future__ import annotations

import uuid

from cartographer.extract import (
    ExtractionBundle,
    _dedupe,
    _stub_blockers,
    _stub_learnings,
    bundle_fingerprint,
    chunk_by_paragraphs,
    extract_stub,
    extraction_bundle_to_persist_dict,
)
from cartographer.triage import EventSignals, TriageContext, TriageResult, triage_event


def _passing_triage(e: EventSignals) -> TriageResult:
    return triage_event(
        TriageContext(
            phase="P5_scale_execution",
            declared_objectives=("NYC DOT",),
            relevance_threshold=0.1,
        ),
        e,
        tenant_id="t",
    )


def test_chunk_by_paragraphs_empty() -> None:
    assert chunk_by_paragraphs("   \n  ") == [(0, "")]


def test_chunk_by_paragraphs_splits_long_text() -> None:
    s = "word " * 2000
    segs = chunk_by_paragraphs(s, max_chars=40)
    assert len(segs) >= 2
    assert all(c for _, c in segs)


def test_chunk_single_segment_smaller_than_max() -> None:
    assert chunk_by_paragraphs("Short text.") == [(0, "Short text.")]


def test_extract_stub_empty_text_returns_empty_bundle() -> None:
    eid = uuid.uuid4()
    e = EventSignals(event_id=eid, text_blob="   ", event_keywords=())
    t = TriageResult(
        event_id=eid,
        relevance_score=1.0,
        outcome="passed",
        triaged_out=False,
        reason="fixture",
        would_consume_extraction=True,
        log_fields={},
    )
    b = extract_stub(e, t)
    assert b.full_text == ""
    assert b.entities == ()


def test_blocker_and_learning_heuristics() -> None:
    eid = uuid.uuid4()
    e = EventSignals(
        event_id=eid,
        text_blob=(
            "Meeting with Jane Smith and NYC DOT. We are blocked on permits. "
            "A lesson learned: prefer early design review."
        ),
    )
    t = _passing_triage(e)
    b = extract_stub(e, t)
    assert b.blockers
    assert b.candidate_learnings
    p = extraction_bundle_to_persist_dict(b)
    assert p["blockers"]
    assert p["candidate_learnings"]


def test_dedupe_skips_second_identical() -> None:
    from cartographer.extract import ExtractedEntity, _envelope

    eid = uuid.uuid4()
    ev = _envelope(eid, chunk_index=0, label="dup", start=0, end=3, graph_epoch=0)
    ent = ExtractedEntity(
        label="Same",
        kind="other",
        evidence_span=ev.evidence_span,
        envelope=ev,
    )
    d = _dedupe([ent, ent])
    assert len(d) == 1


def test_persist_serialization_includes_blockers() -> None:
    eid = uuid.uuid4()
    b = _stub_blockers("We are blocked on this.", eid, 0)
    learn = _stub_learnings("A lesson learned from prior work", eid, 0)
    bundle = ExtractionBundle(
        source_event_id=eid,
        graph_epoch=0,
        full_text="x",
        entities=(),
        relationships=(),
        blockers=b,
        candidate_learnings=learn,
    )
    p = extraction_bundle_to_persist_dict(bundle)
    assert len(p["blockers"]) == 1
    assert len(p["candidate_learnings"]) == 1
    assert p["entity_count"] == 0


def test_bundle_fingerprint_includes_blockers() -> None:
    eid = uuid.uuid4()
    b = _stub_blockers("blocking issue here", eid, 0)
    bundle = ExtractionBundle(
        source_event_id=eid,
        graph_epoch=0,
        full_text="x",
        entities=(),
        relationships=(),
        blockers=b,
        candidate_learnings=(),
    )
    assert len(bundle_fingerprint(bundle)) == 64
