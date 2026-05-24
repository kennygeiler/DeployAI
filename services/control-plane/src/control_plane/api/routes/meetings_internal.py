"""Internal API — meeting webhook ingress (Phase C inc 9.2).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``.
Mirrors the D1 email-paste shape: a receiver endpoint that lands raw
payloads in ``meeting_webhook_events`` for later processing. Real
OAuth-delivered webhooks (Zoom / Google Meet / Teams) replace the
internal caller in a follow-up — the parser shape stays.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.engagement import Engagement
from control_plane.domain.meeting_events import MeetingWebhookEvent
from control_plane.meetings.webhook_receiver import (
    ALLOWED_SOURCES,
    parse_webhook_payload,
    record_webhook_event,
)

router = APIRouter(prefix="/meetings", tags=["internal-meetings"])


class MeetingWebhookIn(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    payload: dict[str, Any]
    engagement_id: uuid.UUID | None = None


class MeetingWebhookEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    source: str
    external_event_id: str | None
    payload: dict[str, Any]
    received_at: datetime
    processed_at: datetime | None
    error: str | None


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
    row = await session.get(Engagement, engagement_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")


@router.post(
    "/webhook",
    response_model=MeetingWebhookEventRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_meeting_webhook(
    body: MeetingWebhookIn,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MeetingWebhookEvent:
    await _require_tenant(session, tenant_id)
    if body.source not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid source: {body.source}",
        )
    if body.engagement_id is not None:
        await _require_engagement(session, tenant_id, body.engagement_id)
    parsed = parse_webhook_payload(body.source, body.payload)
    return await record_webhook_event(
        session,
        tenant_id=tenant_id,
        source=body.source,
        payload=body.payload,
        engagement_id=body.engagement_id,
        parsed=parsed,
    )
