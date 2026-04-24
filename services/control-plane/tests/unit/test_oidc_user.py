"""Unit tests for OIDC JIT role mapping (Story 2-2)."""

from __future__ import annotations

from control_plane.services.oidc_user import roles_for_access_token


def test_roles_for_access_token() -> None:
    assert roles_for_access_token(None) == ["pending_assignment"]
    assert roles_for_access_token([]) == ["pending_assignment"]
    assert roles_for_access_token(["deployment_strategist"]) == ["deployment_strategist"]
