"""Internal API — engagement summary (Wave 2.5 legibility, ticket U6).

One-shot first-paint payload for the engagement page header: identity,
members with display names, entity counts, and a short human-readable
recent-changes feed. Mounted under ``/internal/v1``; same tenant-scoped
auth + RLS session posture as ``engagements_internal``.

Designed as a single round trip with a fixed, small number of aggregate
queries (no per-row fan-out) so it stays fast on large corpora — see the
XL-seed integration test for the latency budget.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session
from control_plane.domain.app_identity.models import AppUser
from control_plane.domain.canonical_memory.matrix import MatrixNode, MatrixProposal
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.review_inbox import ReviewItem
from control_plane.services.engagement_legibility import (
    actor_display_name,
    bucket_for_source_kind,
    humanize_event_title,
    is_risk_open,
    user_display_name,
)

router = APIRouter(prefix="/engagements", tags=["internal-engagement-summary"])

_RECENT_CHANGES_LIMIT = 10


class SummaryEngagement(BaseModel):
    id: uuid.UUID
    name: str
    customer_account: str | None
    current_phase: str
    status: str
    updated_at: datetime


class SummaryMember(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str | None
    role: str


class SummaryCounts(BaseModel):
    """Entity counts for the summary header.

    Conventions (documented here because the U6 contract leaves them open):

    - ``stakeholders`` / ``decisions`` / ``commitments`` count ALL matrix
      nodes of that ``node_type`` regardless of status.
    - ``risks_open`` counts ``node_type='risk'`` matrix nodes whose status is
      not terminal per ``engagement_legibility.RISK_CLOSED_STATUSES``; a NULL
      status counts as open (nothing in the codebase writes risk-node
      statuses with a fixed vocabulary today).
    - ``proposals_pending`` counts ``matrix_proposals.status = 'pending'``.
    - ``escalations_open`` / ``disputes_open`` count open ``review_items`` of
      kind ``agent_escalation`` / ``citation_dispute``.
    """

    stakeholders: int
    decisions: int
    risks_open: int
    commitments: int
    proposals_pending: int
    escalations_open: int
    disputes_open: int
    # TODO(U3): approvals_pending (in-flight LangGraph interrupt approvals) is
    # deliberately omitted — counting pending interrupts from the checkpointer
    # is not cheap or reliable to query yet.


class SummaryRecentChange(BaseModel):
    occurred_at: datetime
    kind: str
    title: str
    actor_display_name: str


class EngagementSummaryRead(BaseModel):
    engagement: SummaryEngagement
    members: list[SummaryMember]
    counts: SummaryCounts
    recent_changes: list[SummaryRecentChange]


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    row = (
        await session.execute(
            select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return row


async def _load_members(session: AsyncSession, engagement_id: uuid.UUID) -> list[SummaryMember]:
    rows = await session.execute(
        select(EngagementMember, AppUser)
        .join(AppUser, AppUser.id == EngagementMember.user_id)
        .where(EngagementMember.engagement_id == engagement_id)
        .order_by(EngagementMember.created_at)
    )
    members: list[SummaryMember] = []
    for member, user in rows.all():
        members.append(
            SummaryMember(
                user_id=member.user_id,
                display_name=user_display_name(
                    user_name=user.user_name,
                    email=user.email,
                    given_name=user.given_name,
                    family_name=user.family_name,
                ),
                email=user.email,
                role=member.role,
            )
        )
    return members


async def _load_counts(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> SummaryCounts:
    # One grouped query over (node_type, status) — cardinality is tiny — then
    # the risk open/closed convention is applied in Python.
    node_rows = (
        await session.execute(
            select(MatrixNode.node_type, MatrixNode.status, func.count())
            .where(MatrixNode.engagement_id == engagement_id)
            .group_by(MatrixNode.node_type, MatrixNode.status)
        )
    ).all()
    stakeholders = decisions = commitments = risks_open = 0
    for node_type, node_status, count in node_rows:
        if node_type == "stakeholder":
            stakeholders += count
        elif node_type == "decision":
            decisions += count
        elif node_type == "commitment":
            commitments += count
        elif node_type == "risk" and is_risk_open(node_status):
            risks_open += count

    proposals_pending = int(
        (
            await session.execute(
                select(func.count())
                .select_from(MatrixProposal)
                .where(
                    MatrixProposal.engagement_id == engagement_id,
                    MatrixProposal.status == "pending",
                )
            )
        ).scalar_one()
    )

    review_rows = (
        await session.execute(
            select(ReviewItem.kind, func.count())
            .where(
                ReviewItem.tenant_id == tenant_id,
                ReviewItem.engagement_id == engagement_id,
                ReviewItem.status == "open",
                ReviewItem.kind.in_(("agent_escalation", "citation_dispute")),
            )
            .group_by(ReviewItem.kind)
        )
    ).all()
    review_counts = {kind: int(count) for kind, count in review_rows}

    return SummaryCounts(
        stakeholders=stakeholders,
        decisions=decisions,
        risks_open=risks_open,
        commitments=commitments,
        proposals_pending=proposals_pending,
        escalations_open=review_counts.get("agent_escalation", 0),
        disputes_open=review_counts.get("citation_dispute", 0),
    )


async def _load_recent_changes(
    session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID
) -> list[SummaryRecentChange]:
    events = list(
        (
            await session.execute(
                select(LedgerEvent)
                .where(
                    LedgerEvent.tenant_id == tenant_id,
                    LedgerEvent.engagement_id == engagement_id,
                )
                .order_by(LedgerEvent.occurred_at.desc(), LedgerEvent.recorded_at.desc())
                .limit(_RECENT_CHANGES_LIMIT)
            )
        ).scalars()
    )

    # Batch-resolve UUID-shaped actor ids against app_users in one query.
    actor_uuids: set[uuid.UUID] = set()
    for ev in events:
        if ev.actor_id:
            try:
                actor_uuids.add(uuid.UUID(ev.actor_id))
            except ValueError:
                continue
    names_by_user_id: dict[str, str] = {}
    if actor_uuids:
        user_rows = (
            await session.execute(select(AppUser).where(AppUser.tenant_id == tenant_id, AppUser.id.in_(actor_uuids)))
        ).scalars()
        for user in user_rows:
            names_by_user_id[str(user.id)] = user_display_name(
                user_name=user.user_name,
                email=user.email,
                given_name=user.given_name,
                family_name=user.family_name,
            )

    return [
        SummaryRecentChange(
            occurred_at=ev.occurred_at,
            kind=bucket_for_source_kind(ev.source_kind),
            title=humanize_event_title(ev.source_kind, ev.summary),
            actor_display_name=actor_display_name(ev.actor_kind, ev.actor_id, names_by_user_id),
        )
        for ev in events
    ]


@router.get(
    "/{engagement_id}/summary",
    response_model=EngagementSummaryRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def get_engagement_summary(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> EngagementSummaryRead:
    """First-paint summary for the engagement page — one round trip, no N+1."""
    eng = await _require_engagement(session, tenant_id, engagement_id)
    members = await _load_members(session, engagement_id)
    counts = await _load_counts(session, tenant_id, engagement_id)
    recent_changes = await _load_recent_changes(session, tenant_id, engagement_id)
    return EngagementSummaryRead(
        engagement=SummaryEngagement(
            id=eng.id,
            name=eng.name,
            customer_account=eng.customer_account,
            current_phase=eng.current_phase,
            status=eng.status,
            updated_at=eng.updated_at,
        ),
        members=members,
        counts=counts,
        recent_changes=recent_changes,
    )
