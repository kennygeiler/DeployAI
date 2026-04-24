"""3-node stub graph emitting Epic 1 citation envelope dicts (Story 4-1, AR6)."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from deployai_citation.citation import CitationEnvelopeV01, EvidenceSpanV01
from langgraph.graph import END, START, StateGraph


# Simple dict state (no message reducer).
class StubState(TypedDict):
    step: int
    envelopes: list[dict[str, Any]]


STUB_SCHEMA_VERSION = "stub-4-1-v1"


def canned_envelopes() -> list[CitationEnvelopeV01]:
    """Three deterministic canned envelopes (one per node)."""
    n1, n2, n3 = (
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
        uuid.UUID("00000000-0000-4000-8000-000000000003"),
    )
    return [
        CitationEnvelopeV01(
            node_id=n1,
            graph_epoch=0,
            evidence_span=EvidenceSpanV01(start=0, end=10, source_ref="stub:ep4-node-a"),
            retrieval_phase="cartographer",
            confidence_score=0.5,
            signed_timestamp="2026-01-15T12:00:00Z",
        ),
        CitationEnvelopeV01(
            node_id=n2,
            graph_epoch=0,
            evidence_span=EvidenceSpanV01(start=10, end=20, source_ref="stub:ep4-node-b"),
            retrieval_phase="cartographer",
            confidence_score=0.75,
            signed_timestamp="2026-01-15T12:00:01Z",
        ),
        CitationEnvelopeV01(
            node_id=n3,
            graph_epoch=0,
            evidence_span=EvidenceSpanV01(start=20, end=30, source_ref="stub:ep4-node-c"),
            retrieval_phase="synthesis",
            confidence_score=1.0,
            signed_timestamp="2026-01-15T12:00:02Z",
        ),
    ]


def _n1(state: StubState) -> StubState:
    ev = canned_envelopes()
    e = ev[0].model_dump(mode="json")
    return {"step": 1, "envelopes": [e]}


def _n2(state: StubState) -> StubState:
    ev = canned_envelopes()
    e = ev[1].model_dump(mode="json")
    cur = list(state.get("envelopes", []))
    cur.append(e)
    return {"step": 2, "envelopes": cur}


def _n3(state: StubState) -> StubState:
    ev = canned_envelopes()
    e = ev[2].model_dump(mode="json")
    cur = list(state.get("envelopes", []))
    cur.append(e)
    return {"step": 3, "envelopes": cur}


def build_stub_graph() -> StateGraph[StubState]:
    """3-node linear graph: n1 -> n2 -> n3 -> END."""
    g: StateGraph[StubState] = StateGraph(StubState)
    g.add_node("emit_1", _n1)
    g.add_node("emit_2", _n2)
    g.add_node("emit_3", _n3)
    g.add_edge(START, "emit_1")
    g.add_edge("emit_1", "emit_2")
    g.add_edge("emit_2", "emit_3")
    g.add_edge("emit_3", END)
    return g
