"""Platform admin APIs (Story 2-5: account provisioning)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PlatformAccountCreate(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=512)
    initial_strategist_email: EmailStr


class PlatformAccountCreated(BaseModel):
    tenant_id: uuid.UUID
    initial_strategist_user_id: uuid.UUID
    created_at: datetime
