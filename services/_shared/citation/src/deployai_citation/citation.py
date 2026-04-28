from __future__ import annotations

import re
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

CITATION_ENVELOPE_SCHEMA_VERSION: Final[Literal["0.1.0"]] = "0.1.0"

RetrievalPhaseV01 = Literal["cartographer", "oracle", "master_strategist", "synthesis"]
_PHASES: frozenset[str] = frozenset(
    ("cartographer", "oracle", "master_strategist", "synthesis"),
)


def _is_rfc3339_utcish(s: str) -> bool:
    """Loose ISO 8601 / RFC 3339 check matching Zod `z.string().min(1)` + tests."""
    if len(s) < 1:
        return False
    return bool(
        re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
            s,
        ),
    )


class CitationSupersessionOverriddenV01(BaseModel):
    """Epic 10.3 — learning was superseded by a strategist override."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["overridden"] = "overridden"
    override_event_id: UUID
    overriding_evidence_event_ids: Annotated[list[UUID], Field(min_length=1)]


class EvidenceSpanV01(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    source_ref: str = Field(min_length=1)

    @field_validator("end")
    @classmethod
    def end_gte_start(cls, v: int, info: ValidationInfo) -> int:
        start = info.data.get("start")
        if start is not None and v < int(start):
            msg = "evidence_span.end must be >= evidence_span.start"
            raise ValueError(msg)
        return v


class CitationEnvelopeV01(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["0.1.0"] = CITATION_ENVELOPE_SCHEMA_VERSION
    node_id: UUID
    graph_epoch: int = Field(ge=0)
    evidence_span: EvidenceSpanV01
    retrieval_phase: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    signed_timestamp: str = Field(min_length=1)
    supersession: CitationSupersessionOverriddenV01 | None = None

    @field_validator("retrieval_phase")
    @classmethod
    def _phase(cls, v: str) -> str:
        if v not in _PHASES:
            msg = f"Invalid retrieval_phase: {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("signed_timestamp")
    @classmethod
    def _ts(cls, v: str) -> str:
        if not _is_rfc3339_utcish(v):
            msg = "signed_timestamp must be an ISO 8601 / RFC 3339 string"
            raise ValueError(msg)
        return v
