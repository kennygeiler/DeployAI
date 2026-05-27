"""Internal API — engagements (Phase 1, team-tracking pivot).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; callers
pass ``tenant_id`` as the scope — an engagement belongs to a tenant (the team).
Tenant filtering is enforced in every query (same posture as the strategist
queues internal API). See ``docs/product/deployai-source-of-truth-spec.md``
section 16 (Phase 1).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
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
    MatrixEdge,
    MatrixInsight,
    MatrixNode,
    MatrixProposal,
)
from control_plane.domain.canonical_memory.node_types import (
    list_tenant_node_types,
    resolve_allowed_node_types,
)
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.domain.ledger import LedgerEvent, TemporalInsight
from control_plane.domain.matrix_snapshot import MatrixSnapshot
from control_plane.domain.member_roles import resolve_allowed_member_roles
from control_plane.domain.strategist_queues import StrategistActionQueueItem
from control_plane.ledger import emit_ledger_event
from control_plane.phases.machine import DEPLOYMENT_PHASES, default_phase
from control_plane.webhooks.dispatcher import dispatch as dispatch_webhook

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


_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EngagementMemberCreate(BaseModel):
    user_id: uuid.UUID | None = None
    email: str | None = Field(default=None, max_length=320)
    role: str

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> EngagementMemberCreate:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("provide exactly one of user_id, email")
        if self.email is not None and not _EMAIL_SHAPE.match(self.email):
            raise ValueError("email must look like local@domain.tld")
        return self


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


async def _find_stakeholder_node_by_email(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    email: str,
) -> uuid.UUID | None:
    """Return a stakeholder matrix_node id whose ``attributes->>'email'`` matches.

    Case-insensitive. Returns the first match (engagement-scoped, stakeholder-typed).
    """
    needle = email.strip().lower()
    if not needle:
        return None
    r = await session.execute(
        select(MatrixNode.id).where(
            MatrixNode.engagement_id == engagement_id,
            MatrixNode.node_type == "stakeholder",
            func.lower(MatrixNode.attributes["email"].astext) == needle,
        )
    )
    return r.scalars().first()


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
    allowed_roles = await resolve_allowed_member_roles(session, tenant_id)
    if body.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid role: {body.role}",
        )

    user: AppUser | None = None
    user_provisioned = False
    if body.user_id is not None:
        user = await session.get(AppUser, body.user_id)
        if user is None or user.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found in tenant")
    else:
        email = (body.email or "").strip()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="email must not be blank",
            )
        # case-insensitive lookup scoped to tenant — typo dedupe per design §3
        match = await session.execute(
            select(AppUser).where(
                AppUser.tenant_id == tenant_id,
                func.lower(AppUser.email) == email.lower(),
            )
        )
        user = match.scalars().first()
        if user is None:
            user = AppUser(tenant_id=tenant_id, user_name=email.lower(), email=email)
            session.add(user)
            await session.flush()
            user_provisioned = True
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="user",
                actor_id=None,
                source_kind="user_provisioned",
                source_ref=user.id,
                summary=f"user provisioned: {email}"[:500],
                detail={"email": email, "user_name": user.user_name},
                affects=[("app_user", user.id)],
            )

    existing = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
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
        user_id=user.id,
        role=body.role,
    )
    session.add(row)
    await session.flush()
    member_detail: dict[str, Any] = {
        "role": row.role,
        "user_id": str(user.id),
        "user_provisioned": user_provisioned,
    }
    # Synthesis-dispatch hint: when the added user's email matches a
    # stakeholder matrix_node in the same engagement, hand that node id to
    # the emitter so it can enqueue a stakeholder_brief refresh.
    if user.email:
        stakeholder_id = await _find_stakeholder_node_by_email(session, engagement_id=engagement_id, email=user.email)
        if stakeholder_id is not None:
            member_detail["stakeholder_node_id"] = str(stakeholder_id)
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="member_added",
        source_ref=row.id,
        summary=f"member added: {row.role}"[:500],
        detail=member_detail,
    )
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
    node_type: str | None = None
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
    allowed = await resolve_allowed_node_types(session, tenant_id)
    if body.node_type not in allowed:
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
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="matrix_node_created",
        source_ref=row.id,
        summary=f"node created: {row.title}"[:500],
        detail={"node_type": row.node_type, "title": row.title},
        affects=[("matrix_node", row.id)],
    )
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
    changes = body.model_dump(exclude_unset=True)
    if "node_type" in changes:
        allowed = await resolve_allowed_node_types(session, tenant_id)
        if changes["node_type"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid node_type: {changes['node_type']}",
            )
    for key, value in changes.items():
        setattr(node, key, value)
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="matrix_node_updated",
        source_ref=node.id,
        summary=f"node updated: {node.title}"[:500],
        detail={"node_type": node.node_type, "fields_changed": sorted(changes.keys())},
        affects=[("matrix_node", node.id)],
    )
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
    node_title = node.title
    node_type = node.node_type
    deleted_id = node.id
    # Edges referencing the node are removed by the ON DELETE CASCADE FK.
    await session.delete(node)
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="matrix_node_deleted",
        source_ref=deleted_id,
        summary=f"node deleted: {node_title}"[:500],
        detail={"node_type": node_type, "title": node_title},
    )
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
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="matrix_edge_created",
        source_ref=row.id,
        summary=f"edge created: {row.edge_type}"[:500],
        detail={
            "edge_type": row.edge_type,
            "from_node_id": str(row.from_node_id),
            "to_node_id": str(row.to_node_id),
        },
        affects=[("matrix_edge", row.id)],
    )
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
    edge_type = edge.edge_type
    from_id = edge.from_node_id
    to_id = edge.to_node_id
    deleted_id = edge.id
    await session.delete(edge)
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="matrix_edge_deleted",
        source_ref=deleted_id,
        summary=f"edge deleted: {edge_type}"[:500],
        detail={
            "edge_type": edge_type,
            "from_node_id": str(from_id),
            "to_node_id": str(to_id),
        },
        affects=[("matrix_edge", deleted_id)],
    )
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


async def _proposal_created_event_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
) -> list[uuid.UUID]:
    """IDs of `llm_proposal_created` ledger rows for this proposal — usually one."""
    rows = await session.execute(
        select(LedgerEvent.id).where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.source_kind == "llm_proposal_created",
            LedgerEvent.source_ref == proposal_id,
        )
    )
    return [r for (r,) in rows.all()]


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


async def _accept_one_proposal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    proposal: MatrixProposal,
    actor_id: str | None,
    allowed_node_types: frozenset[str] | set[str] | None = None,
) -> MatrixProposal:
    """Accept one matrix proposal: commit the proposed node or edge.

    The caller owns the transaction — this helper flushes (so the new row's
    id is visible) and emits the ``proposal_accepted`` ledger event, but
    never commits. The single-accept route wraps a commit around it; the
    bulk-accept route commits each call independently so a payload that
    blows up does not roll back the rows that already landed.
    """
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
        allowed = allowed_node_types
        if allowed is None:
            allowed = await resolve_allowed_node_types(session, tenant_id)
        if not node_type or not title or node_type not in allowed:
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
    proposal.decided_by = actor_id
    await session.flush()
    affects: list[tuple[str, uuid.UUID]] = []
    if proposal.result_node_id is not None:
        affects.append(("matrix_node", proposal.result_node_id))
    if proposal.result_edge_id is not None:
        affects.append(("matrix_edge", proposal.result_edge_id))
    caused_by = await _proposal_created_event_ids(session, tenant_id, proposal.id)
    accept_detail: dict[str, Any] = {
        "proposal_kind": proposal.proposal_kind,
        "result_node_id": str(proposal.result_node_id) if proposal.result_node_id else None,
        "result_edge_id": str(proposal.result_edge_id) if proposal.result_edge_id else None,
    }
    # Synthesis-dispatch hint: emitter._maybe_enqueue_synthesis reads node_type
    # off detail to decide which refresh job (if any) to enqueue.
    if proposal.proposal_kind == "node":
        accepted_node_type = payload.get("node_type")
        if isinstance(accepted_node_type, str) and accepted_node_type:
            accept_detail["node_type"] = accepted_node_type
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=actor_id,
        source_kind="proposal_accepted",
        source_ref=proposal.id,
        summary=f"proposal accepted: {proposal.proposal_kind}"[:500],
        detail=accept_detail,
        caused_by=caused_by,
        affects=affects,
    )
    return proposal


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
    await _accept_one_proposal(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        proposal=proposal,
        actor_id=body.actor_id,
    )
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
    await session.flush()
    caused_by = await _proposal_created_event_ids(session, tenant_id, proposal.id)
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=body.actor_id,
        source_kind="proposal_rejected",
        source_ref=proposal.id,
        summary=f"proposal rejected: {proposal.proposal_kind}"[:500],
        detail={"proposal_kind": proposal.proposal_kind},
        caused_by=caused_by,
    )
    await session.commit()
    await session.refresh(proposal)
    return proposal


# --- Matrix proposals — bulk accept ------------------------------------------
#
# One endpoint, two input modes (mutually exclusive): an explicit ``proposal_ids``
# list, or a ``filter`` block (e.g. ``{"status": "pending", "proposal_kind":
# "node"}``). The caller may not pass both. Implementation is a thin wrapper
# over ``_accept_one_proposal`` — no validation logic is duplicated. Nodes are
# accepted before edges in the same batch so an edge proposal that references
# a node also being accepted has its FK target in place.

_BULK_ACCEPT_BATCH_CAP = 500


class BulkAcceptFilter(BaseModel):
    """Filter expression for ``BulkAcceptBody.filter`` — server-side selection."""

    status: str | None = Field(default="pending", max_length=50)
    proposal_kind: str | None = Field(default=None, max_length=50)


class BulkAcceptBody(BaseModel):
    """Bulk-accept body: pass an explicit id list OR a filter, not both."""

    proposal_ids: list[uuid.UUID] | None = None
    filter: BulkAcceptFilter | None = None
    actor_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def one_of_ids_or_filter(self) -> BulkAcceptBody:
        if (self.proposal_ids is None) == (self.filter is None):
            raise ValueError("provide exactly one of proposal_ids, filter")
        if self.proposal_ids is not None and len(self.proposal_ids) == 0:
            raise ValueError("proposal_ids must not be empty")
        return self


class BulkAcceptFailure(BaseModel):
    id: uuid.UUID
    error: str


class BulkAcceptResponse(BaseModel):
    accepted: int
    failed: list[BulkAcceptFailure]
    skipped: int


@router.post(
    "/{engagement_id}/proposals/accept-bulk",
    response_model=BulkAcceptResponse,
    dependencies=[Depends(require_internal)],
)
async def bulk_accept_matrix_proposals(
    engagement_id: uuid.UUID,
    body: BulkAcceptBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> BulkAcceptResponse:
    """Accept a batch of matrix proposals in one request.

    Order: node proposals first, edges second (edge payloads may reference
    node ids that just landed in this same batch). Each accept lands in its
    own transaction so one bad payload does not roll back its neighbours.
    Returns a per-id failure list alongside the accepted count.
    """
    await _require_engagement(session, tenant_id, engagement_id)

    if body.proposal_ids is not None and len(body.proposal_ids) > _BULK_ACCEPT_BATCH_CAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"batch size exceeds cap ({_BULK_ACCEPT_BATCH_CAP})",
        )

    # Load the candidate rows. For an explicit list we keep the caller's
    # order intact (within kind) so test expectations are stable; for filter
    # mode we order by ``created_at`` like the list endpoint does.
    skipped = 0
    candidates: list[MatrixProposal] = []
    if body.proposal_ids is not None:
        rows_q = await session.execute(
            select(MatrixProposal).where(
                MatrixProposal.tenant_id == tenant_id,
                MatrixProposal.engagement_id == engagement_id,
                MatrixProposal.id.in_(body.proposal_ids),
            )
        )
        rows = list(rows_q.scalars().all())
        by_id = {row.id: row for row in rows}
        for pid in body.proposal_ids:
            row = by_id.get(pid)
            if row is None:
                # not visible to this engagement/tenant — treat as skipped
                skipped += 1
                continue
            candidates.append(row)
    else:
        assert body.filter is not None
        stmt = select(MatrixProposal).where(
            MatrixProposal.tenant_id == tenant_id,
            MatrixProposal.engagement_id == engagement_id,
        )
        if body.filter.status is not None:
            stmt = stmt.where(MatrixProposal.status == body.filter.status)
        if body.filter.proposal_kind is not None:
            stmt = stmt.where(MatrixProposal.proposal_kind == body.filter.proposal_kind)
        rows_q = await session.execute(stmt.order_by(MatrixProposal.created_at))
        candidates = list(rows_q.scalars().all())
        if len(candidates) > _BULK_ACCEPT_BATCH_CAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"batch size exceeds cap ({_BULK_ACCEPT_BATCH_CAP})",
            )

    # Always accept nodes before edges — edges may FK-reference a node id
    # that is also being accepted in this batch.
    node_proposals = [p for p in candidates if p.proposal_kind == "node"]
    edge_proposals = [p for p in candidates if p.proposal_kind == "edge"]
    other = [p for p in candidates if p.proposal_kind not in ("node", "edge")]
    ordered = node_proposals + edge_proposals + other

    # Resolve allowed node types once for the whole batch (the helper
    # accepts a pre-resolved set so per-row callers do not re-query).
    allowed_node_types = await resolve_allowed_node_types(session, tenant_id)

    accepted_count = 0
    failures: list[BulkAcceptFailure] = []
    node_accepted = 0
    edge_accepted = 0
    other_skipped = 0

    for proposal in ordered:
        proposal_id = proposal.id
        try:
            await _accept_one_proposal(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                proposal=proposal,
                actor_id=body.actor_id,
                allowed_node_types=allowed_node_types,
            )
            await session.commit()
            accepted_count += 1
            if proposal.proposal_kind == "node":
                node_accepted += 1
            elif proposal.proposal_kind == "edge":
                edge_accepted += 1
            else:
                other_skipped += 1
        except HTTPException as exc:
            await session.rollback()
            failures.append(BulkAcceptFailure(id=proposal_id, error=str(exc.detail)))
        except Exception as exc:  # defensive: never abort the batch
            await session.rollback()
            failures.append(BulkAcceptFailure(id=proposal_id, error=str(exc)[:500]))

    # One audit row that records the batch outcome. Lives outside the
    # per-row transactions so it always lands, even when every row failed.
    audit_detail: dict[str, Any] = {
        "requested": len(candidates),
        "accepted": accepted_count,
        "failed_count": len(failures),
        "skipped": skipped,
        "kinds_summary": {
            "node_accepted": node_accepted,
            "edge_accepted": edge_accepted,
            "other": other_skipped,
        },
    }
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=body.actor_id,
        source_kind="proposals_bulk_accepted",
        source_ref=None,
        summary=f"bulk accept: {accepted_count}/{len(candidates)} accepted"[:500],
        detail=audit_detail,
    )
    await session.commit()

    return BulkAcceptResponse(accepted=accepted_count, failed=failures, skipped=skipped)


# --- Audit-the-AI: reject an LLM-produced proposal post-hoc (G2.c) -----------
#
# Different from `proposals/{id}/reject` (which acts on a pending proposal):
# audit-decision targets an LLM-produced ledger event (the
# `llm_proposal_created` row), and soft-marks the underlying proposal as
# `audit_rejected` regardless of its current decided state — so the user can
# call out a bad extraction even after they had auto-accepted it. Emits an
# `audit_decision` ledger event with `caused_by` linking to the AI event.


class AuditDecisionBody(BaseModel):
    event_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=2000)


@router.post(
    "/{engagement_id}/audit-decision",
    response_model=MatrixProposalRead,
    dependencies=[Depends(require_internal)],
)
async def audit_decision(
    engagement_id: uuid.UUID,
    body: AuditDecisionBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> MatrixProposal:
    await _require_engagement(session, tenant_id, engagement_id)
    ev_q = await session.execute(
        select(LedgerEvent).where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.engagement_id == engagement_id,
            LedgerEvent.id == body.event_id,
        )
    )
    event = ev_q.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ledger event not found")
    if event.source_ref is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="event has no source_ref to resolve a proposal from",
        )
    p_q = await session.execute(
        select(MatrixProposal).where(
            MatrixProposal.tenant_id == tenant_id,
            MatrixProposal.engagement_id == engagement_id,
            MatrixProposal.id == event.source_ref,
        )
    )
    proposal = p_q.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="matrix proposal not found")
    if proposal.status == "audit_rejected":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="proposal already audit_rejected",
        )
    proposal.status = "audit_rejected"
    proposal.decided_at = datetime.now(UTC)
    await session.flush()
    detail: dict[str, Any] = {"reason": body.reason} if body.reason is not None else {"reason": None}
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="audit_decision",
        source_ref=proposal.id,
        summary=f"audit-rejected: {proposal.proposal_kind}"[:500],
        detail=detail,
        caused_by=[event.id],
        affects=[("matrix_node", proposal.result_node_id)] if proposal.result_node_id else [],
    )
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
    allowed_node_types = await resolve_allowed_node_types(session, tenant_id)

    drafts = await asyncio.to_thread(
        extract_matrix_proposals,
        event_id=event.id,
        event_source=event.event_type,
        event_occurred_at=event.occurred_at,
        event_payload=event.payload,
        existing_nodes=context,
        llm=llm,
        system_prompt=extractor_prompt,
        allowed_node_types=allowed_node_types,
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
    if created:
        await session.flush()
        for r in created:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="agent:matrix_extractor",
                actor_id="cartographer",
                source_kind="llm_proposal_created",
                source_ref=r.id,
                summary=f"proposal drafted: {r.proposal_kind}"[:500],
                detail={
                    "proposal_kind": r.proposal_kind,
                    "source_event_id": str(r.source_event_id),
                },
            )
    await session.commit()
    for r in created:
        await session.refresh(r)
    for r in created:
        await dispatch_webhook(
            session,
            tenant_id,
            "proposal.added",
            {
                "engagement_id": str(engagement_id),
                "proposal_id": str(r.id),
                "proposal_kind": r.proposal_kind,
                "source_event_id": str(r.source_event_id),
            },
        )
    await dispatch_webhook(
        session,
        tenant_id,
        "extraction.completed",
        {
            "engagement_id": str(engagement_id),
            "event_id": str(event.id),
            "proposal_count": len(created),
        },
    )
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
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=actor_id,
        source_kind="insight_closed",
        source_ref=row.id,
        summary=f"insight {new_status}: {row.title}"[:500],
        detail={
            "insight_type": row.insight_type,
            "severity": row.severity,
            "status": new_status,
            "agent": row.agent,
        },
        affects=[("insight", row.id)],
    )
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
    newly_created: list[MatrixInsight] = []
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
            newly_created.append(row)
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
    auto_resolved: list[MatrixInsight] = []
    for key, prev in existing.items():
        if prev.status == "open" and key not in candidate_keys:
            prev.status = "resolved"
            prev.decided_at = datetime.now(UTC)
            prev.decided_by = "auto"
            auto_resolved.append(prev)

    if newly_created or auto_resolved:
        await session.flush()
        for row in newly_created:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="agent:oracle",
                actor_id="oracle",
                source_kind="insight_opened",
                source_ref=row.id,
                summary=f"insight opened: {row.title}"[:500],
                detail={
                    "insight_type": row.insight_type,
                    "severity": row.severity,
                    "agent": row.agent,
                },
                affects=[("insight", row.id)],
            )
        for row in auto_resolved:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="system",
                actor_id="auto",
                source_kind="insight_closed",
                source_ref=row.id,
                summary=f"insight auto-resolved: {row.title}"[:500],
                detail={
                    "insight_type": row.insight_type,
                    "severity": row.severity,
                    "status": "resolved",
                    "agent": row.agent,
                    "reason": "predicate_no_longer_fires",
                },
                affects=[("insight", row.id)],
            )

    await session.commit()

    for row in newly_created:
        await dispatch_webhook(
            session,
            tenant_id,
            "insight.created",
            {
                "engagement_id": str(engagement_id),
                "insight_id": str(row.id),
                "insight_type": row.insight_type,
                "severity": row.severity,
                "title": row.title,
            },
        )

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


# --- Phase D D3.a — engagement-detail aggregate ------------------------------
#
# One-shot fetch backing the engagement-detail page: collapses the six
# sequential CP round-trips the BFF used to issue (engagement, members,
# matrix nodes, matrix edges, pending proposals, custom node types) into a
# single endpoint that also surfaces open insights + a recent-activity tail.
# See docs/perf/engagement-aggregate-query-budget.md.

_AGGREGATE_RECENT_ACTIVITY_LIMIT = 50


class CustomNodeTypeAggregate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    color: str | None


class RecentActivityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    source_ref: str | None


class EngagementDetailRead(BaseModel):
    engagement: EngagementRead
    members: list[EngagementMemberRead]
    matrix_nodes: list[MatrixNodeRead]
    matrix_edges: list[MatrixEdgeRead]
    matrix_proposals: list[MatrixProposalRead]
    custom_node_types: list[CustomNodeTypeAggregate]
    insights: list[MatrixInsightRead]
    recent_activity_events: list[RecentActivityEventRead]


@router.get(
    "/{engagement_id}/detail",
    response_model=EngagementDetailRead,
    dependencies=[Depends(require_internal)],
)
async def get_engagement_detail(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> EngagementDetailRead:
    eng = await _require_engagement(session, tenant_id, engagement_id)

    members_q = await session.execute(
        select(EngagementMember)
        .where(EngagementMember.engagement_id == engagement_id)
        .order_by(EngagementMember.created_at)
    )
    members = list(members_q.scalars().all())

    nodes_q = await session.execute(
        select(MatrixNode).where(MatrixNode.engagement_id == engagement_id).order_by(MatrixNode.created_at)
    )
    nodes = list(nodes_q.scalars().all())

    edges_q = await session.execute(
        select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id).order_by(MatrixEdge.created_at)
    )
    edges = list(edges_q.scalars().all())

    proposals_q = await session.execute(
        select(MatrixProposal)
        .where(
            MatrixProposal.engagement_id == engagement_id,
            MatrixProposal.status == "pending",
        )
        .order_by(MatrixProposal.created_at)
    )
    proposals = list(proposals_q.scalars().all())

    insights_q = await session.execute(
        select(MatrixInsight)
        .where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id == engagement_id,
            MatrixInsight.status == "open",
        )
        .order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc())
    )
    insights = list(insights_q.scalars().all())

    activity_q = await session.execute(
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
        )
        .order_by(CanonicalMemoryEvent.occurred_at.desc())
        .limit(_AGGREGATE_RECENT_ACTIVITY_LIMIT)
    )
    activity = list(activity_q.scalars().all())

    custom_types = await list_tenant_node_types(session, tenant_id)

    return EngagementDetailRead(
        engagement=EngagementRead.model_validate(eng),
        members=[EngagementMemberRead.model_validate(m) for m in members],
        matrix_nodes=[MatrixNodeRead.model_validate(n) for n in nodes],
        matrix_edges=[MatrixEdgeRead.model_validate(e) for e in edges],
        matrix_proposals=[MatrixProposalRead.model_validate(p) for p in proposals],
        custom_node_types=[CustomNodeTypeAggregate.model_validate(c) for c in custom_types],
        insights=[MatrixInsightRead.model_validate(i) for i in insights],
        recent_activity_events=[RecentActivityEventRead.model_validate(a) for a in activity],
    )


# --- Phase F3.b — matrix snapshot read endpoint ------------------------------
#
# Returns the nearest-prior matrix_snapshots row for the requested UTC date.
# Powers the F3.c web time slider. See docs/design/timeline-ledger.md §11.

_AT_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class MatrixSnapshotRead(BaseModel):
    captured_at: datetime
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


def _parse_at_date(raw: str) -> date:
    # Strict YYYY-MM-DD only — reject ISO datetimes and slash-separated forms.
    if not _AT_DATE_PATTERN.fullmatch(raw):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="at must be YYYY-MM-DD",
        )
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="at must be YYYY-MM-DD",
        ) from e


@router.get(
    "/{engagement_id}/matrix-snapshot",
    response_model=MatrixSnapshotRead,
    dependencies=[Depends(require_internal)],
)
async def get_matrix_snapshot(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    at: Annotated[str, Query()],
) -> MatrixSnapshotRead:
    target_day = _parse_at_date(at)
    # Window upper bound is end-of-day UTC so a snapshot captured later on the
    # requested day still matches.
    upper = datetime.combine(target_day, datetime.max.time(), tzinfo=UTC)
    r = await session.execute(
        select(MatrixSnapshot)
        .where(
            MatrixSnapshot.tenant_id == tenant_id,
            MatrixSnapshot.engagement_id == engagement_id,
            MatrixSnapshot.captured_at <= upper,
        )
        .order_by(MatrixSnapshot.captured_at.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no snapshot at or before requested date")
    return MatrixSnapshotRead(captured_at=row.captured_at, nodes=row.nodes, edges=row.edges)


# --- Phase G4.b — temporal insight quick-actions (snooze + followup) ---


class TemporalInsightSnoozeBody(BaseModel):
    days: int = Field(ge=1, le=90)


class TemporalInsightFollowupBody(BaseModel):
    owner_user_id: uuid.UUID
    due_date: date


class TemporalInsightSnoozeResponse(BaseModel):
    insight_id: uuid.UUID
    status: str
    snoozed_until: datetime


class TemporalInsightFollowupResponse(BaseModel):
    action_queue_item_id: str
    insight_id: uuid.UUID


async def _require_temporal_insight(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
) -> TemporalInsight:
    r = await session.execute(
        select(TemporalInsight).where(
            TemporalInsight.tenant_id == tenant_id,
            TemporalInsight.engagement_id == engagement_id,
            TemporalInsight.id == insight_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="insight not found")
    return row


@router.post(
    "/{engagement_id}/insights/{insight_id}/snooze",
    response_model=TemporalInsightSnoozeResponse,
    dependencies=[Depends(require_internal)],
)
async def snooze_temporal_insight(
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TemporalInsightSnoozeBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> TemporalInsightSnoozeResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    row = await _require_temporal_insight(session, tenant_id, engagement_id, insight_id)
    now = datetime.now(UTC)
    row.status = "snoozed"
    row.snoozed_until = now + timedelta(days=body.days)
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=now,
        actor_kind="user",
        actor_id=None,
        source_kind="insight_snoozed",
        source_ref=row.id,
        summary=f"insight snoozed {body.days}d: {row.title}"[:500],
        detail={
            "days": body.days,
            "snoozed_until": row.snoozed_until.isoformat(),
            "insight_kind": row.insight_kind,
        },
        affects=[("insight", row.id)],
    )
    await session.commit()
    await session.refresh(row)
    assert row.snoozed_until is not None
    return TemporalInsightSnoozeResponse(
        insight_id=row.id,
        status=row.status,
        snoozed_until=row.snoozed_until,
    )


@router.post(
    "/{engagement_id}/insights/{insight_id}/followup",
    response_model=TemporalInsightFollowupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_insight_followup(
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TemporalInsightFollowupBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> TemporalInsightFollowupResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    insight = await _require_temporal_insight(session, tenant_id, engagement_id, insight_id)
    now = datetime.now(UTC)
    item_id = f"fu-{uuid.uuid4()}"
    item = StrategistActionQueueItem(
        id=item_id,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        priority="normal",
        phase="followup",
        description=f"Follow up: {insight.title}"[:500],
        status="open",
        claimed_by=str(body.owner_user_id),
        updated_at=now,
        source=f"insight:{insight.id}",
        evidence_node_ids=[],
        resolution_reason=None,
        evidence_event_ids={
            "linked_insight_id": str(insight.id),
            "due_date": body.due_date.isoformat(),
            "owner_user_id": str(body.owner_user_id),
        },
    )
    session.add(item)
    await session.flush()
    evidence = list(insight.evidence_event_ids or [])
    caused_by = [evidence[0]] if evidence else []
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=now,
        actor_kind="user",
        actor_id=None,
        source_kind="followup_task_created",
        source_ref=insight.id,
        summary=f"followup task created: {insight.title}"[:500],
        detail={
            "action_queue_item_id": item_id,
            "owner_user_id": str(body.owner_user_id),
            "due_date": body.due_date.isoformat(),
            "insight_kind": insight.insight_kind,
        },
        caused_by=caused_by,
        affects=[("insight", insight.id)],
    )
    await session.commit()
    return TemporalInsightFollowupResponse(
        action_queue_item_id=item_id,
        insight_id=insight.id,
    )
