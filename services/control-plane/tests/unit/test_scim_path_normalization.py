from __future__ import annotations

from control_plane.api.routes.scim import _normalize_scim_path


def test_normalize_scim_path_json_pointer_style() -> None:
    assert _normalize_scim_path("/name/givenName") == "name.givenname"
    assert _normalize_scim_path("/userName") == "username"


def test_normalize_scim_path_plain() -> None:
    assert _normalize_scim_path("userName") == "username"
    assert _normalize_scim_path(None) == ""
