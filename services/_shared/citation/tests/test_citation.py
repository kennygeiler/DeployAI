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


def test_optional_supersession_round_trip() -> None:
    oid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    d = {
        **_VALID,
        "supersession": {
            "type": "overridden",
            "override_event_id": oid,
            "overriding_evidence_event_ids": [eid],
        },
    }
    m = CitationEnvelopeV01.model_validate(d)
    assert m.supersession is not None
    assert str(m.supersession.override_event_id) == oid


def test_rejects_bad_phase() -> None:
    bad = deepcopy(_VALID)
    bad["retrieval_phase"] = "nope"
    with pytest.raises(ValueError):
        CitationEnvelopeV01.model_validate(bad)


# --- signed_timestamp RFC 3339 fixtures (ticket B6) ---
# Keep these strings identical to the fixtures in
# packages/contracts/tests/envelope.contract.test.ts so regex drift between
# citation.py and citation-envelope.ts fails BOTH test suites.
VALID_SIGNED_TIMESTAMPS = [
    "2026-08-11T12:00:00Z",
    "2026-08-11T12:00:00.123Z",
    "2026-08-11T12:00:00+02:00",
    "2026-08-11T12:00:00.5-07:00",
]
INVALID_SIGNED_TIMESTAMPS = [
    "yesterday",
    "2026-08-11",  # date only
    "2026-08-11T12:00:00",  # missing timezone
    "",
]


@pytest.mark.parametrize("ts", VALID_SIGNED_TIMESTAMPS)
def test_accepts_rfc3339_signed_timestamp(ts: str) -> None:
    m = CitationEnvelopeV01.model_validate({**_VALID, "signed_timestamp": ts})
    assert m.signed_timestamp == ts


@pytest.mark.parametrize("ts", INVALID_SIGNED_TIMESTAMPS)
def test_rejects_non_rfc3339_signed_timestamp(ts: str) -> None:
    with pytest.raises(ValueError):
        CitationEnvelopeV01.model_validate({**_VALID, "signed_timestamp": ts})
