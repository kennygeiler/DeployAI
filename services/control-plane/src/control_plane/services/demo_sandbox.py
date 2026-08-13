"""Demo engagement lifecycle shared by the reset endpoint and guest sandboxes.

Two callers, one implementation:

- ``POST /internal/v1/admin/demo/reset-acme`` (presenter flow) wipes and
  recreates the stable fixture engagement.
- ``POST /internal/v1/demo/session`` (guest flow) mints one fresh sandbox
  engagement per visitor and opportunistically reaps expired ones.

Sandbox engagements carry ``engagements.demo_sandbox_at`` (mint time); the
seeded fixtures and real engagements keep it NULL. All sandboxes share the
fixture's display name — visitors never see each other's engagements (the
list filter hides foreign sandboxes), so a visible name suffix would only
leak plumbing.

The deletion helper here is the ONE sanctioned engagement eraser: two FK
edges (``ledger_events`` / ``temporal_insights``) are plain RESTRICT and
``canonical_memory_events`` is append-only by trigger, so the wipe must run
server-side, in FK-safe order, with the CP's own DB credentials. See the
module docstring of ``api/routes/demo_reset_internal.py`` for the full
ordering rationale.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ACME_ENGAGEMENT_NAME = "Acme Robotics — Pilot Deployment"
ACME_CUSTOMER_ACCOUNT = "Acme Robotics, Inc."
# Stable id so demo bookmarks / tour deep-links survive a reset.
ACME_ENGAGEMENT_ID = uuid.UUID("acacacac-acac-4aca-8aca-acacacacacac")
ACME_PHASE = "P2_discovery"

# Sandboxes older than this are deleted opportunistically on each demo mint.
# Comfortably beyond the 3600s max session TTL — an expired guest who returns
# simply gets a new sandbox.
SANDBOX_MAX_AGE_HOURS = 24

# Bounded work per mint: the reaper never deletes more than this many
# sandboxes in one pass, so a mint stays fast even after a traffic spike.
# Leftovers are picked up by subsequent mints.
SANDBOX_REAP_LIMIT = 20

# Engagement-scoped rows deleted explicitly before the engagement row.
# (table, engagement-id column) — all deletes also pin tenant_id.
#
# Most entries do NOT cascade from the engagement row (RESTRICT or no FK).
# The Wave 5 tables at the tail (gap_ask_dismissals,
# engagement_intake_addresses, slack_channel_mappings) DO carry
# ``ondelete=CASCADE`` engagement FKs and would go with the engagement —
# they are wiped explicitly anyway so this list stays the one authoritative
# inventory of engagement-scoped state and the wipe does not silently
# depend on each new table's FK choice. (slack_staging_messages /
# slack_pending_channels are tenant+channel-scoped with no engagement
# column, so they are out of scope for an engagement wipe.)
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
    # Wave 5 (GA1 / IN1 / SL1) — CASCADE FKs, wiped explicitly (see above).
    ("gap_ask_dismissals", "engagement_id"),
    ("engagement_intake_addresses", "engagement_id"),
    ("slack_channel_mappings", "engagement_id"),
)


async def delete_engagement_scoped_rows(
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
    # append-only by trigger; the demo wipe is the one sanctioned eraser.
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


async def create_demo_engagement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    engagement_id: uuid.UUID | None = None,
    sandbox: bool,
) -> uuid.UUID:
    """Insert one empty demo engagement; returns its id.

    ``sandbox=True`` stamps ``demo_sandbox_at = now()`` (per-guest sandbox);
    ``sandbox=False`` keeps it NULL (the stable presenter fixture). Does not
    commit — the caller owns the transaction.
    """
    eid = engagement_id if engagement_id is not None else uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO engagements "
            "  (id, tenant_id, name, customer_account, current_phase, status, demo_sandbox_at, "
            "   created_at, updated_at) "
            "VALUES "
            "  (CAST(:eid AS uuid), CAST(:tid AS uuid), :name, :customer, :phase, 'active', "
            "   CASE WHEN :sandbox THEN now() END, now(), now())"
        ),
        {
            "eid": str(eid),
            "tid": str(tenant_id),
            "name": ACME_ENGAGEMENT_NAME,
            "customer": ACME_CUSTOMER_ACCOUNT,
            "phase": ACME_PHASE,
            "sandbox": sandbox,
        },
    )
    return eid


async def reap_expired_sandboxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    max_age_hours: int = SANDBOX_MAX_AGE_HOURS,
    limit: int = SANDBOX_REAP_LIMIT,
) -> list[uuid.UUID]:
    """Delete up to ``limit`` sandbox engagements older than ``max_age_hours``.

    Only rows with ``demo_sandbox_at`` set are candidates — the seeded
    fixtures (NULL) can never be reaped, whatever their age. Oldest first, so
    repeated mints drain a backlog in mint order. Does not commit.
    """
    rows = await session.execute(
        text(
            "SELECT id FROM engagements "
            "WHERE tenant_id = CAST(:tid AS uuid) "
            "  AND demo_sandbox_at IS NOT NULL "
            "  AND demo_sandbox_at < now() - make_interval(hours => :hours) "
            "ORDER BY demo_sandbox_at ASC "
            "LIMIT :lim"
        ),
        {"tid": str(tenant_id), "hours": max_age_hours, "lim": limit},
    )
    expired: list[uuid.UUID] = [row[0] for row in rows]
    for eid in expired:
        await delete_engagement_scoped_rows(session, tenant_id, eid)
    return expired


async def provision_sandbox_engagement(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """One demo mint's DB work: reap expired sandboxes, create a fresh one.

    Commits — the caller (the mint route) treats this as a single unit.
    """
    await reap_expired_sandboxes(session, tenant_id)
    eid = await create_demo_engagement(session, tenant_id, sandbox=True)
    await session.commit()
    return eid
