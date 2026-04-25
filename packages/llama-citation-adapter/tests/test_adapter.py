"""Unit + integration-style tests for CitationValidatingRetriever (Story 4-2)."""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from llama_citation_adapter.adapter import (
    CitationMetrics,
    CitationValidatingRetriever,
    validate_envelope_on_retrieval,
)

_VALID_ENVELOPE: dict = {
    "schema_version": "0.1.0",
    "node_id": str(uuid.uuid4()),
    "graph_epoch": 0,
    "evidence_span": {"start": 0, "end": 1, "source_ref": "urn:x"},
    "retrieval_phase": "oracle",
    "confidence_score": 0.5,
    "signed_timestamp": "2026-04-23T12:00:00.000Z",
}


class _MockRetriever(BaseRetriever):
    def __init__(self, nodes: list[NodeWithScore]) -> None:
        super().__init__()
        self._nodes = nodes

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return list(self._nodes)


def _node(text: str, meta: dict) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text, metadata=meta), score=1.0)


def test_validate_envelope_on_retrieval_contract() -> None:
    assert validate_envelope_on_retrieval() == "0.1.0"


def test_exact_match_passes() -> None:
    good = _node("ok", {"citation_envelope": deepcopy(_VALID_ENVELOPE)})
    inner = _MockRetriever([good])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    out = r.retrieve("q")
    assert len(out) == 1
    assert m.rejections == 0


def test_missing_envelope_dropped_and_metric() -> None:
    bad = _node("x", {})
    inner = _MockRetriever([bad])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    out = r.retrieve("q")
    assert out == []
    assert m.rejections == 1


def test_wrong_envelope_type_dropped() -> None:
    bad = _node("x", {"citation_envelope": 42})
    inner = _MockRetriever([bad])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    assert r.retrieve("q") == []
    assert m.rejections == 1


def test_invalid_json_string_dropped() -> None:
    bad = _node("x", {"citation_envelope": "not-json{{"})
    inner = _MockRetriever([bad])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    assert r.retrieve("q") == []
    assert m.rejections == 1


def test_malformed_missing_graph_epoch_dropped() -> None:
    bad_env = deepcopy(_VALID_ENVELOPE)
    del bad_env["graph_epoch"]
    bad = _node("x", {"citation_envelope": bad_env})
    inner = _MockRetriever([bad])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    out = r.retrieve("q")
    assert out == []
    assert m.rejections == 1


def test_mixed_batch_only_good_remain() -> None:
    good = _node("ok", {"citation_envelope": deepcopy(_VALID_ENVELOPE)})
    bad = _node("bad", {})
    inner = _MockRetriever([good, bad])
    m = CitationMetrics()
    r = CitationValidatingRetriever(inner, metrics=m)
    out = r.retrieve("q")
    assert len(out) == 1
    assert m.rejections == 1


@pytest.mark.asyncio
async def test_agent_receives_only_valid_async() -> None:
    """Malformed node never appears in async path (integration AC: zero rejected reach agent)."""
    good = _node("ok", {"citation_envelope": deepcopy(_VALID_ENVELOPE)})
    bad = _node("bad", {"citation_envelope": {"schema_version": "0.1.0"}})  # incomplete
    inner = _MockRetriever([good, bad])
    r = CitationValidatingRetriever(inner)
    out = await r.aretrieve("q")
    assert len(out) == 1
    assert "citation_envelope" in (out[0].node.metadata or {})
