"""Persist ingestion run rows (Epic 3 Story 3-8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ingest_runs import IngestionRun


async def start_ingestion_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    integration: str,
    meta: dict[str, Any] | None = None,
) -> uuid.UUID:
    r = IngestionRun(
        tenant_id=tenant_id,
        integration=integration,
        status="running",
        meta=meta or {},
    )
    session.add(r)
    await session.flush()
    return r.id


async def complete_ingestion_run_success(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    events_written: int,
    meta: dict[str, Any] | None = None,
) -> None:
    r = await session.get(IngestionRun, run_id)
    if r is None:
        return
    r.status = "succeeded"
    r.completed_at = datetime.now(UTC)
    r.events_written = int(events_written)
    if meta:
        r.meta = {**(r.meta or {}), **meta}
    await session.flush()


async def complete_ingestion_run_failure(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    r = await session.get(IngestionRun, run_id)
    if r is None:
        return
    r.status = "failed"
    r.completed_at = datetime.now(UTC)
    r.error_count = 1
    r.error_summary = {"message": message[:2000]}
    if meta:
        r.meta = {**(r.meta or {}), **meta}
    await session.flush()
