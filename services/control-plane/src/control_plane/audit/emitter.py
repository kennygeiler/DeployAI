"""Single entry point for writing rows to ``strategist_activity_events``."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.strategist_personal import StrategistActivityEvent

_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_.]{0,79}$")
_SUMMARY_MIN = 1
_SUMMARY_MAX = 500


async def emit_audit_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    category: str,
    summary: str,
    detail: dict[str, Any],
    ref_id: uuid.UUID | None = None,
) -> StrategistActivityEvent:
    if not _CATEGORY_RE.fullmatch(category):
        raise ValueError("category must match ^[a-z][a-z0-9_.]{0,79}$ (got: " + repr(category) + ")")
    if not isinstance(summary, str) or not (_SUMMARY_MIN <= len(summary) <= _SUMMARY_MAX):
        raise ValueError(f"summary length must be between {_SUMMARY_MIN} and {_SUMMARY_MAX} characters")
    if not isinstance(detail, dict):
        raise ValueError("detail must be a dict")

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
    return row
