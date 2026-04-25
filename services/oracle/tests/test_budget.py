"""Story 6-4: 3-item hard budget + ranked-out footer + contract tests."""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from deployai_citation.citation import CitationEnvelopeV01

from oracle.budget import (
    PRIMARY_BUDGET,
    apply_three_item_budget,
    assert_primary_at_most_three,
)
from oracle.retrieve import (
    ExplicitNullResult,
    OracleItem,
    OracleResponse,
)

_ENV_BASE: dict = {
    "schema_version": "0.1.0",
    "node_id": str(uuid.uuid4()),
    "graph_epoch": 0,
    "evidence_span": {"start": 0, "end": 1, "source_ref": "urn:test"},
    "retrieval_phase": "oracle",
    "confidence_score": 0.5,
    "signed_timestamp": "2026-04-23T12:00:00.000Z",
}


def _make_item(
    text: str,
    *,
    fit: float,
    eid: str | None = None,
) -> OracleItem:
    d = deepcopy(_ENV_BASE)
    d["node_id"] = eid or str(uuid.uuid4())
    env = CitationEnvelopeV01.model_validate(d)
    return OracleItem(
        text=text,
        deployment_phase="P5_pilot",
        contextual_fit_score=fit,
        retriever_score=0.5,
        confidence_score=float(env.confidence_score),
        citation_envelope=env,
        node_id=None,
    )


def test_twenty_candidates_three_primary_seventeen_ranked_out() -> None:
    items = tuple(_make_item(f"row-{i}", fit=1.0 - i * 0.01) for i in range(20))
    assert len(items) == 20
    raw = OracleResponse(
        items=items,
        corpus_confidence_marker="high",
        null_result=None,
    )
    out = apply_three_item_budget(raw)
    assert len(out.primary) == PRIMARY_BUDGET
    assert len(out.ranked_out) == 17
    assert out.corpus_confidence_marker == "high"
    assert out.null_result is None
    assert out.surface == "in_meeting_alert"
    assert "rank 4" in out.ranked_out[0].reason
    assert f"of {20}" in out.ranked_out[0].reason


def test_contract_len_primary_lte_three_every_emission() -> None:
    for n in (0, 1, 2, 3, 4, 20):
        items = tuple(_make_item(f"x{i}", fit=float(10 - i)) for i in range(n))
        raw = OracleResponse(
            items=items,
            corpus_confidence_marker="null" if n == 0 else "low",
            null_result=ExplicitNullResult("x") if n == 0 else None,
        )
        out = apply_three_item_budget(raw)
        assert_primary_at_most_three(out)
        assert len(out.primary) <= PRIMARY_BUDGET


def test_null_response_empty_primary() -> None:
    raw = OracleResponse(
        items=(),
        corpus_confidence_marker="null",
        null_result=ExplicitNullResult(reason="none"),
    )
    out = apply_three_item_budget(raw)
    assert out.primary == ()
    assert out.ranked_out == ()


def test_morning_digest_same_cap() -> None:
    items = (
        _make_item("a", fit=0.9),
        _make_item("b", fit=0.8),
        _make_item("c", fit=0.7),
        _make_item("d", fit=0.1),
    )
    raw = OracleResponse(items=items, corpus_confidence_marker="medium", null_result=None)
    out = apply_three_item_budget(raw, surface="morning_digest")
    assert out.surface == "morning_digest"
    assert len(out.primary) == 3
    assert len(out.ranked_out) == 1
    assert_primary_at_most_three(out)


def test_rejects_over_budget() -> None:
    """Paranoia check: the assert helper raises if a future path violates the cap."""
    from oracle.budget import BudgetedOracleResponse

    fake = BudgetedOracleResponse(
        primary=tuple(_make_item(str(i), fit=0.1) for i in range(4)),
        ranked_out=(),
        corpus_confidence_marker="high",
        null_result=None,
        surface="in_meeting_alert",
    )
    with pytest.raises(AssertionError, match="budget exceeded"):
        assert_primary_at_most_three(fake)
