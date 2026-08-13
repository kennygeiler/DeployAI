"""Internal API — cold-start demo reset (Wave 3 K1).

``POST /internal/v1/admin/demo/reset-acme`` deletes the "Acme Robotics —
Pilot Deployment" engagement (if present) and recreates it empty, so the
three-act demo (see docs/plans/2026-08-11-pilot-refresh-backlog.md Part 5,
"The demo thesis") always starts from a clean cold-start engagement.
Rerunnable between meetings — the route is idempotent.

Auth: ``require_tenant_scoped`` — same gate as the ingest/extract routes it
resets the output of. Accepts a tenant service token for the target tenant
or the legacy global internal key (which is what ``make demo-reset`` sends
from the host). Never exposed through the web BFF; the public internet
cannot reach it on a correctly deployed stack.

Why a dedicated endpoint instead of a client-side wipe: there is no
engagement-level DELETE anywhere in the API surface, and two FK edges
(``ledger_events.engagement_id``, ``temporal_insights.engagement_id``) are
plain RESTRICT — a bare ``DELETE FROM engagements`` fails once the demo has
produced ledger entries. ``canonical_memory_events`` additionally carries
the ``canonical_memory_events_append_only`` trigger, which only the table
owner can step around (``ALTER TABLE … DISABLE TRIGGER``), so the wipe has
to run server-side with the CP's own DB credentials.

The wipe/create implementation lives in
``control_plane/services/demo_sandbox.py`` (shared with the per-guest
sandbox mint in ``demo_session_internal.py``); its docstrings carry the
FK-ordering rationale.

Guest-sandbox interplay: per-visitor sandboxes share the fixture's display
name but are marked with ``engagements.demo_sandbox_at``. The reset's
match-by-name sweep deliberately skips marked rows — a presenter reset must
never yank a sandbox out from under a live guest. Sandboxes age out via the
mint-time reaper instead.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session

# Re-exported: tests and the tour docs reference these under this module's
# historical path.
from control_plane.services.demo_sandbox import (
    ACME_CUSTOMER_ACCOUNT,  # noqa: F401
    ACME_ENGAGEMENT_ID,
    ACME_ENGAGEMENT_NAME,
    ACME_PHASE,  # noqa: F401
    create_demo_engagement,
    delete_engagement_scoped_rows,
)

router = APIRouter(prefix="/admin/demo", tags=["internal-demo-reset"])


class DemoResetResponse(BaseModel):
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    engagement_name: str
    deleted_engagements: int
    deleted_events: int
    deleted_ledger_events: int


@router.post(
    "/reset-acme",
    response_model=DemoResetResponse,
    dependencies=[Depends(require_tenant_scoped)],
)
async def reset_acme_demo_engagement(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> DemoResetResponse:
    """Wipe + recreate the Acme demo engagement (idempotent)."""
    tenant_exists = await session.execute(
        text("SELECT 1 FROM app_tenants WHERE id = CAST(:tid AS uuid)"),
        {"tid": str(tenant_id)},
    )
    if tenant_exists.first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found — run the stack seed first (make dev / make init)",
        )

    # Match by stable id OR by name, so a hand-created engagement with the
    # demo name is also cleaned up rather than left as a confusing twin.
    # Per-guest sandboxes share the name but are excluded via their
    # demo_sandbox_at marker: a presenter reset must not kill live guest
    # sessions (the mint-time reaper retires sandboxes instead).
    rows = await session.execute(
        text(
            "SELECT id FROM engagements "
            "WHERE tenant_id = CAST(:tid AS uuid) "
            "  AND (id = CAST(:eid AS uuid) OR (name = :name AND demo_sandbox_at IS NULL))"
        ),
        {"tid": str(tenant_id), "eid": str(ACME_ENGAGEMENT_ID), "name": ACME_ENGAGEMENT_NAME},
    )
    existing_ids = [row[0] for row in rows]

    deleted_events = 0
    deleted_ledger = 0
    deleted_engagements = 0
    for eid in existing_ids:
        counts = await delete_engagement_scoped_rows(session, tenant_id, eid)
        deleted_events += counts["canonical_memory_events"]
        deleted_ledger += counts["ledger_events"]
        deleted_engagements += counts["engagements"]

    await create_demo_engagement(session, tenant_id, engagement_id=ACME_ENGAGEMENT_ID, sandbox=False)
    await session.commit()

    return DemoResetResponse(
        tenant_id=tenant_id,
        engagement_id=ACME_ENGAGEMENT_ID,
        engagement_name=ACME_ENGAGEMENT_NAME,
        deleted_engagements=deleted_engagements,
        deleted_events=deleted_events,
        deleted_ledger_events=deleted_ledger,
    )
