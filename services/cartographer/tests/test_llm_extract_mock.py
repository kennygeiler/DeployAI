from __future__ import annotations

import uuid
from typing import Any

import pytest

from cartographer.llm_extract import extract_map_reduce_llm
from cartographer.triage import EventSignals, TriageContext, triage_event


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
