from __future__ import annotations

import uuid
from typing import Any

import pytest

from cartographer.llm_extract import extract_map_reduce_llm
from cartographer.triage import EventSignals, TriageContext, TriageResult, triage_event


def test_llm_extract_uses_completer_json() -> None:
    eid = uuid.uuid4()
    event = EventSignals(
        event_id=eid,
        text_blob="Contact NYC DOT for the deployment schedule.",
    )
    ctx = TriageContext(
        phase="P5_scale_execution",
        declared_objectives=("NYC DOT deployment",),
        relevance_threshold=0.1,
    )
    triage = triage_event(ctx, event, tenant_id="t")

    def completer(_chunk: str) -> str:
        return '{"entities":[{"label":"NYC DOT","kind":"organization","span_text":"NYC DOT"}]}'

    b = extract_map_reduce_llm(event, triage, completer=completer)
    assert len(b.entities) >= 1
    assert any("NYC" in e.label for e in b.entities)


def test_llm_extract_default_path_anthropic_class_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover default Anthropic completer by patching ``AnthropicProvider.chat_complete`` (no API)."""
    eid = uuid.uuid4()
    event = EventSignals(
        event_id=eid,
        text_blob="Contact NYC DOT for the deployment schedule.",
    )
    ctx = TriageContext(
        phase="P5_scale_execution",
        declared_objectives=("NYC DOT deployment",),
        relevance_threshold=0.1,
    )
    triage = triage_event(ctx, event, tenant_id="t")

    def _fake_chat_complete(
        self: Any,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        return '{"entities":[{"label":"NYC DOT","kind":"organization","span_text":"NYC DOT"}]}'

    monkeypatch.setattr(
        "llm_provider_py.anthropic.AnthropicProvider.chat_complete",
        _fake_chat_complete,
    )
    b = extract_map_reduce_llm(event, triage, completer=None)
    assert len(b.entities) >= 1
    assert any("NYC" in e.label for e in b.entities)


def _event_and_triage() -> tuple[EventSignals, TriageResult]:
    eid = uuid.uuid4()
    e = EventSignals(event_id=eid, text_blob="NYC DOT meeting.", event_keywords=())
    t = triage_event(
        TriageContext(phase="P5", declared_objectives=("nyc",), relevance_threshold=0.1),
        e,
        tenant_id="t",
    )
    return e, t


def test_llm_invalid_json_returns_no_entities() -> None:
    e, triage = _event_and_triage()

    b = extract_map_reduce_llm(e, triage, completer=lambda _c: "not json {{{")
    assert b.entities == ()


def test_llm_entities_not_list_skipped() -> None:
    e, triage = _event_and_triage()
    b = extract_map_reduce_llm(e, triage, completer=lambda _c: '{"entities":"bad"}')
    assert b.entities == ()


def test_llm_empty_event_text() -> None:
    eid = uuid.uuid4()
    e = EventSignals(event_id=eid, text_blob="   ", event_keywords=())
    tr = TriageResult(
        event_id=eid,
        relevance_score=1.0,
        outcome="passed",
        triaged_out=False,
        reason="fixture",
        would_consume_extraction=True,
        log_fields={},
    )
    b = extract_map_reduce_llm(e, tr, completer=lambda c: f'{{"entities":[{{"label":"x","span_text":{c!r} }}]}}')
    assert b.full_text == ""
    assert b.entities == ()


def test_llm_span_match_case_insensitive() -> None:
    eid = uuid.uuid4()
    e = EventSignals(event_id=eid, text_blob="The nyc dot team is here.", event_keywords=())
    t = triage_event(
        TriageContext(phase="P5", declared_objectives=("nyc", "dot", "team"), relevance_threshold=0.05),
        e,
        tenant_id="t",
    )
    b = extract_map_reduce_llm(
        e,
        t,
        completer=lambda _c: '{"entities":[{"label":"NYC","kind":"x","span_text":"NYC DOT"}]}',
    )
    assert b.entities
