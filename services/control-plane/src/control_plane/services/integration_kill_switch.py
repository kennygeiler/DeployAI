"""Disable integration: revoke token / queue / secrets (stub) + audit (Epic 2 Story 2-6)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.integrations.models import Integration
from control_plane.services.strategist_activity import append_strategist_activity

logger = logging.getLogger(__name__)


def _revoke_oauth_stub(tenant_id: uuid.UUID, integration_id: uuid.UUID, provider: str) -> None:
    """TODO(Epic 3): revoke refresh token with Microsoft Graph + Google …"""
    logger.info(
        "integration.killswitch_oauth_revoke_stub",
        extra={"tenant_id": str(tenant_id), "integration_id": str(integration_id), "provider": provider},
    )


def _purge_queue_stub(tenant_id: uuid.UUID, integration_id: uuid.UUID) -> None:
    """TODO(Epic 3): purge SQS / in-flight for this integration when queues exist."""
    logger.info(
        "integration.killswitch_queue_purge_stub",
        extra={"tenant_id": str(tenant_id), "integration_id": str(integration_id)},
    )


def _delete_secrets_stub(tenant_id: uuid.UUID, integration_id: uuid.UUID) -> None:
    """TODO: delete Secrets Manager material when integration creds are stored there."""
    logger.info(
        "integration.killswitch_secrets_stub",
        extra={"tenant_id": str(tenant_id), "integration_id": str(integration_id)},
    )


async def disable_integration(
    session: AsyncSession,
    integration_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    r = await session.execute(select(Integration).where(Integration.id == integration_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        return {"not_found": True}
    if row.state == "disabled":
        return {"ok": True, "already_disabled": True, "integration_id": row.id, "tenant_id": row.tenant_id}

    now = datetime.now(UTC)
    _revoke_oauth_stub(row.tenant_id, row.id, row.provider)
    _purge_queue_stub(row.tenant_id, row.id)
    _delete_secrets_stub(row.tenant_id, row.id)
    row.state = "disabled"
    row.disabled_at = now
    row.updated_at = now
    if actor_id is not None:
        await append_strategist_activity(
            session,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            category="integration_kill_switch",
            summary=f"Integration kill-switch: {row.provider}",
            detail={"integration_id": str(row.id), "provider": row.provider},
            ref_id=row.id,
        )
    await session.commit()
    await session.refresh(row)

    logger.info(
        "integration.killswitch_triggered",
        extra={
            "event": "integration.killswitch_triggered",
            "tenant_id": str(row.tenant_id),
            "integration_id": str(row.id),
            "provider": row.provider,
        },
    )
    return {"ok": True, "already_disabled": False, "integration_id": row.id, "tenant_id": row.tenant_id}
