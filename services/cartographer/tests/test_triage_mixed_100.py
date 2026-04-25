"""Story 6.1 AC: 100 mixed events — relevant cluster passes; irrelevant cluster is triaged out."""

from __future__ import annotations

import uuid
from random import Random

import pytest

from cartographer.triage import EventSignals, TriageContext, triage_event

OBJECTIVES = (
    "Track NYC DOT deployment schedules and road stakeholder alignment.",
    "Surface transcript-derived action items for the deployment team.",
)
CTX = TriageContext(
    phase="P5_scale_execution",
    declared_objectives=OBJECTIVES,
    relevance_threshold=0.3,
)
RNG = Random(42)
IRRELEVANT = (
    "pizza",
    "lunch",
    "baseball",
    "holiday",
    "foo",
    "bar",
    "quux",
    "weather",
    "movie",
    "recipe",
    "game",
    "music",
    "random",
    "noise",
)
RELEVANT = (
    "nyc",
    "dot",
    "deployment",
    "schedule",
    "stakeholder",
    "transcript",
    "action",
    "items",
    "road",
    "alignment",
    "review",
    "meeting",
)


def _make_event(*, relevant: bool) -> EventSignals:
    eid = uuid.uuid4()
    if relevant:
        k = [RNG.choice(RELEVANT) for _ in range(5)]
        # Echo mission language so Jaccard + substring match align with declared objectives.
        body = (
            f"NYC DOT deployment schedules and road stakeholder alignment. "
            f"Transcript-derived action items for the deployment team. "
            f"Extra context: {' '.join(k)}."
        )
    else:
        k = [RNG.choice(IRRELEVANT) for _ in range(4)]
        body = f"Unrelated: {' '.join(k)} nothing about the mission."
    return EventSignals(
        event_id=eid,
        event_participants=(),
        event_keywords=tuple(k),
        text_blob=body,
    )


def test_100_mixed_triage_separates_clusters(monkeypatch: pytest.MonkeyPatch) -> None:
    """50 strong-relevant + 50 strong-irrelevant; expect large majority correct."""
    observed: list[str] = []

    def cap(*, tenant_id: str, phase: str, outcome: str) -> None:
        observed.append(outcome)

    monkeypatch.setattr("cartographer.triage.observe_triage", cap)

    passed = 0
    triaged = 0
    for _ in range(50):
        r = triage_event(CTX, _make_event(relevant=True), tenant_id="t-mix")
        if not r.triaged_out:
            passed += 1
    for _ in range(50):
        r = triage_event(CTX, _make_event(relevant=False), tenant_id="t-mix")
        if r.triaged_out:
            triaged += 1

    assert passed >= 45, f"expected most relevant to pass, got {passed}/50"
    assert triaged >= 45, f"expected most irrelevant triaged, got {triaged}/50"
    assert len(observed) == 100
    assert all(o in ("passed", "triaged_out") for o in observed)
