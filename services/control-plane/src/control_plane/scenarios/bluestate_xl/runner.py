"""Async runner that applies the BlueState-XL scenario to a CP session.

The integration test override (``days``) trims the 1825-day snapshot
backfill so CI doesn't sit on it for minutes. Production callers leave the
default in place.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.scenarios.bluestate_xl.builder import (
    CUSTOMER_ACCOUNT,
    ENGAGEMENT_ID,
    ENGAGEMENT_NAME,
    ENGAGEMENT_PHASE,
    TENANT_ID,
    TENANT_NAME,
    USER_BIZDEV_ID,
    USER_FDE_ID,
    USER_STRATEGIST_ID,
    XlTimeAnchor,
    build_xl_scenario_sql,
)
from control_plane.snapshots.cron import backfill_snapshots

DEFAULT_SNAPSHOT_DAYS = 1825  # 5 years


class XlScenarioSummary(BaseModel):
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    stakeholder_node_count: int
    decision_node_count: int
    risk_count: int
    narrative_event_count: int
    ledger_event_count: int
    matrix_edge_count: int
    snapshot_count: int


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


async def apply_bluestate_xl_scenario(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    base_now: datetime | None = None,
    skip_snapshots: bool = False,
    skip_analyzers: bool = False,
    days: int = DEFAULT_SNAPSHOT_DAYS,
) -> XlScenarioSummary:
    """Apply the BlueState-XL 5-year scenario via a single async session.

    ``days`` is the snapshot-backfill horizon; tests pass a smaller value
    (e.g. 365) so CI doesn't backfill 1825 daily rows. ``skip_analyzers`` is
    accepted for API symmetry with the small fixture but the XL scenario
    runs no analyzers in-band — the targeted analyzer anchors don't
    translate to a 260-week timeline and would only add latency.
    """
    effective_tenant = tenant_id or uuid.UUID(TENANT_ID)
    effective_tenant_str = str(effective_tenant)
    is_default_tenant = effective_tenant_str == TENANT_ID

    tenant_name = TENANT_NAME if is_default_tenant else f"bluestate-xl-test-{effective_tenant}"
    await _seed_tenant_and_users(session, tenant_id=effective_tenant_str, tenant_name=tenant_name)
    await _seed_engagement(session, tenant_id=effective_tenant_str)
    await _seed_members(session, tenant_id=effective_tenant_str)

    anchor = XlTimeAnchor(base_now=base_now or datetime.now(UTC))
    sql, _registry = build_xl_scenario_sql(anchor)
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    if not is_default_tenant:
        sql = sql.replace(TENANT_ID, effective_tenant_str)

    await session.flush()
    sync_conn = await session.connection()
    raw = await sync_conn.get_raw_connection()
    driver_conn = raw.driver_connection
    if driver_conn is None:
        raise RuntimeError("expected asyncpg driver connection for multi-statement seed")
    await driver_conn.execute(sql)
    await session.flush()

    snapshot_count = 0
    if not skip_snapshots and days > 0:
        snapshot_count = await backfill_snapshots(
            session,
            tenant_id=effective_tenant,
            engagement_id=uuid.UUID(ENGAGEMENT_ID),
            days=days,
            rebuild=True,
        )
        await session.flush()

    _ = skip_analyzers  # acknowledged but unused; see docstring

    stakeholder_node_count = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'stakeholder'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    decision_node_count = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'decision'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    risk_count = await _count(
        session,
        "SELECT count(*) FROM matrix_insights WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND insight_type = 'risk'",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    narrative_event_count = await _count(
        session,
        "SELECT count(*) FROM ledger_events WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND source_kind IN ('email_ingest', 'meeting_webhook', 'manual_capture')",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    ledger_event_count = await _count(
        session,
        "SELECT count(*) FROM ledger_events WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid)",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )
    matrix_edge_count = await _count(
        session,
        "SELECT count(*) FROM matrix_edges WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)",
        {"eid": ENGAGEMENT_ID, "tid": effective_tenant_str},
    )

    return XlScenarioSummary(
        tenant_id=effective_tenant,
        engagement_id=uuid.UUID(ENGAGEMENT_ID),
        stakeholder_node_count=stakeholder_node_count,
        decision_node_count=decision_node_count,
        risk_count=risk_count,
        narrative_event_count=narrative_event_count,
        ledger_event_count=ledger_event_count,
        matrix_edge_count=matrix_edge_count,
        snapshot_count=snapshot_count,
    )


async def xl_engagement_exists_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    return await _engagement_exists(session, tenant_id)


__all__ = [
    "DEFAULT_SNAPSHOT_DAYS",
    "XlScenarioSummary",
    "apply_bluestate_xl_scenario",
    "xl_engagement_exists_for_tenant",
]
