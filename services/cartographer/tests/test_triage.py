from __future__ import annotations

import logging
import uuid

import pytest

from cartographer.triage import EventSignals, TriageContext, score_relevance, triage_event


def test_score_zero_without_objectives() -> None:
    ctx = TriageContext(phase="P1_pre_engagement", declared_objectives=())
    ev = EventSignals(
        event_id=uuid.uuid4(),
        event_keywords=("deployment", "nyc"),
        text_blob="deployment schedule NYC",
    )
    assert score_relevance(ctx, ev) == 0.0


def test_passes_when_keywords_align() -> None:
    ctx = TriageContext(
        phase="P5_scale_execution",
        declared_objectives=(
            "Coordinate deployment schedules with NYC DOT stakeholders.",
            "Review meeting transcripts for action items.",
        ),
    )
    ev = EventSignals(
        event_id=uuid.uuid4(),
        event_participants=("jane@dot.nyc.gov",),
        event_keywords=("deployment", "schedule", "nyc", "transcript"),
        text_blob="Deployment schedule review for NYC DOT with stakeholders",
    )
    assert score_relevance(ctx, ev) >= 0.4


def test_triage_out_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, str, str]] = []

    def cap(tenant_id: str, phase: str, outcome: str) -> None:
        called.append((tenant_id, phase, outcome))

    monkeypatch.setattr("cartographer.triage.observe_triage", cap)
    ctx = TriageContext(
        phase="P1_pre_engagement",
        declared_objectives=("only specific dot keywords here",),
        relevance_threshold=0.9,
    )
    ev = EventSignals(
        event_id=uuid.uuid4(),
        event_keywords=("unrelated", "foobar", "xyzzy"),
        text_blob="coffee shop lunch",
    )
    r = triage_event(ctx, ev, tenant_id="t-1")
    assert r.triaged_out
    assert r.outcome == "triaged_out"
    assert not r.would_consume_extraction
    assert called == [("t-1", "P1_pre_engagement", "triaged_out")]


def test_triage_pass_increments_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def cap(*, tenant_id: str, phase: str, outcome: str) -> None:
        called.append(outcome)

    monkeypatch.setattr("cartographer.triage.observe_triage", cap)
    ctx = TriageContext(
        phase="P4_validation",
        declared_objectives=("NYC DOT deployment schedule coordination", "stakeholder transcripts"),
    )
    ev = EventSignals(
        event_id=uuid.uuid4(),
        event_keywords=("nyc", "dot", "deployment", "schedule", "stakeholder", "transcript"),
        text_blob="NYC DOT deployment schedule with stakeholders and transcript review",
    )
    r = triage_event(ctx, ev, tenant_id="acme")
    assert not r.triaged_out
    assert r.outcome == "passed"
    assert r.would_consume_extraction
    assert called == ["passed"]


def test_triage_context_relevance_threshold_out_of_range() -> None:
    with pytest.raises(ValueError, match="relevance_threshold"):
        TriageContext(phase="P1", declared_objectives=("a",), relevance_threshold=1.1)


def test_triage_log_json_uses_hashed_event_and_tenant(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO, logger="cartographer.triage")
    monkeypatch.setenv("DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_JSON", "1")
    monkeypatch.delenv("DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_IDENTIFIERS", raising=False)
    eid = uuid.uuid4()
    ev = EventSignals(
        event_id=eid,
        event_keywords=("nyc", "dot", "deployment"),
        text_blob="NYC DOT deployment work",
    )
    ctx = TriageContext(phase="P5", declared_objectives=("deployment",))
    r = triage_event(ctx, ev, tenant_id="acme-tenant")
    assert not r.triaged_out
    assert str(eid) not in caplog.text
    assert "acme-tenant" not in caplog.text
    assert "cartographer_triage" in caplog.text


def test_triage_log_json_raw_identifiers(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO, logger="cartographer.triage")
    monkeypatch.setenv("DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_JSON", "1")
    monkeypatch.setenv("DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_IDENTIFIERS", "raw")
    eid = uuid.uuid4()
    ev = EventSignals(event_id=eid, text_blob="NYC", event_keywords=("nyc",))
    ctx = TriageContext(phase="P1", declared_objectives=("nyc",))
    triage_event(ctx, ev, tenant_id="raw-tenant")
    assert str(eid) in caplog.text
    assert "raw-tenant" in caplog.text


def test_from_event_dict_accepts_uuid_instance() -> None:
    eid = uuid.uuid4()
    ev = EventSignals.from_event_dict({"id": eid, "body": "x"})
    assert ev.event_id == eid


def test_event_from_dict_mapping() -> None:
    eid = uuid.uuid4()
    raw = {
        "id": str(eid),
        "participants": ["maya@example.com"],
        "keywords": ["kickoff"],
        "subject": "Kickoff meeting",
        "body": "Discussion of deployment",
    }
    ev = EventSignals.from_event_dict(raw)
    assert ev.event_id == eid
    assert "kickoff" in ev.event_keywords
    assert "deployment" in ev.text_blob.lower()


def test_from_event_dict_invalid_id_string_uses_fresh_uuid() -> None:
    ev = EventSignals.from_event_dict({"id": "this-is-not-a-uuid", "body": "hello world there"})
    assert isinstance(ev.event_id, uuid.UUID)


def test_from_event_dict_missing_id_uses_fresh_uuid() -> None:
    a = EventSignals.from_event_dict({"body": "hello world there"})
    b = EventSignals.from_event_dict({"body": "hello world there"})
    assert a.event_id != b.event_id


def test_from_event_dict_participants_not_list_coerced() -> None:
    eid = uuid.uuid4()
    ev = EventSignals.from_event_dict(
        {
            "id": str(eid),
            "participants": 12345,
            "body": "text",
        },
    )
    assert ev.event_id == eid
    assert ev.event_participants == ()


def test_from_event_dict_keywords_not_list_coerced() -> None:
    eid = uuid.uuid4()
    ev = EventSignals.from_event_dict(
        {
            "id": str(eid),
            "event_keywords": "ignored-not-iterable-right-type",
            "body": "hello",
        },
    )
    assert ev.event_keywords == ()


def test_from_event_dict_event_participants_key() -> None:
    eid = uuid.uuid4()
    ev = EventSignals.from_event_dict(
        {
            "id": str(eid),
            "event_participants": ["a@b.com"],
            "body": "x",
        },
    )
    assert "a@b.com" in ev.event_participants
