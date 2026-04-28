"""Append-only strategist activity log for personal audit (Epic 10.7)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.strategist_personal import StrategistActivityEvent


async def append_strategist_activity(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    category: str,
    summary: str,
    detail: dict[str, Any],
    ref_id: uuid.UUID | None = None,
) -> uuid.UUID:
    row = StrategistActivityEvent(
        tenant_id=tenant_id,
        actor_id=actor_id,
        category=category,
        summary=summary,
        detail=detail,
        ref_id=ref_id,
    )
    session.add(row)
    await session.flush()
    return row.id
