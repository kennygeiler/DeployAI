"""Unit tests for ``control_plane.domain.member_roles``."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.engagement import TenantMemberRole
from control_plane.domain.member_roles import (
    BUILTIN_MEMBER_ROLES,
    list_tenant_member_roles,
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


def test_builtin_member_roles_is_the_baked_in_trio() -> None:
    assert BUILTIN_MEMBER_ROLES == ("fde", "deployment_strategist", "biz_dev")


@pytest.mark.asyncio
async def test_list_returns_session_rows() -> None:
    tid = uuid.uuid4()
    row = TenantMemberRole(tenant_id=tid, name="clinical_lead", label="Clinical lead")
    session = _fake_session_returning([row])
    out = await list_tenant_member_roles(session, tid)
    assert out == [row]


@pytest.mark.asyncio
async def test_resolve_with_no_custom_returns_builtins_only() -> None:
    session = _fake_session_returning([])
    out = await resolve_allowed_member_roles(session, uuid.uuid4())
    assert out == set(BUILTIN_MEMBER_ROLES)


@pytest.mark.asyncio
async def test_resolve_unions_builtins_and_custom() -> None:
    tid = uuid.uuid4()
    rows = [
        TenantMemberRole(tenant_id=tid, name="clinical_lead", label="Clinical lead"),
        TenantMemberRole(tenant_id=tid, name="sales_engineer", label="Sales engineer"),
    ]
    session = _fake_session_returning(rows)
    out = await resolve_allowed_member_roles(session, tid)
    assert out == set(BUILTIN_MEMBER_ROLES) | {"clinical_lead", "sales_engineer"}
