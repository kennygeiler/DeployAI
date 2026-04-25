"""Story 6-5: suggestions-only action posture (FR25, DP10)."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import cast
from unittest.mock import Mock

import pytest
from deployai_citation.citation import CitationEnvelopeV01

from oracle.budget import apply_three_item_budget
from oracle.posture import (
    assert_oracle_items_suggestions_only,
    validate_budgeted_oracle_posture,
    validate_oracle_response_posture,
)
from oracle.retrieve import OracleItem, OracleResponse

# Reuse shape from test_budget
_ENV_BASE: dict = {
    "schema_version": "0.1.0",
    "node_id": str(uuid.uuid4()),
    "graph_epoch": 0,
    "evidence_span": {"start": 0, "end": 1, "source_ref": "urn:test"},
    "retrieval_phase": "oracle",
    "confidence_score": 0.5,
    "signed_timestamp": "2026-04-23T12:00:00.000Z",
}


def _item(fit: float = 0.9) -> OracleItem:
    d = deepcopy(_ENV_BASE)
    d["node_id"] = str(uuid.uuid4())
    env = CitationEnvelopeV01.model_validate(d)
    return OracleItem(
        text="suggestion body",
        deployment_phase="P5_pilot",
        contextual_fit_score=fit,
        retriever_score=0.5,
        confidence_score=float(env.confidence_score),
        citation_envelope=env,
    )


def test_all_items_are_suggestion_posture() -> None:
    a = _item()
    assert a.action_posture == "suggestion"
    assert_oracle_items_suggestions_only((a,))


def test_validate_full_and_budgeted_responses() -> None:
    raw = OracleResponse(
        items=(_item(0.9), _item(0.8)),
        corpus_confidence_marker="high",
        null_result=None,
    )
    validate_oracle_response_posture(raw)
    budgeted = apply_three_item_budget(raw)
    validate_budgeted_oracle_posture(budgeted)


def test_rejects_if_posture_mismatch() -> None:
    bad = cast(
        OracleItem,
        Mock(
            spec=OracleItem,
            action_posture="executed",
            node_id="n1",
        ),
    )
    with pytest.raises(AssertionError, match="suggestions-only"):
        assert_oracle_items_suggestions_only((bad,))
