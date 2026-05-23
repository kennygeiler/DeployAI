"""Internal API — global event search (Sprint 4 increment 2).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; the
``{tenant_id}`` path segment scopes every query.

Substring search across all ``canonical_memory_events`` in the tenant.
ILIKE on ``payload::text`` is enough for MVP — the seed-data volumes
don't yet warrant a tsvector or trigram index.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.api.routes.tenants_internal import _require_tenant
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent

router = APIRouter(prefix="/tenants", tags=["internal-event-search"])


_SNIPPET_RADIUS = 60
_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50
_MIN_QUERY_LEN = 2


class EventSearchHit(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID | None
    occurred_at: datetime
    event_type: str
    source_ref: str | None
    snippet: str


class EventSearchResponse(BaseModel):
    results: list[EventSearchHit]


def _snippet_around(payload_text: str, query: str) -> str:
    """Return up to ``_SNIPPET_RADIUS`` chars on either side of the first
    case-insensitive match. Falls back to the leading slice when the
    match cannot be found in the JSON-serialised text (the DB cast may
    differ subtly from Python's ``str(dict)``)."""
    lower = payload_text.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        return payload_text[: _SNIPPET_RADIUS * 2]
    start = max(0, idx - _SNIPPET_RADIUS)
    end = min(len(payload_text), idx + len(query) + _SNIPPET_RADIUS)
    chunk = payload_text[start:end]
    if start > 0:
        chunk = "…" + chunk
    if end < len(payload_text):
        chunk = chunk + "…"
    return chunk


@router.get(
    "/{tenant_id}/events/search",
    response_model=EventSearchResponse,
    dependencies=[Depends(require_internal)],
)
async def search_events(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    q: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> EventSearchResponse:
    query = q.strip()
    if len(query) < _MIN_QUERY_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"q must be at least {_MIN_QUERY_LEN} characters",
        )
    await _require_tenant(session, tenant_id)
    pattern = f"%{query}%"
    stmt = (
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            cast(CanonicalMemoryEvent.payload, TEXT).ilike(pattern),
        )
        .order_by(CanonicalMemoryEvent.occurred_at.desc())
        .limit(limit)
    )
    r = await session.execute(stmt)
    rows = list(r.scalars().all())
    hits = [
        EventSearchHit(
            id=row.id,
            engagement_id=row.engagement_id,
            occurred_at=row.occurred_at,
            event_type=row.event_type,
            source_ref=row.source_ref,
            snippet=_snippet_around(json.dumps(row.payload, default=str), query),
        )
        for row in rows
    ]
    return EventSearchResponse(results=hits)
