"""Break-glass session lifecycle (Epic 2 Story 2-7; customer notification in Epic 12)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.break_glass.models import BreakGlassSession
from control_plane.exceptions import NotFoundError

logger = logging.getLogger(__name__)

_BG_TTL = timedelta(hours=4)


async def _expire_active_past_due(session: AsyncSession) -> None:
    await session.execute(
        text(
            "UPDATE break_glass_sessions "
            "SET status = 'expired' "
            "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < now()"
        )
    )


async def create_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    initiator_sub: str,
    requested_scope: str,
) -> BreakGlassSession:
    await _expire_active_past_due(session)
    row = BreakGlassSession(
        tenant_id=tenant_id,
        initiator_sub=initiator_sub,
        status="requested",
        requested_scope=requested_scope,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info(
        "audit_events.break_glass.requested",
        extra={"tenant_id": str(tenant_id), "session_id": str(row.id), "initiator_sub": initiator_sub},
    )
    return row


async def approve(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    approver_sub: str,
) -> BreakGlassSession:
    await _expire_active_past_due(session)
    r = await session.execute(select(BreakGlassSession).where(BreakGlassSession.id == session_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        raise NotFoundError("break-glass session not found")
    if row.initiator_sub == approver_sub:
        raise ValueError("approver must be a different principal than the initiator")
    if row.status != "requested":
        raise ValueError("session is not in the requested state")
    now = datetime.now(UTC)
    row.approver_sub = approver_sub
    row.approved_at = now
    row.status = "active"
    row.expires_at = now + _BG_TTL
    await session.commit()
    await session.refresh(row)
    logger.info(
        "audit_events.break_glass.approved",
        extra={
            "tenant_id": str(row.tenant_id),
            "session_id": str(row.id),
            "initiator_sub": row.initiator_sub,
            "approver_sub": approver_sub,
        },
    )
    return row


async def revoke(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_sub: str,
    allow_if_platform: bool,
) -> None:
    r = await session.execute(select(BreakGlassSession).where(BreakGlassSession.id == session_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        raise NotFoundError("break-glass session not found")
    if not allow_if_platform:
        if actor_sub != row.initiator_sub and actor_sub != (row.approver_sub or ""):
            raise PermissionError("not allowed to revoke this session")
    if row.status in ("expired", "denied"):
        return
    now = datetime.now(UTC)
    if row.status == "requested":
        row.status = "denied"
    else:
        row.status = "expired"
        row.revoked_at = now
    await session.commit()
    logger.info(
        "audit_events.break_glass.revoked",
        extra={"session_id": str(row.id), "actor_sub": actor_sub, "final_status": row.status},
    )
