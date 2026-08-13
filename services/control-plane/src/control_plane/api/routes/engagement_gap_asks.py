"""Internal API — "Kenny asks" gap detection (Wave 5, GA1).

GET recomputes the deterministic asks over the engagement's matrix and
filters out the ones the user has dismissed or snoozed; POST dismiss/snooze
upserts the durable decision. Mounted under ``/internal/v1``; same
tenant-scoped auth + RLS session posture as ``engagement_summary_internal``
(the Brief's other feed).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode
from control_plane.domain.engagement import Engagement
from control_plane.domain.gap_asks import GapAskDismissal
from control_plane.services.gap_detection import (
    COMMITMENT_EVIDENCE_STALE_DAYS,
    GapAsk,
    detect_gaps,
)

router = APIRouter(prefix="/engagements", tags=["internal-engagement-gap-asks"])

# Evidence-recency window is bounded so a huge corpus stays cheap; the
# silence rule uses the unbounded max(occurred_at) aggregate instead.
_RECENT_EVENTS_CAP = 500

_ASK_ID = Path(min_length=1, max_length=64, pattern=r"^[0-9a-f]+$")


class GapAsksResponse(BaseModel):
    asks: list[GapAsk]


class GapAskDismissBody(BaseModel):
    dismissed_by: str | None = Field(default=None, max_length=320)


class GapAskSnoozeBody(BaseModel):
    days: int = Field(ge=1, le=90)
    dismissed_by: str | None = Field(default=None, max_length=320)


class GapAskDismissalRead(BaseModel):
    ask_id: str
    dismissed_at: datetime
    snooze_until: datetime | None


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    row = (
        await session.execute(
            select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return row


@router.get(
    "/{engagement_id}/gap-asks",
    response_model=GapAsksResponse,
    dependencies=[Depends(require_tenant_scoped)],
)
async def get_engagement_gap_asks(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> GapAsksResponse:
    """Recompute the asks and drop the dismissed / actively-snoozed ones."""
    await _require_engagement(session, tenant_id, engagement_id)
    now = datetime.now(UTC)

    nodes = list((await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))).scalars())
    edges = list((await session.execute(select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id))).scalars())
    cutoff = now - timedelta(days=COMMITMENT_EVIDENCE_STALE_DAYS)
    recent_events = list(
        (
            await session.execute(
                select(CanonicalMemoryEvent)
                .where(
                    CanonicalMemoryEvent.tenant_id == tenant_id,
                    CanonicalMemoryEvent.engagement_id == engagement_id,
                    CanonicalMemoryEvent.occurred_at >= cutoff,
                )
                .order_by(CanonicalMemoryEvent.occurred_at.desc())
                .limit(_RECENT_EVENTS_CAP)
            )
        ).scalars()
    )
    latest_event_at = (
        await session.execute(
            select(func.max(CanonicalMemoryEvent.occurred_at)).where(
                CanonicalMemoryEvent.tenant_id == tenant_id,
                CanonicalMemoryEvent.engagement_id == engagement_id,
            )
        )
    ).scalar_one_or_none()

    asks = detect_gaps(nodes, edges, recent_events, latest_event_at, now)
    if not asks:
        return GapAsksResponse(asks=[])

    # Hidden = permanently dismissed (snooze_until NULL) or snooze still active.
    dismissal_rows = (
        await session.execute(
            select(GapAskDismissal).where(
                GapAskDismissal.tenant_id == tenant_id,
                GapAskDismissal.engagement_id == engagement_id,
                GapAskDismissal.ask_id.in_([a.id for a in asks]),
            )
        )
    ).scalars()
    hidden = {d.ask_id for d in dismissal_rows if d.snooze_until is None or d.snooze_until > now}
    return GapAsksResponse(asks=[a for a in asks if a.id not in hidden])


async def _upsert_dismissal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    ask_id: str,
    *,
    dismissed_by: str | None,
    snooze_until: datetime | None,
    now: datetime,
) -> GapAskDismissalRead:
    stmt = (
        pg_insert(GapAskDismissal)
        .values(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            ask_id=ask_id,
            dismissed_by=dismissed_by,
            dismissed_at=now,
            snooze_until=snooze_until,
        )
        .on_conflict_do_update(
            constraint="uq_gap_ask_dismissals_tenant_engagement_ask",
            set_={"dismissed_by": dismissed_by, "dismissed_at": now, "snooze_until": snooze_until},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return GapAskDismissalRead(ask_id=ask_id, dismissed_at=now, snooze_until=snooze_until)


@router.post(
    "/{engagement_id}/gap-asks/{ask_id}/dismiss",
    response_model=GapAskDismissalRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def dismiss_gap_ask(
    engagement_id: uuid.UUID,
    ask_id: Annotated[str, _ASK_ID],
    body: GapAskDismissBody,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> GapAskDismissalRead:
    """Permanently hide an ask (until its target node changes identity)."""
    await _require_engagement(session, tenant_id, engagement_id)
    return await _upsert_dismissal(
        session,
        tenant_id,
        engagement_id,
        ask_id,
        dismissed_by=body.dismissed_by,
        snooze_until=None,
        now=datetime.now(UTC),
    )


@router.post(
    "/{engagement_id}/gap-asks/{ask_id}/snooze",
    response_model=GapAskDismissalRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def snooze_gap_ask(
    engagement_id: uuid.UUID,
    ask_id: Annotated[str, _ASK_ID],
    body: GapAskSnoozeBody,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> GapAskDismissalRead:
    """Hide an ask until ``now + days``; it reappears after that."""
    await _require_engagement(session, tenant_id, engagement_id)
    now = datetime.now(UTC)
    return await _upsert_dismissal(
        session,
        tenant_id,
        engagement_id,
        ask_id,
        dismissed_by=body.dismissed_by,
        snooze_until=now + timedelta(days=body.days),
        now=now,
    )
