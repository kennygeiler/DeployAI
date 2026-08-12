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

Deletion order (everything scoped to the Acme engagement id, never the
whole tenant):

1. LangGraph checkpoints for the engagement's chat threads (thread_id
   prefix match — no FK, would otherwise leak stale agent state into the
   recreated engagement).
2. ``oracle_conversations`` (chat turns cascade via conversation FK).
3. ``ledger_events`` (causes/affects cascade off the event FK; the
   engagement FK is RESTRICT so these must go before the engagement row).
4. ``temporal_insights`` (RESTRICT FK, same reason).
5. The engagement row — matrix nodes/edges/proposals/insights, snapshots,
   review items, members, lint flags, audit traces, and strategist queues
   all cascade off it. Must precede the events: ``matrix_proposals`` FKs
   ``source_event_id`` → ``canonical_memory_events`` without cascade.
6. ``canonical_memory_events`` (append-only trigger disabled and re-enabled
   inside the same transaction).

Tables like ``solidified_learnings`` / ``identity_nodes`` / ``tombstones``
also carry an ``engagement_id`` column without an FK; they are included in
the wipe for completeness even though the demo flow never writes them.
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

router = APIRouter(prefix="/admin/demo", tags=["internal-demo-reset"])

ACME_ENGAGEMENT_NAME = "Acme Robotics — Pilot Deployment"
ACME_CUSTOMER_ACCOUNT = "Acme Robotics, Inc."
# Stable id so demo bookmarks / tour deep-links survive a reset.
ACME_ENGAGEMENT_ID = uuid.UUID("acacacac-acac-4aca-8aca-acacacacacac")
ACME_PHASE = "P2_discovery"

# Engagement-scoped rows that do NOT cascade from the engagement row.
# (table, engagement-id column) — all deletes also pin tenant_id.
_MANUAL_DELETE_TABLES: tuple[tuple[str, str], ...] = (
    ("oracle_conversations", "engagement_id"),  # chat turns cascade off this
    ("ledger_events", "engagement_id"),  # causes/affects cascade off this
    ("temporal_insights", "engagement_id"),
    ("solidified_learnings", "engagement_id"),
    ("learning_lifecycle_states", "engagement_id"),
    ("identity_attribute_history", "engagement_id"),
    ("identity_supersessions", "engagement_id"),
    ("identity_nodes", "engagement_id"),
    ("tombstones", "engagement_id"),
)


class DemoResetResponse(BaseModel):
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    engagement_name: str
    deleted_engagements: int
    deleted_events: int
    deleted_ledger_events: int


async def _delete_engagement_scoped_rows(
    session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID
) -> dict[str, int]:
    """Delete every row scoped to one engagement, in FK-safe order."""
    counts: dict[str, int] = {}
    params = {"tid": str(tenant_id), "eid": str(engagement_id)}

    # LangGraph checkpoints — keyed by composite thread_id, no FK.
    thread_prefix = f"tenant:{tenant_id}:engagement:{engagement_id}:%"
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        r = await session.execute(
            text(f"DELETE FROM {table} WHERE thread_id LIKE :prefix"),
            {"prefix": thread_prefix},
        )
        counts[table] = int(getattr(r, "rowcount", 0) or 0)

    for table, col in _MANUAL_DELETE_TABLES:
        r = await session.execute(
            text(f"DELETE FROM {table} WHERE tenant_id = CAST(:tid AS uuid) AND {col} = CAST(:eid AS uuid)"),
            params,
        )
        counts[table] = int(getattr(r, "rowcount", 0) or 0)

    # The engagement row — matrix_*, snapshots, review_items, members,
    # lint_flags, agent_audit_traces, strategist queues cascade off it. This
    # must happen BEFORE the canonical events go: matrix_proposals FKs
    # source_event_id → canonical_memory_events without cascade.
    r = await session.execute(
        text("DELETE FROM engagements WHERE tenant_id = CAST(:tid AS uuid) AND id = CAST(:eid AS uuid)"),
        params,
    )
    counts["engagements"] = int(getattr(r, "rowcount", 0) or 0)

    # canonical_memory_events last — nothing references the events once the
    # engagement cascade has cleared proposals/nodes. The table is
    # append-only by trigger; the demo reset is the one sanctioned eraser.
    # Disable + re-enable inside this transaction (transactional DDL) so the
    # invariant holds for everyone else at every point in time.
    await session.execute(
        text("ALTER TABLE canonical_memory_events DISABLE TRIGGER canonical_memory_events_append_only")
    )
    r = await session.execute(
        text(
            "DELETE FROM canonical_memory_events "
            "WHERE tenant_id = CAST(:tid AS uuid) AND engagement_id = CAST(:eid AS uuid)"
        ),
        params,
    )
    counts["canonical_memory_events"] = int(getattr(r, "rowcount", 0) or 0)
    await session.execute(
        text("ALTER TABLE canonical_memory_events ENABLE TRIGGER canonical_memory_events_append_only")
    )
    return counts


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
    rows = await session.execute(
        text(
            "SELECT id FROM engagements "
            "WHERE tenant_id = CAST(:tid AS uuid) AND (id = CAST(:eid AS uuid) OR name = :name)"
        ),
        {"tid": str(tenant_id), "eid": str(ACME_ENGAGEMENT_ID), "name": ACME_ENGAGEMENT_NAME},
    )
    existing_ids = [row[0] for row in rows]

    deleted_events = 0
    deleted_ledger = 0
    deleted_engagements = 0
    for eid in existing_ids:
        counts = await _delete_engagement_scoped_rows(session, tenant_id, eid)
        deleted_events += counts["canonical_memory_events"]
        deleted_ledger += counts["ledger_events"]
        deleted_engagements += counts["engagements"]

    await session.execute(
        text(
            "INSERT INTO engagements "
            "  (id, tenant_id, name, customer_account, current_phase, status, created_at, updated_at) "
            "VALUES "
            "  (CAST(:eid AS uuid), CAST(:tid AS uuid), :name, :customer, :phase, 'active', now(), now())"
        ),
        {
            "eid": str(ACME_ENGAGEMENT_ID),
            "tid": str(tenant_id),
            "name": ACME_ENGAGEMENT_NAME,
            "customer": ACME_CUSTOMER_ACCOUNT,
            "phase": ACME_PHASE,
        },
    )
    await session.commit()

    return DemoResetResponse(
        tenant_id=tenant_id,
        engagement_id=ACME_ENGAGEMENT_ID,
        engagement_name=ACME_ENGAGEMENT_NAME,
        deleted_engagements=deleted_engagements,
        deleted_events=deleted_events,
        deleted_ledger_events=deleted_ledger,
    )
