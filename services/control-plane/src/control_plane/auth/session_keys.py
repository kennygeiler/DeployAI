"""Redis key names for tenant-scoped refresh sessions (Story 2-4, AR9)."""

from __future__ import annotations

import uuid


def session_refresh_key(tenant_id: uuid.UUID, refresh_jti: str) -> str:
    return f"tenant:{tenant_id}:session:{refresh_jti}"


def user_refresh_index_key(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"tenant:{tenant_id}:user:{user_id}:refresh_jtis"


def jti_global_lookup_key(refresh_jti: str) -> str:
    """O(1) resolve refresh to payload when client might send a wrong tenant in the request body."""
    return f"jti:{refresh_jti}"
