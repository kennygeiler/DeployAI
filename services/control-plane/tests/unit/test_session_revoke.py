from __future__ import annotations

import uuid

from control_plane.auth.session_revoke import revoke_sessions_for_user


def test_revoke_sessions_for_user_is_callable() -> None:
    """Contract for SCIM/SSO: must not throw before Story 2-4 (Redis)."""
    revoke_sessions_for_user(uuid.uuid4(), uuid.uuid4())
