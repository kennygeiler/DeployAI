"""Daily-snapshot writer — one row per active engagement, idempotent per UTC day."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.engagement import Engagement
from control_plane.domain.matrix_snapshot import MatrixSnapshot
from control_plane.snapshots.builder import build_matrix_snapshot


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999_999)
    return start, end


async def _has_snapshot_today(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    now: datetime,
) -> bool:
    start, end = _utc_day_bounds(now)
    existing = await session.execute(
        select(func.count(MatrixSnapshot.id)).where(
            MatrixSnapshot.tenant_id == tenant_id,
            MatrixSnapshot.engagement_id == engagement_id,
            MatrixSnapshot.captured_at >= start,
            MatrixSnapshot.captured_at <= end,
        )
    )
    return (existing.scalar_one() or 0) > 0


async def write_daily_snapshots(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Write one snapshot per active engagement in ``tenant_id``; return count written.

    Idempotent within a UTC day — engagements that already have a snapshot dated
    today are skipped. Strictly tenant-scoped: never touches another tenant's rows.
    ``captured_at`` is normalized to UTC midnight so daily anchors line up with
    backfill output and the time-machine endpoint sees evenly spaced timestamps.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    captured_at = moment.replace(hour=0, minute=0, second=0, microsecond=0)

    engagements = (
        (
            await session.execute(
                select(Engagement.id).where(
                    Engagement.tenant_id == tenant_id,
                    Engagement.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )

    written = 0
    for engagement_id in engagements:
        if await _has_snapshot_today(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=captured_at,
        ):
            continue
        nodes, edges = await build_matrix_snapshot(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
        )
        session.add(
            MatrixSnapshot(
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                captured_at=captured_at,
                nodes=nodes,
                edges=edges,
                node_count=len(nodes),
                edge_count=len(edges),
            )
        )
        written += 1
    await session.flush()
    return written


async def backfill_snapshots(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    days: int,
    now: datetime | None = None,
) -> int:
    """Create one snapshot per missing UTC day going back ``days`` from ``now``.

    Same-day idempotency applies per backfilled day; rows are only inserted when
    no existing row falls inside that UTC day window. Snapshot ``captured_at`` is
    the UTC midnight of the target day so the time-machine endpoint sees evenly
    spaced anchors.
    """
    if days <= 0:
        return 0
    anchor = (now or datetime.now(UTC)).astimezone(UTC)
    midnight = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    written = 0
    for offset in range(days):
        day_anchor = midnight - timedelta(days=offset)
        if await _has_snapshot_today(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=day_anchor,
        ):
            continue
        nodes, edges = await build_matrix_snapshot(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
        )
        session.add(
            MatrixSnapshot(
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                captured_at=day_anchor,
                nodes=nodes,
                edges=edges,
                node_count=len(nodes),
                edge_count=len(edges),
            )
        )
        written += 1
    await session.flush()
    return written


__all__ = ["backfill_snapshots", "write_daily_snapshots"]
