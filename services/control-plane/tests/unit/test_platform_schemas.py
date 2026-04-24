"""Platform account request validation (Story 2-5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from control_plane.schemas.platform import PlatformAccountCreate


def test_organization_name_rejects_whitespace_only() -> None:
    with pytest.raises(ValidationError):
        PlatformAccountCreate(organization_name="   ", initial_strategist_email="a@b.example")


def test_organization_name_strips_surrounding_space() -> None:
    m = PlatformAccountCreate(
        organization_name="  Acme  ",
        initial_strategist_email="a@b.example",
    )
    assert m.organization_name == "Acme"
