"""Pydantic shapes for schema proposal API (Story 1-17)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SchemaProposalCreate(BaseModel):
    proposer_actor_id: uuid.UUID
    proposed_ddl: str
    proposer_agent: str | None = None
    proposed_field_path: str | None = None
    proposed_type: str | None = None
    sample_evidence: dict[str, Any] | None = None


class SchemaProposalRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    proposer_actor_id: uuid.UUID
    proposed_ddl: str
    status: str
    reviewed_at: datetime | None
    reviewer_actor_id: uuid.UUID | None
    proposer_agent: str | None
    proposed_field_path: str | None
    proposed_type: str | None
    sample_evidence: dict[str, Any] | None
    rejection_reason: str | None


class RejectBody(BaseModel):
    rejection_reason: str = Field(default="", max_length=16_000)
