"""Table-driven edge coverage for ``llm_extract`` (short span, empty label, non-dict rows)."""

from __future__ import annotations

import json
import uuid

import pytest

from cartographer.llm_extract import extract_map_reduce_llm
from cartographer.triage import EventSignals, TriageContext, TriageResult, triage_event


def _fixture() -> tuple[EventSignals, TriageResult]:
    eid = uuid.uuid4()
    e = EventSignals(
        event_id=eid,
        text_blob="Hello world here and something longer for tokens.",
        event_keywords=("hello", "world"),
    )
    t = triage_event(
        TriageContext(
            phase="P5_scale_execution",
            declared_objectives=("hello", "world", "something"),
            relevance_threshold=0.05,
        ),
        e,
        tenant_id="t",
    )
    return e, t


@pytest.mark.parametrize(
    ("payload", "expect_count"),
    [
        (
            {"entities": [{"label": "", "kind": "x", "span_text": "Hello"}]},
            0,
        ),
        (
            {"entities": [{"label": " ", "kind": "x", "span_text": "Hello"}]},
            0,
        ),
        (
            # One-char span_text -> _span_for_quote None -> fallback span
            {"entities": [{"label": "X", "kind": "x", "span_text": "H"}]},
            1,
        ),
        (
            {"entities": [42, {"label": "Ok", "kind": "x", "span_text": "Hello"}]},
            1,
        ),
        (
            {"entities": "not-a-list"},
            0,
        ),
    ],
)
def test_llm_map_chunk_table_rows(
    payload: dict,
    expect_count: int,
) -> None:
    e, tri = _fixture()

    def completer(_c: str) -> str:
        return json.dumps(payload)

    b = extract_map_reduce_llm(e, tri, completer=completer)
    assert len(b.entities) == expect_count
