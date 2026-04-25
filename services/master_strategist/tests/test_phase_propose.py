"""Story 6-7: phase transition proposal bundle."""

from __future__ import annotations

import uuid

import pytest
from deployai_citation.citation import CitationEnvelopeV01, EvidenceSpanV01

from master_strategist.phase_propose import (
    build_control_plane_propose_body,
    build_phase_transition_bundle,
    should_propose_phase_transition,
)


def _env(n: uuid.UUID) -> CitationEnvelopeV01:
    return CitationEnvelopeV01(
        node_id=n,
        graph_epoch=0,
        evidence_span=EvidenceSpanV01(start=0, end=1, source_ref="urn:evidence"),
        retrieval_phase="cartographer",
        confidence_score=0.8,
        signed_timestamp="2026-01-15T12:00:00Z",
    )


def test_builds_bundle_and_api_body() -> None:
    tid = uuid.uuid4()
    e1, e2 = uuid.uuid4(), uuid.uuid4()
    b = build_phase_transition_bundle(
        tenant_id=tid,
        current_phase="P1_pre_engagement",
        target_phase="P2_discovery",
        evidence_events=(e1, e2),
        evidence_citations=(_env(e1), _env(e2)),
        proposer_agent="master_strategist",
        reason="readiness",
    )
    assert b is not None
    assert b.category == "phase_transition"
    body = build_control_plane_propose_body(b)
    assert body["from_phase"] == "P1_pre_engagement"
    assert body["to_phase"] == "P2_discovery"
    assert len(body["evidence_event_ids"]) == 2
    assert body["proposer_agent"] == "master_strategist"


def test_invalid_hop_returns_none() -> None:
    tid = uuid.uuid4()
    e1 = uuid.uuid4()
    out = build_phase_transition_bundle(
        tenant_id=tid,
        current_phase="P1_pre_engagement",
        target_phase="P5_pilot",  # skip
        evidence_events=(e1,),
        evidence_citations=(_env(e1),),
        proposer_agent="x",
        reason="nope",
    )
    assert out is None


def test_mismatched_evidence_lengths() -> None:
    with pytest.raises(ValueError, match="align"):
        build_phase_transition_bundle(
            tenant_id=uuid.uuid4(),
            current_phase="P1_pre_engagement",
            target_phase="P2_discovery",
            evidence_events=(uuid.uuid4(), uuid.uuid4()),
            evidence_citations=(_env(uuid.uuid4()),),
            proposer_agent="x",
            reason="y",
        )


def test_should_propose() -> None:
    assert should_propose_phase_transition(evidence_count=1, avg_confidence=0.9) is False
    assert should_propose_phase_transition(evidence_count=2, avg_confidence=0.6) is True
