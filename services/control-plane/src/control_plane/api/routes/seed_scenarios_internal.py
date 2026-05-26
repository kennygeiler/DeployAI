"""Internal API — pre-canned demo scenarios (Path B onboarding).

Lets the onboarding wizard load the BlueState 26-week scenario natively via
a single CP route, replacing the host-side ``make seed-scenario-bluestate``
shellout for the demo-loader path. The wizard's "Start fresh" flow still
uses the regular onboarding endpoints.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.scenarios.bluestate import (
    ENGAGEMENT_ID as BLUESTATE_ENGAGEMENT_ID,
)
from control_plane.scenarios.bluestate import (
    ScenarioSummary,
    apply_bluestate_scenario,
    engagement_exists_for_tenant,
)

router = APIRouter(prefix="/admin/seed-scenarios", tags=["internal-seed-scenarios"])


class SeedBluestateRequest(BaseModel):
    force: bool = False


class SeedBluestateResponse(BaseModel):
    engagement_id: uuid.UUID
    summary: ScenarioSummary
    took_seconds: float
    source: str = "cp"


class SeedBluestateConflict(BaseModel):
    error: str
    engagement_id: uuid.UUID


@router.post(
    "/bluestate",
    response_model=SeedBluestateResponse,
    dependencies=[Depends(require_internal)],
)
async def seed_bluestate(
    body: SeedBluestateRequest,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> SeedBluestateResponse:
    already = await engagement_exists_for_tenant(session, tenant_id)
    if already and not body.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "already_seeded",
                "engagement_id": BLUESTATE_ENGAGEMENT_ID,
            },
        )

    started = time.monotonic()
    summary = await apply_bluestate_scenario(session, tenant_id=tenant_id)
    await session.commit()
    elapsed = time.monotonic() - started

    return SeedBluestateResponse(
        engagement_id=summary.engagement_id,
        summary=summary,
        took_seconds=round(elapsed, 3),
    )
