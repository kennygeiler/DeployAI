"""Unit tests for ``control_plane.domain.member_roles`` resolver."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.engagement import TenantMemberRole
from control_plane.domain.member_roles import (
    BUILTIN_MEMBER_ROLES,
    resolve_allowed_member_roles,
)


def _fake_session_returning(rows: list[TenantMemberRole]) -> AsyncMock:
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_returns_builtin_only_when_no_custom_rows() -> None:
    session = _fake_session_returning([])
    allowed = await resolve_allowed_member_roles(session, uuid.uuid4())
    assert allowed == set(BUILTIN_MEMBER_ROLES)


@pytest.mark.asyncio
async def test_returns_union_of_builtin_and_custom() -> None:
    tid = uuid.uuid4()
    custom = [
        TenantMemberRole(tenant_id=tid, name="clinical_lead", label="Clinical lead"),
        TenantMemberRole(tenant_id=tid, name="sales_engineer", label="Sales engineer"),
    ]
    session = _fake_session_returning(custom)
    allowed = await resolve_allowed_member_roles(session, tid)
    assert allowed == set(BUILTIN_MEMBER_ROLES) | {"clinical_lead", "sales_engineer"}


@pytest.mark.asyncio
async def test_builtin_constant_shape() -> None:
    assert "fde" in BUILTIN_MEMBER_ROLES
    assert "deployment_strategist" in BUILTIN_MEMBER_ROLES
    assert "biz_dev" in BUILTIN_MEMBER_ROLES
    assert len(BUILTIN_MEMBER_ROLES) == 3
