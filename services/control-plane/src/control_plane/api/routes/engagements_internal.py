"""Internal API — engagements (Phase 1, team-tracking pivot).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; callers
pass ``tenant_id`` as the scope — an engagement belongs to a tenant (the team).
Tenant filtering is enforced in every query (same posture as the strategist
queues internal API). See ``docs/product/deployai-source-of-truth-spec.md``
section 16 (Phase 1).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.agents.matrix_extractor import (
    ExistingNode,
    extract_matrix_proposals,
)
from control_plane.agents.matrix_extractor import (
    default_system_prompt as matrix_extractor_default_prompt,
)
from control_plane.agents.oracle import (
    EdgeSnapshot as OracleEdgeSnapshot,
)
from control_plane.agents.oracle import (
    EventSnapshot as OracleEventSnapshot,
)
from control_plane.agents.oracle import (
    NodeSnapshot as OracleNodeSnapshot,
)
from control_plane.agents.oracle import (
    OracleCandidate,
    oracle_candidates,
    oracle_phrase,
)
from control_plane.agents.oracle import (
    default_system_prompt as oracle_default_prompt,
)
from control_plane.agents.prompts import resolve_tenant_prompt
from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant, AppUser
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.identity import IdentityNode
from control_plane.domain.canonical_memory.matrix import (
    INSIGHT_STATUSES,
    MATRIX_EDGE_TYPES,
    MATRIX_NODE_TYPES,
    MatrixEdge,
    MatrixInsight,
    MatrixNode,
    MatrixProposal,
)
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.phases.machine import DEPLOYMENT_PHASES, default_phase

# Roles a user can hold on an engagement — the cross-functional team.
_ENGAGEMENT_MEMBER_ROLES: tuple[str, ...] = ("fde", "deployment_strategist", "biz_dev")

router = APIRouter(prefix="/engagements", tags=["internal-engagements"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    customer_account: str | None = Field(default=None, max_length=200)
    current_phase: str = default_phase


class EngagementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    customer_account: str | None
    current_phase: str
    status: str
    created_at: datetime
    updated_at: datetime


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")


@router.get("", response_model=list[EngagementRead], dependencies=[Depends(require_internal)])
async def list_engagements(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[Engagement]:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id).order_by(Engagement.created_at.desc())
    )
    return list(r.scalars().all())


@router.post(
    "",
    response_model=EngagementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_engagement(
    body: EngagementCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Engagement:
    await _require_tenant(session, tenant_id)
    if body.current_phase not in DEPLOYMENT_PHASES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid phase: {body.current_phase}",
        )
    row = Engagement(
        tenant_id=tenant_id,
        name=body.name,
        customer_account=body.customer_account,
        current_phase=body.current_phase,
        status="active",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{engagement_id}", response_model=EngagementRead, dependencies=[Depends(require_internal)])
async def get_engagement(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Engagement:
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return row


# --- Engagement membership (Phase 2, increment 2.2) ---


class EngagementMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: str


class EngagementMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
    )
    eng = r.scalar_one_or_none()
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return eng


@router.get(
    "/{engagement_id}/members",
    response_model=list[EngagementMemberRead],
    dependencies=[Depends(require_internal)],
)
async def list_engagement_members(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[EngagementMember]:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(EngagementMember)
        .where(EngagementMember.engagement_id == engagement_id)
        .order_by(EngagementMember.created_at)
    )
    return list(r.scalars().all())


@router.post(
    "/{engagement_id}/members",
    response_model=EngagementMemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def add_engagement_member(
    engagement_id: uuid.UUID,
    body: EngagementMemberCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> EngagementMember:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.role not in _ENGAGEMENT_MEMBER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid role: {body.role}",
        )
    user = await session.get(AppUser, body.user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found in tenant")
    existing = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user is already a member of this engagement",
        )
    row = EngagementMember(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        user_id=body.user_id,
        role=body.role,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/{engagement_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def remove_engagement_member(
    engagement_id: uuid.UUID,
    member_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.id == member_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    await session.delete(row)
    await session.commit()


# --- Deployment matrix (Phase 5, increment 5.2b) ---
# (Phase 3's engagement-log endpoints were retired in increment 5.5; the
# journal is superseded by the matrix below.)
#
# The matrix is a typed property graph: matrix_nodes joined by matrix_edges,
# engagement-scoped. node_type / edge_type are validated against the catalog
# below (a constant — the extension seam; see docs/product/
# deployment-matrix-model.md). All filtering is app-layer, same posture as the
# rest of this internal API.


class MatrixNodeCreate(BaseModel):
    node_type: str
    title: str = Field(min_length=1, max_length=400)
    identity_node_id: uuid.UUID | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=100)
    evidence_event_ids: list[uuid.UUID] = Field(default_factory=list)


class MatrixNodeUpdate(BaseModel):
    """Partial update — only fields present in the request body are applied."""

    title: str | None = Field(default=None, min_length=1, max_length=400)
    attributes: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=100)
    evidence_event_ids: list[uuid.UUID] | None = None


class MatrixNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    node_type: str
    title: str
    identity_node_id: uuid.UUID | None
    attributes: dict[str, Any]
    status: str | None
    evidence_event_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class MatrixEdgeCreate(BaseModel):
    edge_type: str
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_event_ids: list[uuid.UUID] = Field(default_factory=list)


class MatrixEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    edge_type: str
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    attributes: dict[str, Any]
    evidence_event_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


async def _require_matrix_node(session: AsyncSession, engagement_id: uuid.UUID, node_id: uuid.UUID) -> MatrixNode:
    r = await session.execute(
        select(MatrixNode).where(MatrixNode.engagement_id == engagement_id, MatrixNode.id == node_id)
    )
    node = r.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="matrix node not found")
    return node


@router.post(
    "/{engagement_id}/matrix/nodes",
    response_model=MatrixNodeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_matrix_node(
    engagement_id: uuid.UUID,
    body: MatrixNodeCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixNode:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.node_type not in MATRIX_NODE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid node_type: {body.node_type}",
        )
    if body.identity_node_id is not None:
        identity = await session.get(IdentityNode, body.identity_node_id)
        if identity is None or identity.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="identity_node_id not found in tenant",
            )
    row = MatrixNode(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        node_type=body.node_type,
        title=body.title,
        identity_node_id=body.identity_node_id,
        attributes=body.attributes,
        status=body.status,
        evidence_event_ids=body.evidence_event_ids,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get(
    "/{engagement_id}/matrix/nodes",
    response_model=list[MatrixNodeRead],
    dependencies=[Depends(require_internal)],
)
async def list_matrix_nodes(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    node_type: Annotated[str | None, Query()] = None,
) -> list[MatrixNode]:
    await _require_engagement(session, tenant_id, engagement_id)
    stmt = select(MatrixNode).where(MatrixNode.engagement_id == engagement_id)
    if node_type is not None:
        stmt = stmt.where(MatrixNode.node_type == node_type)
    r = await session.execute(stmt.order_by(MatrixNode.created_at))
    return list(r.scalars().all())


@router.get(
    "/{engagement_id}/matrix/nodes/{node_id}",
    response_model=MatrixNodeRead,
    dependencies=[Depends(require_internal)],
)
async def get_matrix_node(
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixNode:
    await _require_engagement(session, tenant_id, engagement_id)
    return await _require_matrix_node(session, engagement_id, node_id)


@router.patch(
    "/{engagement_id}/matrix/nodes/{node_id}",
    response_model=MatrixNodeRead,
    dependencies=[Depends(require_internal)],
)
async def update_matrix_node(
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
    body: MatrixNodeUpdate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixNode:
    await _require_engagement(session, tenant_id, engagement_id)
    node = await _require_matrix_node(session, engagement_id, node_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    await session.commit()
    await session.refresh(node)
    return node


@router.delete(
    "/{engagement_id}/matrix/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_matrix_node(
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_engagement(session, tenant_id, engagement_id)
    node = await _require_matrix_node(session, engagement_id, node_id)
    # Edges referencing the node are removed by the ON DELETE CASCADE FK.
    await session.delete(node)
    await session.commit()


@router.post(
    "/{engagement_id}/matrix/edges",
    response_model=MatrixEdgeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_matrix_edge(
    engagement_id: uuid.UUID,
    body: MatrixEdgeCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixEdge:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.edge_type not in MATRIX_EDGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid edge_type: {body.edge_type}",
        )
    for label, node_id in (("from_node_id", body.from_node_id), ("to_node_id", body.to_node_id)):
        r = await session.execute(
            select(MatrixNode.id).where(MatrixNode.engagement_id == engagement_id, MatrixNode.id == node_id)
        )
        if r.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{label} not found in this engagement",
            )
    row = MatrixEdge(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        edge_type=body.edge_type,
        from_node_id=body.from_node_id,
        to_node_id=body.to_node_id,
        attributes=body.attributes,
        evidence_event_ids=body.evidence_event_ids,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get(
    "/{engagement_id}/matrix/edges",
    response_model=list[MatrixEdgeRead],
    dependencies=[Depends(require_internal)],
)
async def list_matrix_edges(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[MatrixEdge]:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id).order_by(MatrixEdge.created_at)
    )
    return list(r.scalars().all())


@router.delete(
    "/{engagement_id}/matrix/edges/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_matrix_edge(
    engagement_id: uuid.UUID,
    edge_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id, MatrixEdge.id == edge_id)
    )
    edge = r.scalar_one_or_none()
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="matrix edge not found")
    await session.delete(edge)
    await session.commit()


# --- Ingestion (Phase 6, increment 6.1 — universal one-shot import) ---
#
# An interaction (email / meeting note / field note / manual import) lands
# as one canonical_memory_events row, engagement-scoped. Phase 6.2 layers an
# extraction agent on top that proposes matrix entities citing the event;
# this increment just establishes the data path. dedup_key is honoured
# idempotently — re-ingesting the same key returns the existing event.

_INGEST_SOURCES: tuple[str, ...] = ("manual_import", "meeting_note", "email", "field_note")


class IngestInteractionCreate(BaseModel):
    source: str
    occurred_at: datetime
    content: dict[str, Any]
    source_ref: str | None = Field(default=None, max_length=500)
    dedup_key: str | None = Field(default=None, max_length=500)


class IngestedEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID | None
    event_type: str
    occurred_at: datetime
    source_ref: str | None
    ingestion_dedup_key: str | None
    payload: dict[str, Any]
    created_at: datetime


@router.post(
    "/{engagement_id}/ingest",
    response_model=IngestedEventRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def ingest_interaction(
    engagement_id: uuid.UUID,
    body: IngestInteractionCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> CanonicalMemoryEvent:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.source not in _INGEST_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid source: {body.source}",
        )
    # Idempotency: same (tenant_id, ingestion_dedup_key) returns the existing
    # event. App-layer check — no DB unique constraint on dedup_key (FR18
    # treats the key as advisory).
    if body.dedup_key is not None:
        r = await session.execute(
            select(CanonicalMemoryEvent).where(
                CanonicalMemoryEvent.tenant_id == tenant_id,
                CanonicalMemoryEvent.ingestion_dedup_key == body.dedup_key,
            )
        )
        existing = r.scalar_one_or_none()
        if existing is not None:
            return existing
    row = CanonicalMemoryEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        event_type=f"ingest.{body.source}",
        occurred_at=body.occurred_at,
        source_ref=body.source_ref,
        ingestion_dedup_key=body.dedup_key,
        payload={"content": body.content},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# --- Matrix proposals (Phase 6, increment 6.2a — human review loop) ---
#
# A matrix_proposal references the canonical event it was derived from
# (source_event_id) and carries a payload ready to insert as a matrix node
# or edge. Accept commits it with evidence_event_ids = [source_event_id];
# reject closes it out. The Cartographer extraction agent (6.2b) is what
# produces proposals; this increment is the review-loop infrastructure.


class MatrixProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    source_event_id: uuid.UUID
    proposal_kind: str
    payload: dict[str, Any]
    rationale: str | None
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    result_node_id: uuid.UUID | None
    result_edge_id: uuid.UUID | None


class MatrixProposalDecision(BaseModel):
    """Optional metadata for accept / reject — the BFF passes the actor id."""

    actor_id: str | None = Field(default=None, max_length=200)


async def _require_proposal(session: AsyncSession, engagement_id: uuid.UUID, proposal_id: uuid.UUID) -> MatrixProposal:
    r = await session.execute(
        select(MatrixProposal).where(
            MatrixProposal.engagement_id == engagement_id,
            MatrixProposal.id == proposal_id,
        )
    )
    p = r.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="matrix proposal not found")
    return p


@router.get(
    "/{engagement_id}/proposals",
    response_model=list[MatrixProposalRead],
    dependencies=[Depends(require_internal)],
)
async def list_matrix_proposals(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[str | None, Query(alias="status")] = "pending",
) -> list[MatrixProposal]:
    await _require_engagement(session, tenant_id, engagement_id)
    stmt = select(MatrixProposal).where(MatrixProposal.engagement_id == engagement_id)
    if status_filter is not None:
        stmt = stmt.where(MatrixProposal.status == status_filter)
    r = await session.execute(stmt.order_by(MatrixProposal.created_at))
    return list(r.scalars().all())


@router.post(
    "/{engagement_id}/proposals/{proposal_id}/accept",
    response_model=MatrixProposalRead,
    dependencies=[Depends(require_internal)],
)
async def accept_matrix_proposal(
    engagement_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: MatrixProposalDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixProposal:
    await _require_engagement(session, tenant_id, engagement_id)
    proposal = await _require_proposal(session, engagement_id, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"proposal is not pending (status={proposal.status})",
        )
    payload = proposal.payload or {}
    extra_evidence = payload.get("evidence_event_ids")
    evidence_ids: list[uuid.UUID] = [proposal.source_event_id]
    if isinstance(extra_evidence, list):
        for raw in extra_evidence:
            try:
                evidence_ids.append(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue

    if proposal.proposal_kind == "node":
        node_type = payload.get("node_type") if isinstance(payload.get("node_type"), str) else ""
        title = payload.get("title") if isinstance(payload.get("title"), str) else ""
        if not node_type or not title or node_type not in MATRIX_NODE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="proposal payload must include a valid node_type and a title",
            )
        identity_raw = payload.get("identity_node_id")
        identity_node_id: uuid.UUID | None = None
        if isinstance(identity_raw, str) and identity_raw:
            try:
                identity_node_id = uuid.UUID(identity_raw)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="identity_node_id is not a valid UUID",
                ) from e
            identity = await session.get(IdentityNode, identity_node_id)
            if identity is None or identity.tenant_id != tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="identity_node_id not found in tenant",
                )
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        node_status = payload.get("status") if isinstance(payload.get("status"), str) else None
        node = MatrixNode(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            node_type=node_type,
            title=title,
            identity_node_id=identity_node_id,
            attributes=attributes,
            status=node_status,
            evidence_event_ids=evidence_ids,
        )
        session.add(node)
        await session.flush()
        proposal.result_node_id = node.id
    elif proposal.proposal_kind == "edge":
        edge_type = payload.get("edge_type") if isinstance(payload.get("edge_type"), str) else ""
        if not edge_type or edge_type not in MATRIX_EDGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="proposal payload must include a valid edge_type",
            )
        try:
            from_node_id = uuid.UUID(str(payload.get("from_node_id")))
            to_node_id = uuid.UUID(str(payload.get("to_node_id")))
        except (TypeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="proposal payload must include valid from_node_id / to_node_id UUIDs",
            ) from e
        for label, node_id in (("from_node_id", from_node_id), ("to_node_id", to_node_id)):
            r = await session.execute(
                select(MatrixNode.id).where(MatrixNode.engagement_id == engagement_id, MatrixNode.id == node_id)
            )
            if r.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"{label} not found in this engagement",
                )
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        edge = MatrixEdge(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            edge_type=edge_type,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            attributes=attributes,
            evidence_event_ids=evidence_ids,
        )
        session.add(edge)
        await session.flush()
        proposal.result_edge_id = edge.id
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown proposal_kind: {proposal.proposal_kind}",
        )

    proposal.status = "accepted"
    proposal.decided_at = datetime.now(UTC)
    proposal.decided_by = body.actor_id
    await session.commit()
    await session.refresh(proposal)
    return proposal


@router.post(
    "/{engagement_id}/proposals/{proposal_id}/reject",
    response_model=MatrixProposalRead,
    dependencies=[Depends(require_internal)],
)
async def reject_matrix_proposal(
    engagement_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: MatrixProposalDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixProposal:
    await _require_engagement(session, tenant_id, engagement_id)
    proposal = await _require_proposal(session, engagement_id, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"proposal is not pending (status={proposal.status})",
        )
    proposal.status = "rejected"
    proposal.decided_at = datetime.now(UTC)
    proposal.decided_by = body.actor_id
    await session.commit()
    await session.refresh(proposal)
    return proposal


# --- Matrix extraction agent (Phase 6, increment 6.2c — Cartographer) ---


@router.post(
    "/{engagement_id}/extract",
    response_model=list[MatrixProposalRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def extract_engagement_proposals(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    event_id: Annotated[uuid.UUID, Query()],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    force: Annotated[bool, Query()] = False,
) -> list[MatrixProposal]:
    """Run the matrix-extraction agent on one canonical event.

    Idempotent by ``(tenant, event_id)``: if proposals already exist for the
    event and ``force`` is false, returns them without calling the LLM.
    ``force=true`` deletes the event's *pending* proposals and re-runs
    (accepted / rejected proposals are preserved as history).
    """
    await _require_engagement(session, tenant_id, engagement_id)
    llm = await resolve_tenant_llm_provider(session, tenant_id, llm)
    extractor_prompt = await resolve_tenant_prompt(
        session, tenant_id, "cartographer", matrix_extractor_default_prompt()
    )
    event_row = await session.execute(
        select(CanonicalMemoryEvent).where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
            CanonicalMemoryEvent.id == event_id,
        )
    )
    event = event_row.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="canonical event not found")

    existing_q = await session.execute(
        select(MatrixProposal).where(MatrixProposal.source_event_id == event_id).order_by(MatrixProposal.created_at)
    )
    existing = list(existing_q.scalars().all())

    if existing and not force:
        return existing
    if force:
        for p in existing:
            if p.status == "pending":
                await session.delete(p)
        await session.flush()

    nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))
    nodes = list(nodes_q.scalars().all())
    context = [ExistingNode(id=n.id, title=n.title, node_type=n.node_type) for n in nodes]

    drafts = await asyncio.to_thread(
        extract_matrix_proposals,
        event_id=event.id,
        event_source=event.event_type,
        event_occurred_at=event.occurred_at,
        event_payload=event.payload,
        existing_nodes=context,
        llm=llm,
        system_prompt=extractor_prompt,
    )

    created: list[MatrixProposal] = []
    for d in drafts:
        row = MatrixProposal(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            source_event_id=event.id,
            proposal_kind=d.kind,
            payload=d.payload,
            rationale=d.rationale,
        )
        session.add(row)
        created.append(row)
    await session.commit()
    for r in created:
        await session.refresh(r)
    # When force was used, history-preserved (accepted/rejected) rows that
    # were not deleted should appear alongside the new pending rows.
    if force:
        kept = [p for p in existing if p.status != "pending"]
        return kept + created
    return created


# --- Matrix insights — Oracle (Phase 7, increment 7.2) ----------------------
#
# Insights are observations the Oracle agent produces from the matrix +
# recent canonical events. Refresh runs deterministic predicates, computes
# a per-candidate ``dedup_key`` + ``input_hash``, then calls the LLM only
# for candidates whose inputs changed (or whose row was previously resolved
# and now fires again). Dismissed rows stick — refresh never re-surfaces
# something the user already triaged. Open rows whose dedup_key no longer
# fires are auto-resolved (the underlying problem went away). Full design:
# ``docs/product/synthesis-agents.md``.

# Cap how far back we look for canonical events when building the snapshot.
_INSIGHT_RECENT_EVENTS_DAYS = 90
_INSIGHT_RECENT_EVENTS_CAP = 50


class MatrixInsightRead(BaseModel):
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


class MatrixInsightDecision(BaseModel):
    """Optional metadata for dismiss/resolve — the BFF passes the actor id."""

    actor_id: str | None = Field(default=None, max_length=200)


def _event_text_for_oracle(event: CanonicalMemoryEvent) -> str:
    """Pick a reasonable short summary text from a canonical event payload."""
    payload = event.payload or {}
    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text[:400]
    return f"{event.event_type} at {event.occurred_at.isoformat()}"


@router.get(
    "/{engagement_id}/insights",
    response_model=list[MatrixInsightRead],
    dependencies=[Depends(require_internal)],
)
async def list_matrix_insights(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[str | None, Query(alias="status")] = "open",
) -> list[MatrixInsight]:
    await _require_engagement(session, tenant_id, engagement_id)
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
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


async def _decide_insight(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
    new_status: str,
    actor_id: str | None,
) -> MatrixInsight:
    """Shared dismiss/resolve helper."""
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id == engagement_id,
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
    "/{engagement_id}/insights/{insight_id}/dismiss",
    response_model=MatrixInsightRead,
    dependencies=[Depends(require_internal)],
)
async def dismiss_matrix_insight(
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: MatrixInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixInsight:
    return await _decide_insight(session, tenant_id, engagement_id, insight_id, "dismissed", body.actor_id)


@router.post(
    "/{engagement_id}/insights/{insight_id}/resolve",
    response_model=MatrixInsightRead,
    dependencies=[Depends(require_internal)],
)
async def resolve_matrix_insight(
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: MatrixInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixInsight:
    return await _decide_insight(session, tenant_id, engagement_id, insight_id, "resolved", body.actor_id)


@router.post(
    "/{engagement_id}/insights/refresh",
    response_model=list[MatrixInsightRead],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal)],
)
async def refresh_matrix_insights(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> list[MatrixInsight]:
    """Run the Oracle synthesis agent on the engagement and upsert insights.

    Returns the full list of ``open`` insights after the upsert. See the
    design record §11 for the idempotency rules.
    """
    engagement = await _require_engagement(session, tenant_id, engagement_id)
    llm = await resolve_tenant_llm_provider(session, tenant_id, llm)
    oracle_prompt = await resolve_tenant_prompt(session, tenant_id, "oracle", oracle_default_prompt())

    nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))
    nodes = list(nodes_q.scalars().all())
    edges_q = await session.execute(select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id))
    edges = list(edges_q.scalars().all())
    cutoff = datetime.now(UTC) - timedelta(days=_INSIGHT_RECENT_EVENTS_DAYS)
    events_q = await session.execute(
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
            CanonicalMemoryEvent.occurred_at >= cutoff,
        )
        .order_by(CanonicalMemoryEvent.occurred_at.desc())
        .limit(_INSIGHT_RECENT_EVENTS_CAP)
    )
    events = list(events_q.scalars().all())

    node_snapshots = [
        OracleNodeSnapshot(
            id=n.id,
            node_type=n.node_type,
            title=n.title,
            attributes=n.attributes or {},
            evidence_event_ids=tuple(n.evidence_event_ids or ()),
        )
        for n in nodes
    ]
    edge_snapshots = [
        OracleEdgeSnapshot(
            id=e.id,
            edge_type=e.edge_type,
            from_node_id=e.from_node_id,
            to_node_id=e.to_node_id,
        )
        for e in edges
    ]
    event_snapshots = [
        OracleEventSnapshot(
            id=e.id,
            occurred_at=e.occurred_at,
            event_type=e.event_type,
            text=_event_text_for_oracle(e),
        )
        for e in events
    ]

    candidates = oracle_candidates(
        engagement_id=engagement_id,
        nodes=node_snapshots,
        edges=edge_snapshots,
        recent_events=event_snapshots,
    )

    # Index existing insights for this engagement by dedup_key (any status).
    existing_q = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id == engagement_id,
        )
    )
    existing: dict[str, MatrixInsight] = {row.dedup_key: row for row in existing_q.scalars().all()}

    # Decide which candidates need the LLM call.
    to_phrase: list[OracleCandidate] = []
    for c in candidates:
        prev = existing.get(c.dedup_key)
        if prev is None:
            to_phrase.append(c)
            continue
        if prev.status == "dismissed":
            continue  # user already triaged; never re-surface
        if prev.status == "open" and prev.input_hash == c.input_hash:
            continue  # unchanged; skip LLM, leave row untouched
        # open w/ changed input_hash, or resolved that should re-open
        to_phrase.append(c)

    drafts = []
    if to_phrase:
        drafts = oracle_phrase(
            engagement_name=engagement.name,
            engagement_phase=engagement.current_phase,
            nodes=node_snapshots,
            edges=edge_snapshots,
            candidates=to_phrase,
            llm=llm,
            system_prompt=oracle_prompt,
        )

    # Apply drafts: upsert by dedup_key.
    drafts_by_key = {d.dedup_key: d for d in drafts}
    for c in to_phrase:
        d = drafts_by_key.get(c.dedup_key)
        if d is None:
            # LLM either dropped this candidate (empty title) or failed.
            # If a previous open row exists, leave it as-is (rather than
            # silently regressing). If none, just skip.
            continue
        prev = existing.get(c.dedup_key)
        if prev is None:
            row = MatrixInsight(
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                agent="oracle",
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
            prev.citation_event_ids = list(d.citation_event_ids)
            prev.input_hash = d.input_hash
            if prev.status == "resolved":
                # Predicate fires again — re-open. Decided_at/by stay as the
                # last decision for history, the status flip is the new signal.
                prev.status = "open"
                prev.decided_at = None
                prev.decided_by = None

    # Auto-resolve open rows whose dedup_key no longer fires.
    candidate_keys = {c.dedup_key for c in candidates}
    for key, prev in existing.items():
        if prev.status == "open" and key not in candidate_keys:
            prev.status = "resolved"
            prev.decided_at = datetime.now(UTC)
            prev.decided_by = "auto"

    await session.commit()

    # Return open rows for the engagement, severity desc then created desc.
    final_q = await session.execute(
        select(MatrixInsight)
        .where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id == engagement_id,
            MatrixInsight.status == "open",
        )
        .order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc())
    )
    return list(final_q.scalars().all())
