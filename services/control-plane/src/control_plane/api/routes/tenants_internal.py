"""Internal API — tenants / portfolio insights (Phase 7 increment 7.4).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; the
``{tenant_id}`` path segment scopes every query.

The per-engagement Oracle (7.2) lives in ``engagements_internal.py`` —
this module holds the *tenant-scoped* counterpart: the Master Strategist
cross-engagement insights, plus dismiss/resolve for tenant-scoped rows
(which can't share the engagement-scoped paths because their
``engagement_id`` is null).

See ``docs/product/synthesis-agents.md`` §4, §11.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider
from control_plane.agents.master_strategist import (
    MasterStrategistCandidate,
    PortfolioEdge,
    PortfolioEngagement,
    PortfolioNode,
    master_strategist_candidates,
    master_strategist_phrase,
)
from control_plane.agents.oracle import InsightDraft
from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.canonical_memory.matrix import (
    INSIGHT_STATUSES,
    MatrixEdge,
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.engagement import Engagement, EngagementMember

router = APIRouter(prefix="/tenants", tags=["internal-tenants"])


class TenantInsightRead(BaseModel):
    """Mirrors ``MatrixInsightRead`` from engagements_internal — re-declared
    here so this module is self-contained and the imports stay one-way."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    agent: str
    insight_type: str
    severity: str
    title: str
    body: str
    citation_node_ids: list[uuid.UUID]
    citation_edge_ids: list[uuid.UUID]
    citation_event_ids: list[uuid.UUID]
    dedup_key: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None


class TenantInsightDecision(BaseModel):
    actor_id: str | None = Field(default=None, max_length=200)


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AppTenant:
    row = await session.get(AppTenant, tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return row


@router.get(
    "/{tenant_id}/insights",
    response_model=list[TenantInsightRead],
    dependencies=[Depends(require_internal)],
)
async def list_tenant_insights(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = "open",
) -> list[MatrixInsight]:
    await _require_tenant(session, tenant_id)
    # Only tenant-scoped rows (Master Strategist output) — engagement_id IS NULL.
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id.is_(None),
    )
    if status_filter is not None:
        if status_filter not in INSIGHT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid status: {status_filter}",
            )
        stmt = stmt.where(MatrixInsight.status == status_filter)
    r = await session.execute(stmt.order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc()))
    return list(r.scalars().all())


async def _decide_tenant_insight(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    new_status: str,
    actor_id: str | None,
) -> MatrixInsight:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
            MatrixInsight.id == insight_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="insight not found")
    if row.status != "open":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"insight is not open (status={row.status})",
        )
    row.status = new_status
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor_id
    await session.commit()
    await session.refresh(row)
    return row


@router.post(
    "/{tenant_id}/insights/{insight_id}/dismiss",
    response_model=TenantInsightRead,
    dependencies=[Depends(require_internal)],
)
async def dismiss_tenant_insight(
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TenantInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> MatrixInsight:
    return await _decide_tenant_insight(session, tenant_id, insight_id, "dismissed", body.actor_id)


@router.post(
    "/{tenant_id}/insights/{insight_id}/resolve",
    response_model=TenantInsightRead,
    dependencies=[Depends(require_internal)],
)
async def resolve_tenant_insight(
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TenantInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> MatrixInsight:
    return await _decide_tenant_insight(session, tenant_id, insight_id, "resolved", body.actor_id)


@router.post(
    "/{tenant_id}/insights/refresh",
    response_model=list[TenantInsightRead],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal)],
)
async def refresh_tenant_insights(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> list[MatrixInsight]:
    """Run the Master Strategist over the tenant's portfolio.

    Tenant-scoped twin of ``refresh_matrix_insights`` (Oracle, engagements
    router). Same dedup_key upsert + auto-resolve semantics — see design §11.
    """
    tenant = await _require_tenant(session, tenant_id)

    # Snapshot: every engagement + its matrix + member roles.
    eng_q = await session.execute(select(Engagement).where(Engagement.tenant_id == tenant_id))
    engagements_rows = list(eng_q.scalars().all())

    portfolio: list[PortfolioEngagement] = []
    for eng in engagements_rows:
        members_q = await session.execute(select(EngagementMember).where(EngagementMember.engagement_id == eng.id))
        roles = tuple(m.role for m in members_q.scalars().all())
        nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == eng.id))
        nodes = tuple(
            PortfolioNode(
                id=n.id,
                node_type=n.node_type,
                title=n.title,
                attributes=n.attributes or {},
            )
            for n in nodes_q.scalars().all()
        )
        edges_q = await session.execute(select(MatrixEdge).where(MatrixEdge.engagement_id == eng.id))
        edges = tuple(
            PortfolioEdge(
                id=e.id,
                edge_type=e.edge_type,
                from_node_id=e.from_node_id,
                to_node_id=e.to_node_id,
            )
            for e in edges_q.scalars().all()
        )
        portfolio.append(
            PortfolioEngagement(
                id=eng.id,
                name=eng.name,
                status=eng.status,
                current_phase=eng.current_phase,
                member_roles=roles,
                nodes=nodes,
                edges=edges,
            )
        )

    candidates = master_strategist_candidates(tenant_id=tenant_id, engagements=portfolio)

    existing_q = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
        )
    )
    existing: dict[str, MatrixInsight] = {row.dedup_key: row for row in existing_q.scalars().all()}

    to_phrase: list[MasterStrategistCandidate] = []
    for c in candidates:
        prev = existing.get(c.dedup_key)
        if prev is None:
            to_phrase.append(c)
            continue
        if prev.status == "dismissed":
            continue
        if prev.status == "open" and prev.input_hash == c.input_hash:
            continue
        to_phrase.append(c)

    drafts: list[InsightDraft] = []
    if to_phrase:
        drafts = master_strategist_phrase(
            tenant_name=tenant.name,
            engagements=portfolio,
            candidates=to_phrase,
            llm=llm,
        )

    drafts_by_key = {d.dedup_key: d for d in drafts}
    for c in to_phrase:
        d = drafts_by_key.get(c.dedup_key)
        if d is None:
            continue
        prev = existing.get(c.dedup_key)
        if prev is None:
            row = MatrixInsight(
                tenant_id=tenant_id,
                engagement_id=None,
                agent="master_strategist",
                insight_type=d.insight_type,
                severity=d.severity,
                title=d.title,
                body=d.body,
                citation_node_ids=list(d.citation_node_ids),
                citation_edge_ids=list(d.citation_edge_ids),
                citation_event_ids=list(d.citation_event_ids),
                dedup_key=d.dedup_key,
                input_hash=d.input_hash,
            )
            session.add(row)
        else:
            prev.severity = d.severity
            prev.title = d.title
            prev.body = d.body
            prev.citation_node_ids = list(d.citation_node_ids)
            prev.citation_edge_ids = list(d.citation_edge_ids)
            prev.input_hash = d.input_hash
            if prev.status == "resolved":
                prev.status = "open"
                prev.decided_at = None
                prev.decided_by = None

    candidate_keys = {c.dedup_key for c in candidates}
    for key, prev in existing.items():
        if prev.status == "open" and key not in candidate_keys:
            prev.status = "resolved"
            prev.decided_at = datetime.now(UTC)
            prev.decided_by = "auto"

    await session.commit()

    final_q = await session.execute(
        select(MatrixInsight)
        .where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
            MatrixInsight.status == "open",
        )
        .order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc())
    )
    return list(final_q.scalars().all())
