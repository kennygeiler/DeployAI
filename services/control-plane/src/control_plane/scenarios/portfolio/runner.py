"""Async runner that applies the DeployAI Portfolio scenario.

Iterates the 5 engagement configs under one tenant and emits one
``ScenarioSummary`` per engagement. Returns aggregate ``PortfolioSummary``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.scenarios.bluestate.runner import ScenarioSummary
from control_plane.scenarios.portfolio.engagements import (
    PORTFOLIO_ENGAGEMENTS,
    PORTFOLIO_TENANT_ID,
    EngagementConfig,
)
from control_plane.scenarios.portfolio.templates import (
    TimeAnchor,
    build_engagement_sql,
)
from control_plane.snapshots.cron import backfill_snapshots

_INSERT_TENANT = "INSERT INTO app_tenants (id, name) VALUES (CAST(:tid AS uuid), :name) ON CONFLICT (id) DO NOTHING"

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

_ENGAGEMENT_EXISTS = "SELECT id FROM engagements WHERE id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)"


class PortfolioSummary(BaseModel):
    tenant_id: uuid.UUID
    engagement_count: int
    engagements: list[ScenarioSummary]


async def _seed_tenant(session: AsyncSession, *, tenant_id: str, tenant_name: str) -> None:
    await session.execute(text(_INSERT_TENANT), {"tid": tenant_id, "name": tenant_name})


async def _seed_engagement(session: AsyncSession, *, tenant_id: str, config: EngagementConfig) -> None:
    await session.execute(
        text(_INSERT_ENGAGEMENT),
        {
            "eid": config.engagement_id,
            "tid": tenant_id,
            "name": config.name,
            "customer": config.customer_account,
            "phase": config.phase,
        },
    )


async def _engagement_exists(session: AsyncSession, *, tenant_id: str, engagement_id: str) -> bool:
    row = await session.execute(
        text(_ENGAGEMENT_EXISTS),
        {"eid": engagement_id, "tid": tenant_id},
    )
    return row.first() is not None


async def portfolio_engagements_exist_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """True if ANY of the 5 portfolio engagements already exist for tenant."""
    tid = str(tenant_id)
    for config in PORTFOLIO_ENGAGEMENTS:
        if await _engagement_exists(session, tenant_id=tid, engagement_id=config.engagement_id):
            return True
    return False


async def _count(session: AsyncSession, sql: str, params: dict[str, str]) -> int:
    row = await session.execute(text(sql), params)
    n = row.scalar()
    return int(n or 0)


async def _summarize(
    session: AsyncSession, *, tenant_id: str, config: EngagementConfig, snapshot_count: int
) -> ScenarioSummary:
    stakeholder_nodes = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'stakeholder'",
        {"eid": config.engagement_id, "tid": tenant_id},
    )
    decision_nodes = await _count(
        session,
        "SELECT count(*) FROM matrix_nodes WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND node_type = 'decision'",
        {"eid": config.engagement_id, "tid": tenant_id},
    )
    risks = await _count(
        session,
        "SELECT count(*) FROM matrix_insights WHERE engagement_id = CAST(:eid AS uuid) "
        "AND tenant_id = CAST(:tid AS uuid) AND insight_type = 'risk'",
        {"eid": config.engagement_id, "tid": tenant_id},
    )
    temporal_insight_count = await _count(
        session,
        "SELECT count(*) FROM temporal_insights "
        "WHERE engagement_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid)",
        {"eid": config.engagement_id, "tid": tenant_id},
    )
    return ScenarioSummary(
        tenant_id=uuid.UUID(tenant_id),
        engagement_id=uuid.UUID(config.engagement_id),
        stakeholder_nodes=stakeholder_nodes,
        decision_nodes=decision_nodes,
        risks=risks,
        snapshot_count=snapshot_count,
        temporal_insight_count=temporal_insight_count,
    )


async def apply_portfolio_scenario(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    base_now: datetime | None = None,
    skip_snapshots: bool = False,
    skip_analyzers: bool = False,
) -> PortfolioSummary:
    """Seed the 5-engagement portfolio under one tenant.

    ``skip_analyzers`` is accepted for parity with the BlueState runner;
    the portfolio fixture currently doesn't drive analyzers explicitly
    because its purpose is cross-engagement isolation rather than
    analyzer coverage.
    """
    effective_tenant = tenant_id or uuid.UUID(PORTFOLIO_TENANT_ID)
    effective_tenant_str = str(effective_tenant)
    is_default_tenant = effective_tenant_str == PORTFOLIO_TENANT_ID
    tenant_name = "acme-county-pilot" if is_default_tenant else f"portfolio-test-{effective_tenant}"

    await _seed_tenant(session, tenant_id=effective_tenant_str, tenant_name=tenant_name)
    for config in PORTFOLIO_ENGAGEMENTS:
        await _seed_engagement(session, tenant_id=effective_tenant_str, config=config)

    anchor = TimeAnchor(base_now=base_now or datetime.now(UTC))

    sql_parts: list[str] = []
    for config in PORTFOLIO_ENGAGEMENTS:
        sql_parts.append(
            build_engagement_sql(
                config,
                tenant_id=effective_tenant_str,
                anchor=anchor,
            )
        )
    sql = "\n".join(sql_parts)

    await session.flush()
    sync_conn = await session.connection()
    raw = await sync_conn.get_raw_connection()
    driver_conn = raw.driver_connection
    if driver_conn is None:
        raise RuntimeError("expected asyncpg driver connection for multi-statement seed")
    await driver_conn.execute(sql)
    await session.flush()

    engagement_summaries: list[ScenarioSummary] = []
    for config in PORTFOLIO_ENGAGEMENTS:
        snapshot_count = 0
        if not skip_snapshots:
            snapshot_count = await backfill_snapshots(
                session,
                tenant_id=effective_tenant,
                engagement_id=uuid.UUID(config.engagement_id),
                days=30,
                rebuild=True,
            )
            await session.flush()
        summary = await _summarize(
            session,
            tenant_id=effective_tenant_str,
            config=config,
            snapshot_count=snapshot_count,
        )
        engagement_summaries.append(summary)

    # Analyzers intentionally skipped — see docstring.
    _ = skip_analyzers

    return PortfolioSummary(
        tenant_id=effective_tenant,
        engagement_count=len(engagement_summaries),
        engagements=engagement_summaries,
    )


__all__ = [
    "PortfolioSummary",
    "apply_portfolio_scenario",
    "portfolio_engagements_exist_for_tenant",
]
