"""Internal API — Slack channel → engagement mappings + snapshot flush (Wave 5 SL1).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key`` (or a
per-tenant service token) via ``require_tenant_scoped``; the BFF layers the
user-facing authz on top (create/revoke gated ``ingest:sync``, list gated
``canonical:read``).

The mapping is the consent record: only actively mapped channels' messages
are staged, and revoking a mapping discards the channel's unflushed staged
messages (content already flushed into canonical memory stays — the ledger
is append-only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session
from control_plane.domain.engagement import Engagement
from control_plane.domain.slack_intake import (
    SlackChannelMapping,
    SlackPendingChannel,
    SlackStagingMessage,
)
from control_plane.services.slack_snapshot_flush import flush_tenant_slack_staging

router = APIRouter(prefix="/slack", tags=["internal-slack-intake"])


class SlackChannelMappingCreate(BaseModel):
    channel_id: str = Field(min_length=1, max_length=64)
    channel_name: str = Field(default="", max_length=200)
    engagement_id: uuid.UUID
    created_by: str | None = Field(default=None, max_length=200)


class SlackChannelMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: str
    channel_name: str
    engagement_id: uuid.UUID
    created_by: str | None
    created_at: datetime
    revoked_at: datetime | None


class SlackPendingChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: str
    channel_name: str
    first_seen_at: datetime


class SlackFlushReport(BaseModel):
    snapshots_written: int
    deduped_units: int
    messages_flushed: int
    messages_discarded: int
    extraction_errors: list[str]


@router.get(
    "/channel-mappings",
    response_model=list[SlackChannelMappingRead],
    dependencies=[Depends(require_tenant_scoped)],
)
async def list_slack_channel_mappings(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    include_revoked: Annotated[bool, Query()] = False,
) -> list[SlackChannelMapping]:
    stmt = select(SlackChannelMapping).where(SlackChannelMapping.tenant_id == tenant_id)
    if not include_revoked:
        stmt = stmt.where(SlackChannelMapping.revoked_at.is_(None))
    r = await session.execute(stmt.order_by(SlackChannelMapping.created_at))
    return list(r.scalars().all())


@router.post(
    "/channel-mappings",
    response_model=SlackChannelMappingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_scoped)],
)
async def create_slack_channel_mapping(
    body: SlackChannelMappingCreate,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> SlackChannelMapping:
    eng = (
        await session.execute(
            select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == body.engagement_id)
        )
    ).scalar_one_or_none()
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    existing = (
        await session.execute(
            select(SlackChannelMapping).where(
                SlackChannelMapping.tenant_id == tenant_id,
                SlackChannelMapping.channel_id == body.channel_id,
                SlackChannelMapping.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"channel {body.channel_id} is already mapped",
        )
    row = SlackChannelMapping(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        channel_name=body.channel_name,
        engagement_id=body.engagement_id,
        created_by=body.created_by,
    )
    session.add(row)
    # Mapping resolves the pending offer for this channel, if any.
    await session.execute(
        delete(SlackPendingChannel).where(
            SlackPendingChannel.tenant_id == tenant_id,
            SlackPendingChannel.channel_id == body.channel_id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.post(
    "/channel-mappings/{mapping_id}/revoke",
    response_model=SlackChannelMappingRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def revoke_slack_channel_mapping(
    mapping_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> SlackChannelMapping:
    """Revoke (idempotent). Unflushed staged messages for the channel are
    discarded — revocation withdraws consent for anything not yet canonical."""
    row = (
        await session.execute(
            select(SlackChannelMapping).where(
                SlackChannelMapping.tenant_id == tenant_id,
                SlackChannelMapping.id == mapping_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mapping not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.execute(
            delete(SlackStagingMessage).where(
                SlackStagingMessage.tenant_id == tenant_id,
                SlackStagingMessage.channel_id == row.channel_id,
                SlackStagingMessage.flushed_at.is_(None),
            )
        )
        await session.commit()
        await session.refresh(row)
    return row


@router.get(
    "/pending-channels",
    response_model=list[SlackPendingChannelRead],
    dependencies=[Depends(require_tenant_scoped)],
)
async def list_slack_pending_channels(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[SlackPendingChannel]:
    r = await session.execute(
        select(SlackPendingChannel)
        .where(SlackPendingChannel.tenant_id == tenant_id)
        .order_by(SlackPendingChannel.first_seen_at)
    )
    return list(r.scalars().all())


@router.post(
    "/flush",
    response_model=SlackFlushReport,
    dependencies=[Depends(require_tenant_scoped)],
)
async def flush_slack_staging(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> dict[str, Any]:
    """Batch staged messages into ``slack.thread`` snapshots + chain extraction.

    Idempotent: re-flushing an unchanged unit dedups on the fingerprinted
    ``ingestion_dedup_key``. Run this from a scheduler (cron) — see
    ``docs/ops/slack-intake.md``.
    """
    resolved = await resolve_tenant_llm_provider(session, tenant_id, llm)
    return await flush_tenant_slack_staging(tenant_id=tenant_id, llm=resolved)
