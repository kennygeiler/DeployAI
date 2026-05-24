"""Internal API — email paste-import ingress (Phase C inc 9.1).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``.
Mirrors the inc 9.2 meeting webhook receiver shape: a receiver endpoint
that lands raw payloads in ``email_ingest_events`` for later folding into
canonical memory. Real OAuth-delivered email (Gmail / M365) replaces the
internal caller in a follow-up — the parser + storage shape stays.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.email_events import EmailIngestEvent
from control_plane.domain.engagement import Engagement
from control_plane.emails.paste_parser import (
    ALLOWED_SOURCES,
    ParsedEmail,
    parse_email_paste,
)
from control_plane.emails.storage import record_email_event

router = APIRouter(prefix="/emails", tags=["internal-emails"])


class EmailPasteIn(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    raw: str = Field(min_length=1)
    engagement_id: uuid.UUID | None = None


class EmailIngestEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    source: str
    external_message_id: str | None
    raw_payload: str
    parsed_subject: str | None
    parsed_from: str | None
    parsed_to: list[str]
    parsed_date: datetime | None
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
    "/ingest",
    response_model=list[EmailIngestEventRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_email_paste(
    body: EmailPasteIn,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[EmailIngestEvent]:
    await _require_tenant(session, tenant_id)
    if body.source not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid source: {body.source}",
        )
    if body.engagement_id is not None:
        await _require_engagement(session, tenant_id, body.engagement_id)

    parsed = parse_email_paste(body.source, body.raw)
    parsed_list: list[ParsedEmail] = parsed if isinstance(parsed, list) else [parsed]
    if not parsed_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="no messages found in paste",
        )

    rows: list[EmailIngestEvent] = []
    for p in parsed_list:
        row = await record_email_event(
            session,
            tenant_id=tenant_id,
            source=body.source,
            raw=p.raw if p.raw else body.raw,
            parsed=p,
            engagement_id=body.engagement_id,
        )
        rows.append(row)
    return rows
