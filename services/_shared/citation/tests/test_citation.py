import uuid
from copy import deepcopy

import pytest

from deployai_citation.citation import CitationEnvelopeV01

_VALID = {
    "schema_version": "0.1.0",
    "node_id": str(uuid.uuid4()),
    "graph_epoch": 0,
    "evidence_span": {"start": 0, "end": 1, "source_ref": "urn:x"},
    "retrieval_phase": "oracle",
    "confidence_score": 0.5,
    "signed_timestamp": "2026-04-23T12:00:00.000Z",
}


def test_round_trip() -> None:
    m = CitationEnvelopeV01.model_validate(_VALID)
    d = m.model_dump(mode="json")
    m2 = CitationEnvelopeV01.model_validate(d)
    assert m2 == m


def test_rejects_bad_phase() -> None:
    bad = deepcopy(_VALID)
    bad["retrieval_phase"] = "nope"
    with pytest.raises(ValueError):
        CitationEnvelopeV01.model_validate(bad)
