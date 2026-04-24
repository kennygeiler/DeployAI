"""Session revocation; Redis refresh keys (Story 2-4; SCIM/SSO call sites)."""

from __future__ import annotations

import logging
import uuid

from control_plane.auth.session_service import revoke_all_for_user

logger = logging.getLogger(__name__)


async def revoke_sessions_for_user(tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Delete all refresh tokens for a user in ``tenant`` (SCIM deprovision, admin revoke)."""
    n = await revoke_all_for_user(tenant_id, user_id)
    if n == 0:
        logger.info(
            "scim.sessions_revoke.noop",
            extra={"tenant_id": str(tenant_id), "user_id": str(user_id), "note": "no active refresh keys"},
        )
