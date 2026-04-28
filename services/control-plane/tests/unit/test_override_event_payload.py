"""Contract tests for Epic 10 Story 10.1 override payload (Pydantic v2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from control_plane.domain.canonical_memory.override_payload import (
    OVERRIDE_EVENT_TYPE,
    OverrideEventPayloadV1,
    parse_override_payload,
)


def test_override_event_type_literal() -> None:
    assert OVERRIDE_EVENT_TYPE == "override_event"


def test_model_json_schema_has_core_properties() -> None:
    schema = OverrideEventPayloadV1.model_json_schema()
    props = schema["properties"]
    for key in (
        "schema_id",
        "override_id",
        "user_id",
        "learning_id",
        "override_evidence_event_ids",
        "reason_string",
        "what_changed",
        "why",
        "occurred_at",
        "rfc3161_tsa",
    ):
        assert key in props


def test_parse_roundtrip_from_dumped_payload() -> None:
    oid = uuid.uuid4()
    uid = uuid.uuid4()
    lid = uuid.uuid4()
    eid = uuid.uuid4()
    when = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    original = OverrideEventPayloadV1.build(
        override_id=oid,
        user_id=uid,
        learning_id=lid,
        override_evidence_event_ids=[eid],
        reason_string="Corrected belief after new transcript evidence.",
        occurred_at=when,
        rfc3161_tsa_token=b"\x30\x31tsa-bytes",
    )
    blob = original.model_dump(mode="json")
    again = parse_override_payload(blob)
    assert again == original
    assert again.rfc3161_tsa is not None


def test_rejects_empty_evidence_list() -> None:
    with pytest.raises(ValidationError):
        OverrideEventPayloadV1.build(
            override_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            learning_id=uuid.uuid4(),
            override_evidence_event_ids=[],
            reason_string="x",
            occurred_at=datetime.now(tz=UTC),
        )


def test_parse_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        parse_override_payload(
            {
                "schema_id": "epic10.override_payload.v1",
                "override_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "learning_id": str(uuid.uuid4()),
                "override_evidence_event_ids": [str(uuid.uuid4())],
                "reason_string": "y",
                "occurred_at": "2026-04-26T12:00:00Z",
                "extra": "nope",
            }
        )
