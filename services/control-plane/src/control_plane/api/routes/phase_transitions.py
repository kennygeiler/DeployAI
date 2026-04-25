"""Internal phase transition API (Epic 5, Story 5.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.tenant_phase import PhaseTransitionProposal, TenantDeploymentPhase
from control_plane.phases.machine import can_transition, default_phase

router = APIRouter(prefix="/tenants", tags=["internal-phase"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class DeploymentPhaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: uuid.UUID
    phase: str
    updated_at: datetime


class ProposeBody(BaseModel):
    from_phase: str
    to_phase: str
    evidence_event_ids: list[uuid.UUID] = Field(default_factory=list)
    proposer_agent: str
    reason: str = ""


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    from_phase: str
    to_phase: str
    status: str
    proposer_agent: str
    reason: str
    created_at: datetime


@router.get(
    "/{tenant_id}/deployment-phase",
    response_model=DeploymentPhaseRead,
    dependencies=[Depends(require_internal)],
)
async def get_deployment_phase(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> TenantDeploymentPhase:
    row = await session.get(TenantDeploymentPhase, tenant_id)
    if row is None:
        row = TenantDeploymentPhase(tenant_id=tenant_id, phase=default_phase)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


@router.post(
    "/{tenant_id}/phase-transitions/propose",
    response_model=ProposalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def propose_phase_transition(
    tenant_id: uuid.UUID,
    body: ProposeBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> PhaseTransitionProposal:
    cur = await session.get(TenantDeploymentPhase, tenant_id)
    current = cur.phase if cur is not None else default_phase
    if body.from_phase != current:
        raise HTTPException(status_code=409, detail="from_phase does not match current phase")
    if not can_transition(body.from_phase, body.to_phase):
        raise HTTPException(status_code=400, detail="invalid phase transition")
    prop = PhaseTransitionProposal(
        tenant_id=tenant_id,
        from_phase=body.from_phase,
        to_phase=body.to_phase,
        status="pending",
        evidence_event_ids=[str(x) for x in body.evidence_event_ids],  # JSONB-friendly
        proposer_agent=body.proposer_agent,
        reason=body.reason,
    )
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return prop


@router.post(
    "/{tenant_id}/phase-transitions/{proposal_id}/confirm",
    response_model=DeploymentPhaseRead,
    dependencies=[Depends(require_internal)],
)
async def confirm_phase_transition(
    tenant_id: uuid.UUID,
    proposal_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    x_deployai_strategist_actor: Annotated[uuid.UUID, Header(alias="X-Deployai-Strategist-Actor-Id")],
) -> TenantDeploymentPhase:
    prop = await session.get(PhaseTransitionProposal, proposal_id)
    if prop is None or prop.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="proposal not found")
    if prop.status != "pending":
        raise HTTPException(status_code=409, detail="proposal is not pending")
    row = await session.get(TenantDeploymentPhase, prop.tenant_id)
    if row is None:
        row = TenantDeploymentPhase(tenant_id=prop.tenant_id, phase=default_phase)
        session.add(row)
    if row.phase != prop.from_phase:
        raise HTTPException(status_code=409, detail="current phase has changed")
    row.phase = prop.to_phase
    row.updated_at = datetime.now(tz=UTC)
    prop.status = "confirmed"
    prop.decided_at = datetime.now(tz=UTC)
    prop.decided_by_actor_id = x_deployai_strategist_actor
    await session.commit()
    await session.refresh(row)
    return row


@router.get(
    "/{tenant_id}/phase-transitions",
    response_model=list[ProposalRead],
    dependencies=[Depends(require_internal)],
)
async def list_proposals(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> list[PhaseTransitionProposal]:
    r = await session.execute(select(PhaseTransitionProposal).where(PhaseTransitionProposal.tenant_id == tenant_id))
    return list(r.scalars().all())
