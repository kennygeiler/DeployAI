"""Break-glass request/response types (Epic 2 Story 2-7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BreakGlassRequestBody(BaseModel):
    tenant_id: uuid.UUID
    requested_scope: str = Field(default="tenant_data_read", max_length=256)


class BreakGlassSessionRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    initiator_sub: str
    approver_sub: str | None
    requested_scope: str
    requested_at: datetime
    approved_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}
