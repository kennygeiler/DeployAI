from __future__ import annotations

import uuid

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
