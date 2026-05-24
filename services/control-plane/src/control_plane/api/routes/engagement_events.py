"""Batched read of canonical_memory_events by id for citation drill-down."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import (
    _require_engagement,
    require_internal,
)
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent

router = APIRouter(prefix="/engagements", tags=["internal-engagements-events"])

_SUMMARY_CHARS = 240
_MAX_IDS = 50


class EventRead(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    source_ref: str | None
    summary: str


class EventsResponse(BaseModel):
    events: list[EventRead]


def _summary_for(event: CanonicalMemoryEvent) -> str:
    payload = event.payload or {}
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, dict):
            nested_text = content.get("text")
            if isinstance(nested_text, str):
                return nested_text[:_SUMMARY_CHARS]
        flat_text = payload.get("text")
        if isinstance(flat_text, str):
            return flat_text[:_SUMMARY_CHARS]
    return json.dumps(payload, default=str, sort_keys=True)[:_SUMMARY_CHARS]


def _parse_ids(raw: str) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for chunk in raw.split(","):
        s = chunk.strip()
        if not s:
            continue
        try:
            parsed = uuid.UUID(s)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid event id: {s}",
            ) from e
        if parsed in seen:
            continue
        seen.add(parsed)
        out.append(parsed)
    return out


@router.get(
    "/{engagement_id}/events",
    response_model=EventsResponse,
    dependencies=[Depends(require_internal)],
)
async def get_engagement_events_by_ids(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    ids: Annotated[str, Query()],
) -> EventsResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    parsed_ids = _parse_ids(ids)
    if not parsed_ids:
        return EventsResponse(events=[])
    if len(parsed_ids) > _MAX_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"too many ids: {len(parsed_ids)} (max {_MAX_IDS})",
        )
    r = await session.execute(
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
            CanonicalMemoryEvent.id.in_(parsed_ids),
        )
        .order_by(CanonicalMemoryEvent.occurred_at.asc())
    )
    rows = list(r.scalars().all())
    return EventsResponse(
        events=[
            EventRead(
                id=row.id,
                occurred_at=row.occurred_at,
                event_type=row.event_type,
                source_ref=row.source_ref,
                summary=_summary_for(row),
            )
            for row in rows
        ]
    )
