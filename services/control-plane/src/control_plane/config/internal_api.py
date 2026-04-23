"""Internal API shared-secret validation (Story 1-17, Epic 2 replaces with auth)."""

from __future__ import annotations

import hmac
import os


def internal_api_key() -> str:
    """Key required on ``X-DeployAI-Internal-Key`` for internal routes.

    In tests, set :envvar:`DEPLOYAI_INTERNAL_API_KEY` before importing the
    app (and clear :func:`control_plane.db.get_engine` cache).
    """
    return os.environ.get("DEPLOYAI_INTERNAL_API_KEY", "")


def verify_internal_key(header_value: str | None) -> bool:
    if not internal_api_key():
        return False
    if not header_value:
        return False
    return hmac.compare_digest(header_value, internal_api_key())
