"""Break-glass session lifecycle (Epic 2 Story 2-7; customer notification in Epic 12)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from deployai_authz import AuthActor, can_access
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.audit import emit_audit_event
from control_plane.domain.break_glass.models import BreakGlassSession
from control_plane.exceptions import NotFoundError

logger = logging.getLogger(__name__)

_BG_TTL = timedelta(hours=4)


def _try_uuid(sub: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(sub)
    except ValueError:
        return None


def _require_break_glass_tenant(actor: AuthActor, tenant_id: uuid.UUID) -> None:
    d = can_access(
        actor,
        "break_glass:invoke",
        {"kind": "tenant", "id": str(tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise PermissionError(d.reason or "break_glass:invoke denied for this tenant")


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
    auth_actor: AuthActor,
) -> BreakGlassSession:
    _require_break_glass_tenant(auth_actor, tenant_id)
    await _expire_active_past_due(session)
    row = BreakGlassSession(
        tenant_id=tenant_id,
        initiator_sub=initiator_sub,
        status="requested",
        requested_scope=requested_scope,
    )
    session.add(row)
    await session.flush()
    actor_uuid = _try_uuid(initiator_sub)
    if actor_uuid is not None:
        await emit_audit_event(
            session,
            tenant_id=tenant_id,
            actor_id=actor_uuid,
            category="break_glass.requested",
            summary="break-glass session requested",
            detail={
                "session_id": str(row.id),
                "initiator_sub": initiator_sub,
                "requested_scope": requested_scope,
            },
            ref_id=row.id,
        )
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
    auth_actor: AuthActor,
) -> BreakGlassSession:
    await _expire_active_past_due(session)
    r = await session.execute(select(BreakGlassSession).where(BreakGlassSession.id == session_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        raise NotFoundError("break-glass session not found")
    _require_break_glass_tenant(auth_actor, row.tenant_id)
    if row.initiator_sub == approver_sub:
        raise ValueError("approver must be a different principal than the initiator")
    if row.status != "requested":
        raise ValueError("session is not in the requested state")
    now = datetime.now(UTC)
    row.approver_sub = approver_sub
    row.approved_at = now
    row.status = "active"
    row.expires_at = now + _BG_TTL
    actor_uuid = _try_uuid(approver_sub)
    if actor_uuid is not None:
        await emit_audit_event(
            session,
            tenant_id=row.tenant_id,
            actor_id=actor_uuid,
            category="break_glass.approved",
            summary="break-glass session approved",
            detail={
                "session_id": str(row.id),
                "initiator_sub": row.initiator_sub,
                "approver_sub": approver_sub,
            },
            ref_id=row.id,
        )
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
    auth_actor: AuthActor,
) -> None:
    r = await session.execute(select(BreakGlassSession).where(BreakGlassSession.id == session_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        raise NotFoundError("break-glass session not found")
    _require_break_glass_tenant(auth_actor, row.tenant_id)
    if row.status in ("expired", "denied"):
        return
    now = datetime.now(UTC)
    if row.status == "requested":
        row.status = "denied"
    else:
        row.status = "expired"
    row.revoked_at = now
    actor_uuid = _try_uuid(actor_sub)
    if actor_uuid is not None:
        await emit_audit_event(
            session,
            tenant_id=row.tenant_id,
            actor_id=actor_uuid,
            category="break_glass.revoked",
            summary="break-glass session revoked",
            detail={
                "session_id": str(row.id),
                "actor_sub": actor_sub,
                "final_status": row.status,
            },
            ref_id=row.id,
        )
    await session.commit()
    logger.info(
        "audit_events.break_glass.revoked",
        extra={"session_id": str(row.id), "actor_sub": actor_sub, "final_status": row.status},
    )
