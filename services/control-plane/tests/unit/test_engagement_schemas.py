"""Unit tests for the engagement API schemas (Phase 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from control_plane.api.routes.engagements_internal import EngagementCreate


def test_engagement_create_defaults_to_first_phase() -> None:
    m = EngagementCreate(name="NYC DOT LiDAR")
    assert m.current_phase == "P1_pre_engagement"
    assert m.customer_account is None


def test_engagement_create_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        EngagementCreate(name="")


def test_engagement_create_accepts_customer_account() -> None:
    m = EngagementCreate(name="Acme rollout", customer_account="Acme Corp")
    assert m.customer_account == "Acme Corp"
