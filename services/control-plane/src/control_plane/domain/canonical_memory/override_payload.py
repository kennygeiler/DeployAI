"""Typed payload for ``canonical_memory_events`` rows with ``event_type = override_event`` (Epic 10)."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OVERRIDE_EVENT_TYPE: Literal["override_event"] = "override_event"


class OverrideEventPayloadV1(BaseModel):
    """Contract for Story 10.1 — serialized into ``canonical_memory_events.payload`` (JSONB)."""

    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["epic10.override_payload.v1"] = "epic10.override_payload.v1"
    override_id: UUID
    user_id: UUID
    learning_id: UUID
    override_evidence_event_ids: Annotated[list[UUID], Field(min_length=1)]
    reason_string: Annotated[str, Field(min_length=1)]
    what_changed: str | None = None
    why: str | None = Field(
        default=None,
        description="Structured justification (≥20 chars at API); optional for legacy rows.",
    )
    occurred_at: datetime
    rfc3161_tsa: str | None = Field(
        default=None,
        description="Optional RFC 3161 TimeStampResp bytes, base64 (Story 1.13 wiring).",
    )

    @classmethod
    def build(
        cls,
        *,
        override_id: UUID,
        user_id: UUID,
        learning_id: UUID,
        override_evidence_event_ids: list[UUID],
        reason_string: str,
        occurred_at: datetime,
        what_changed: str | None = None,
        why: str | None = None,
        rfc3161_tsa_token: bytes | None = None,
    ) -> OverrideEventPayloadV1:
        b64: str | None = None
        if rfc3161_tsa_token is not None:
            b64 = base64.b64encode(rfc3161_tsa_token).decode("ascii")
        return cls(
            override_id=override_id,
            user_id=user_id,
            learning_id=learning_id,
            override_evidence_event_ids=override_evidence_event_ids,
            reason_string=reason_string,
            what_changed=what_changed,
            why=why,
            occurred_at=occurred_at,
            rfc3161_tsa=b64,
        )


def parse_override_payload(data: object) -> OverrideEventPayloadV1:
    """Strict parse for contract tests and ingestion guards."""
    if not isinstance(data, dict):
        msg = "override payload must be a JSON object"
        raise TypeError(msg)
    return OverrideEventPayloadV1.model_validate(data)
