"""Read-only chronological view over ``canonical_memory_events`` for one engagement."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import (
    _require_engagement,
    require_internal,
)
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent

router = APIRouter(prefix="/engagements", tags=["internal-engagements-timeline"])

_SUMMARY_CHARS = 240
_DEFAULT_DAYS = 180
_MAX_DAYS = 365


class TimelineEvent(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    source_ref: str | None
    summary: str


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]


def _summary_for(event: CanonicalMemoryEvent) -> str:
    payload = event.payload or {}
    if isinstance(payload, dict):
        # ingest_interaction wraps content as {"content": {"text": "..."}}; some
        # synthetic producers store {"text": "..."} flat. Probe both before the
        # json.dumps fallback so real events render readable text, not raw JSON.
        content = payload.get("content")
        if isinstance(content, dict):
            nested_text = content.get("text")
            if isinstance(nested_text, str):
                return nested_text[:_SUMMARY_CHARS]
        flat_text = payload.get("text")
        if isinstance(flat_text, str):
            return flat_text[:_SUMMARY_CHARS]
    return json.dumps(payload, default=str, sort_keys=True)[:_SUMMARY_CHARS]


@router.get(
    "/{engagement_id}/timeline",
    response_model=TimelineResponse,
    dependencies=[Depends(require_internal)],
)
async def get_engagement_timeline(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    days: Annotated[int, Query(ge=1, le=_MAX_DAYS)] = _DEFAULT_DAYS,
) -> TimelineResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    r = await session.execute(
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
            CanonicalMemoryEvent.occurred_at >= cutoff,
        )
        .order_by(CanonicalMemoryEvent.occurred_at.asc())
    )
    rows = list(r.scalars().all())
    return TimelineResponse(
        events=[
            TimelineEvent(
                id=row.id,
                occurred_at=row.occurred_at,
                event_type=row.event_type,
                source_ref=row.source_ref,
                summary=_summary_for(row),
            )
            for row in rows
        ]
    )
