"""Session revocation hook; Redis key format finalized in Story 2-4."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def revoke_sessions_for_user(tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Delete cached sessions for a user. TODO(2-4): `tenant:{tid}:session:*` pattern."""
    # Contract for SCIM/SSO: callers may rely on this being invoked; implementation ships with 2-4.
    logger.info(
        "scim.sessions_revoke.noop",
        extra={"tenant_id": str(tenant_id), "user_id": str(user_id), "note": "TODO(2-4)"},
    )
