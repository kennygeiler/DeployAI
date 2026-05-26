"""Async runner that applies the BlueState scenario to a CP session.

Same observable output as ``infra/compose/seed/seed_scenario_bluestate.py``
but driven from an in-process async session, suitable for invocation from
a CP route. The runner:

1. Upserts tenant + 3 deployment-team users + engagement + 3 members.
2. Executes the multi-statement scenario SQL (ledger + matrix nodes/edges
   + insights).
3. Backfills 182 daily matrix snapshots (unless ``skip_snapshots``).
4. Runs analyzers at six scenario-time anchors so each analyzer's window
   catches the right event cluster (unless ``skip_analyzers``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.intelligence.scheduler import run_analyzers
from control_plane.scenarios.bluestate.builder import (
    CUSTOMER_ACCOUNT,
    ENGAGEMENT_ID,
    ENGAGEMENT_NAME,
    ENGAGEMENT_PHASE,
    TENANT_ID,
    TENANT_NAME,
    USER_BIZDEV_ID,
    USER_FDE_ID,
    USER_STRATEGIST_ID,
    TimeAnchor,
    build_scenario_sql,
)
from control_plane.snapshots.cron import backfill_snapshots


class ScenarioSummary(BaseModel):
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    stakeholder_nodes: int
    decision_nodes: int
    risks: int
    snapshot_count: int
    temporal_insight_count: int


# SQLAlchemy `text()` interprets `:name::uuid` as a malformed bound param.
# Use `CAST(:name AS uuid)` so the param resolves before the type cast.
_INSERT_TENANT = "INSERT INTO app_tenants (id, name) VALUES (CAST(:tid AS uuid), :name) ON CONFLICT (id) DO NOTHING"

_INSERT_USERS = (
    "INSERT INTO app_users (id, tenant_id, user_name, email, given_name, family_name, active) "
    "VALUES "
    "(CAST(:sid AS uuid), CAST(:tid AS uuid), 'alex.chen', 'alex.chen@deployai.com', 'Alex', 'Chen', true), "
    "(CAST(:fid AS uuid), CAST(:tid AS uuid), 'jordan.park', 'jordan.park@deployai.com', 'Jordan', 'Park', true), "
    "(CAST(:bid AS uuid), CAST(:tid AS uuid), 'sam.lee', 'sam.lee@deployai.com', 'Sam', 'Lee', true) "
    "ON CONFLICT (id) DO NOTHING"
)

_INSERT_ENGAGEMENT = (
    "INSERT INTO engagements "
    "  (id, tenant_id, name, customer_account, current_phase, status, created_at, updated_at) "
    "VALUES "
    "  (CAST(:eid AS uuid), CAST(:tid AS uuid), :name, :customer, :phase, 'active', now(), now()) "
    "ON CONFLICT (id) DO UPDATE SET "
    "  name = EXCLUDED.name, "
    "  customer_account = EXCLUDED.customer_account, "
    "  current_phase = EXCLUDED.current_phase, "
    "  status = EXCLUDED.status, "
    "  updated_at = now()"
)

_INSERT_MEMBER = (
    "INSERT INTO engagement_members (id, tenant_id, engagement_id, user_id, role) "
    "VALUES (gen_random_uuid(), CAST(:tid AS uuid), CAST(:eid AS uuid), CAST(:uid AS uuid), :role) "
    "ON CONFLICT (engagement_id, user_id) DO NOTHING"
)

_ENGAGEMENT_EXISTS = "SELECT 1 FROM engagements WHERE id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"


async def _seed_tenant_and_users(session: AsyncSession, *, tenant_id: str, tenant_name: str) -> None:
    await session.execute(text(_INSERT_TENANT), {"tid": tenant_id, "name": tenant_name})
    await session.execute(
        text(_INSERT_USERS),
        {
            "tid": tenant_id,
            "sid": USER_STRATEGIST_ID,
            "fid": USER_FDE_ID,
            "bid": USER_BIZDEV_ID,
        },
    )


async def _seed_engagement(session: AsyncSession, *, tenant_id: str) -> None:
    await session.execute(
        text(_INSERT_ENGAGEMENT),
        {
            "eid": ENGAGEMENT_ID,
            "tid": tenant_id,
            "name": ENGAGEMENT_NAME,
            "customer": CUSTOMER_ACCOUNT,
            "phase": ENGAGEMENT_PHASE,
        },
    )


async def _seed_members(session: AsyncSession, *, tenant_id: str) -> None:
    for user_id, role in (
        (USER_STRATEGIST_ID, "deployment_strategist"),
        (USER_FDE_ID, "fde"),
        (USER_BIZDEV_ID, "biz_dev"),
    ):
        await session.execute(
            text(_INSERT_MEMBER),
            {"tid": tenant_id, "eid": ENGAGEMENT_ID, "uid": user_id, "role": role},
        )


async def _engagement_exists(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    row = await session.execute(
        text(_ENGAGEMENT_EXISTS),
        {"eid": ENGAGEMENT_ID, "tid": str(tenant_id)},
    )
    return row.first() is not None


async def _count(session: AsyncSession, sql: str, params: dict[str, str]) -> int:
    row = await session.execute(text(sql), params)
    n = row.scalar()
    return int(n or 0)


async def apply_bluestate_scenario(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    base_now: datetime | None = None,
    skip_snapshots: bool = False,
    skip_analyzers: bool = False,
) -> ScenarioSummary:
    """Apply the BlueState 26-week scenario via a single async session.

    ``tenant_id`` defaults to the shared seed-app tenant so the
    BlueState + Acme engagements live under one team. Pass an explicit
    UUID for test isolation.
    """
    effective_tenant = tenant_id or uuid.UUID(TENANT_ID)
    effective_tenant_str = str(effective_tenant)
    is_default_tenant = effective_tenant_str == TENANT_ID

    tenant_name = TENANT_NAME if is_default_tenant else f"bluestate-test-{effective_tenant}"
    await _seed_tenant_and_users(session, tenant_id=effective_tenant_str, tenant_name=tenant_name)
    await _seed_engagement(session, tenant_id=effective_tenant_str)
    await _seed_members(session, tenant_id=effective_tenant_str)

    anchor = TimeAnchor(base_now=base_now or datetime.now(UTC))
    sql, _registry = build_scenario_sql(anchor)
    # Builder emits BEGIN/COMMIT to wrap its block when run via psql. Inside an
    # async session that already manages a transaction these statements are
    # noise; strip them so we don't fight the existing transaction.
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    if not is_default_tenant:
        sql = sql.replace(TENANT_ID, effective_tenant_str)
    # SQLAlchemy + asyncpg refuses multi-statement blocks ("cannot insert
    # multiple commands into a prepared statement"). Drop down to the raw
    # asyncpg connection and run the block via its `execute` API, which DOES
    # support multi-statement DDL/DML when run as a simple query.
    await session.flush()
    sync_conn = await session.connection()
    raw = await sync_conn.get_raw_connection()
    driver_conn = raw.driver_connection
    if driver_conn is None:
        raise RuntimeError("expected asyncpg driver connection for multi-statement seed")
    await driver_conn.execute(sql)
    await session.flush()

    snapshot_count = 0
    if not skip_snapshots:
        snapshot_count = await backfill_snapshots(
            session,
            tenant_id=effective_tenant,
            engagement_id=uuid.UUID(ENGAGEMENT_ID),
            days=182,
            rebuild=True,
        )
        await session.flush()

    if not skip_analyzers:
        w14_end = anchor.at(14, 7, 23)
        w16_end_plus1 = anchor.at(16, 7, 23) + timedelta(days=1)
        w22_end_plus1 = anchor.at(22, 7, 23) + timedelta(days=1)
        w24_end_plus2 = anchor.at(24, 7, 23) + timedelta(days=2)
        go_create = anchor.at(26, 2, 15)
        go_accept_plus12 = go_create + timedelta(hours=72 + 12)
        for now_value in (
            w14_end,
            w16_end_plus1,
            w22_end_plus1,
            w24_end_plus2,
            go_accept_plus12,
            anchor.base_now,
        ):
            await run_analyzers(
                session,
                tenant_id=effective_tenant,
                engagement_id=uuid.UUID(ENGAGEMENT_ID),
                now=now_value,
            )
            await session.flush()

    stakeholder_nodes = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'stakeholder'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    decision_nodes = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'decision'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    risks = await _count(
        session,
        "SELECT count(*) FROM matrix_insights WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND insight_type = 'risk'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    temporal_insight_count = await _count(
        session,
        "SELECT count(*) FROM temporal_insights "
        "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )

    return ScenarioSummary(
        tenant_id=effective_tenant,
        engagement_id=uuid.UUID(ENGAGEMENT_ID),
        stakeholder_nodes=stakeholder_nodes,
        decision_nodes=decision_nodes,
        risks=risks,
        snapshot_count=snapshot_count,
        temporal_insight_count=temporal_insight_count,
    )


async def engagement_exists_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    return await _engagement_exists(session, tenant_id)


__all__ = [
    "ScenarioSummary",
    "apply_bluestate_scenario",
    "engagement_exists_for_tenant",
]
