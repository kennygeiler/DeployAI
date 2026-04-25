"""Story 6-3: Oracle retrieval + CCM + null + phase-ambiguity union (integration-style, no live DB)."""

from __future__ import annotations

import uuid
from copy import deepcopy

from llama_citation_adapter import CitationValidatingRetriever
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from oracle.retrieve import (
    OracleRetrievalRequest,
    oracle_retrieve,
)


def _envelope() -> dict:
    return {
        "schema_version": "0.1.0",
        "node_id": str(uuid.uuid4()),
        "graph_epoch": 0,
        "evidence_span": {"start": 0, "end": 1, "source_ref": "urn:fixture"},
        "retrieval_phase": "oracle",
        "confidence_score": 0.9,
        "signed_timestamp": "2026-04-23T12:00:00.000Z",
    }


def _nws(
    text: str,
    *,
    tenant: str,
    dep_phase: str,
    score: float,
    confidence: float | None = None,
    recency: float | None = None,
) -> NodeWithScore:
    env = _envelope()
    if confidence is not None:
        e2 = deepcopy(env)
        e2["confidence_score"] = confidence
        env = e2
    meta: dict = {
        "citation_envelope": env,
        "tenant_id": tenant,
        "deployment_phase": dep_phase,
    }
    if recency is not None:
        meta["recency"] = recency
    return NodeWithScore(node=TextNode(text=text, metadata=meta), score=score)


class _MockRetriever(BaseRetriever):
    def __init__(self, nodes: list[NodeWithScore]) -> None:
        super().__init__()
        self._nodes = nodes

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return list(self._nodes)


def _wrapped(inner: _MockRetriever) -> CitationValidatingRetriever:
    return CitationValidatingRetriever(inner)


def test_high_confidence_retrieval() -> None:
    inner = _MockRetriever(
        [
            _nws("alpha", tenant="t1", dep_phase="P5_pilot", score=0.95, recency=0.9),
        ],
    )
    r = _wrapped(inner)
    req = OracleRetrievalRequest(
        tenant_id="t1",
        target_deployment_phase="P5_pilot",
        query_text="stakeholder deployment",
    )
    out = oracle_retrieve(r, req)
    assert out.null_result is None
    assert len(out.items) == 1
    assert out.corpus_confidence_marker == "high"
    assert out.items[0].deployment_phase == "P5_pilot"
    assert out.items[0].contextual_fit_score >= 0.7


def test_null_result_no_hits_for_phase() -> None:
    inner = _MockRetriever(
        [
            _nws("other phase only", tenant="t1", dep_phase="P1_pre_engagement", score=0.99),
        ],
    )
    r = _wrapped(inner)
    req = OracleRetrievalRequest(
        tenant_id="t1",
        target_deployment_phase="P5_pilot",
        query_text="q",
    )
    out = oracle_retrieve(r, req)
    assert out.items == ()
    assert out.corpus_confidence_marker == "null"
    assert out.null_result is not None
    assert "no_phase" in out.null_result.reason


def test_null_result_wrong_tenant() -> None:
    inner = _MockRetriever([_nws("x", tenant="other", dep_phase="P5_pilot", score=0.9)])
    r = _wrapped(inner)
    out = oracle_retrieve(
        r,
        OracleRetrievalRequest(
            tenant_id="t1",
            target_deployment_phase="P5_pilot",
            query_text="q",
        ),
    )
    assert out.items == ()
    assert out.corpus_confidence_marker == "null"


def test_phase_ambiguity_union_includes_both_with_labels() -> None:
    inner = _MockRetriever(
        [
            _nws("a", tenant="t1", dep_phase="P4_design", score=0.5),
            _nws("b", tenant="t1", dep_phase="P5_pilot", score=0.6),
        ],
    )
    r = _wrapped(inner)
    req = OracleRetrievalRequest(
        tenant_id="t1",
        target_deployment_phase="P4_design",
        query_text="q",
        phase_ambiguous=True,
        ambiguous_phases=("P4_design", "P5_pilot"),
    )
    out = oracle_retrieve(r, req)
    phases = {x.deployment_phase for x in out.items}
    assert phases == {"P4_design", "P5_pilot"}
    assert out.null_result is None
    assert len(out.items) == 2


def test_medium_confidence_band() -> None:
    """Scores around the 0.45–0.72 band should surface ``medium`` CCM."""
    inner = _MockRetriever(
        [
            _nws(
                "m",
                tenant="t1",
                dep_phase="P5_pilot",
                score=0.5,
                confidence=0.5,
                recency=0.4,
            ),
        ],
    )
    r = _wrapped(inner)
    out = oracle_retrieve(
        r,
        OracleRetrievalRequest(
            tenant_id="t1",
            target_deployment_phase="P5_pilot",
            query_text="q",
        ),
    )
    assert out.corpus_confidence_marker == "medium"
    assert out.null_result is None


def test_drops_node_without_deployment_phase() -> None:
    env = _envelope()
    bad_meta = {"citation_envelope": env, "tenant_id": "t1"}
    node = NodeWithScore(node=TextNode(text="nophase", metadata=bad_meta), score=1.0)
    inner = _MockRetriever([node])
    r = _wrapped(inner)
    out = oracle_retrieve(
        r,
        OracleRetrievalRequest(
            tenant_id="t1",
            target_deployment_phase="P5_pilot",
            query_text="q",
        ),
    )
    assert out.items == ()
    assert out.corpus_confidence_marker == "null"
