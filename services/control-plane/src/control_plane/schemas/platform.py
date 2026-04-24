"""Platform admin APIs (Story 2-5: account provisioning)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class PlatformAccountCreate(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=512)
    initial_strategist_email: EmailStr

    @field_validator("organization_name")
    @classmethod
    def _strip_nonempty_org_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("organization_name must contain non-whitespace characters")
        return s


class PlatformAccountCreated(BaseModel):
    tenant_id: uuid.UUID
    initial_strategist_user_id: uuid.UUID
    created_at: datetime
