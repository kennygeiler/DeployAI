"""Internal schema-proposal review API (Story 1-17)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.proposals import SchemaProposal
from control_plane.schemas.schema_proposals import RejectBody, SchemaProposalCreate, SchemaProposalRead
from control_plane.services.schema_proposal_scaffold import write_promotion_scaffold

router = APIRouter(prefix="/tenants", tags=["internal-schema-proposals"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


def _parse_reviewer(
    x_reviewer: str | None = Header(default=None, alias="X-Deployai-Reviewer-Actor-Id"),
) -> uuid.UUID:
    if not x_reviewer or not x_reviewer.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Deployai-Reviewer-Actor-Id header is required for this action",
        )
    try:
        return uuid.UUID(x_reviewer)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Deployai-Reviewer-Actor-Id must be a UUID",
        ) from e


def _orm_to_read(p: SchemaProposal) -> SchemaProposalRead:
    se = p.sample_evidence
    ev: dict[str, object] | None = se if isinstance(se, dict) else None
    return SchemaProposalRead(
        id=p.id,
        tenant_id=p.tenant_id,
        created_at=p.created_at,
        proposer_actor_id=p.proposer_actor_id,
        proposed_ddl=p.proposed_ddl,
        status=p.status,
        reviewed_at=p.reviewed_at,
        reviewer_actor_id=p.reviewer_actor_id,
        proposer_agent=p.proposer_agent,
        proposed_field_path=p.proposed_field_path,
        proposed_type=p.proposed_type,
        sample_evidence=ev,
        rejection_reason=p.rejection_reason,
    )


@router.get(
    "/{tenant_id}/schema-proposals",
    dependencies=[Depends(require_internal)],
    response_model=list[SchemaProposalRead],
)
async def list_schema_proposals(
    tenant_id: uuid.UUID,
    proposals_status: str = Query("pending", alias="status"),
) -> list[SchemaProposalRead]:
    """List proposals for a tenant, filtered by ``status`` (default: pending)."""
    sf = proposals_status
    async with tenant_session(tenant_id) as session:
        assert isinstance(session, AsyncSession)
        res = await session.execute(
            select(SchemaProposal).where(SchemaProposal.status == sf).order_by(SchemaProposal.created_at.desc()),
        )
        rows = res.scalars().all()
    return [_orm_to_read(p) for p in rows]


@router.post(
    "/{tenant_id}/schema-proposals",
    dependencies=[Depends(require_internal)],
    response_model=SchemaProposalRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_schema_proposal(
    tenant_id: uuid.UUID,
    body: SchemaProposalCreate,
) -> SchemaProposalRead:
    """Stage a new schema proposal (Cartographer stub, Epic 6)."""
    p = SchemaProposal(
        tenant_id=tenant_id,
        proposer_actor_id=body.proposer_actor_id,
        proposed_ddl=body.proposed_ddl,
        proposer_agent=body.proposer_agent,
        proposed_field_path=body.proposed_field_path,
        proposed_type=body.proposed_type,
        sample_evidence=body.sample_evidence,
    )
    async with tenant_session(tenant_id) as session:
        assert isinstance(session, AsyncSession)
        session.add(p)
        await session.flush()
        await session.refresh(p)
    return _orm_to_read(p)


@router.post(
    "/{tenant_id}/schema-proposals/{proposal_id}/promote",
    dependencies=[Depends(require_internal)],
    response_model=SchemaProposalRead,
)
async def promote_schema_proposal(
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
    reviewer: Annotated[uuid.UUID, Depends(_parse_reviewer)],
) -> SchemaProposalRead:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    async with tenant_session(tenant_id) as session:
        assert isinstance(session, AsyncSession)
        res = await session.execute(
            select(SchemaProposal).where(
                SchemaProposal.id == proposal_id,
                SchemaProposal.tenant_id == tenant_id,
            ),
        )
        row = res.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        if row.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"proposal is not pending (status={row.status!r})",
            )
        _ = write_promotion_scaffold(row)
        row.status = "promoted"
        row.reviewed_at = now
        row.reviewer_actor_id = reviewer
    async with tenant_session(tenant_id) as session2:
        assert isinstance(session2, AsyncSession)
        res2 = await session2.execute(
            select(SchemaProposal).where(SchemaProposal.id == proposal_id),
        )
        out = res2.scalar_one()
    return _orm_to_read(out)


@router.post(
    "/{tenant_id}/schema-proposals/{proposal_id}/reject",
    dependencies=[Depends(require_internal)],
    response_model=SchemaProposalRead,
)
async def reject_schema_proposal(
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: RejectBody,
    reviewer: Annotated[uuid.UUID, Depends(_parse_reviewer)],
) -> SchemaProposalRead:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    async with tenant_session(tenant_id) as session:
        assert isinstance(session, AsyncSession)
        res = await session.execute(
            select(SchemaProposal).where(
                SchemaProposal.id == proposal_id,
                SchemaProposal.tenant_id == tenant_id,
            ),
        )
        row = res.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
        if row.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"proposal is not pending (status={row.status!r})",
            )
        row.status = "rejected"
        row.reviewed_at = now
        row.reviewer_actor_id = reviewer
        row.rejection_reason = body.rejection_reason
    async with tenant_session(tenant_id) as session2:
        assert isinstance(session2, AsyncSession)
        res2 = await session2.execute(
            select(SchemaProposal).where(SchemaProposal.id == proposal_id),
        )
        out = res2.scalar_one()
    return _orm_to_read(out)
