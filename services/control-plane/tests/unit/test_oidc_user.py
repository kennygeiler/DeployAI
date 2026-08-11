"""Unit tests for OIDC JIT role mapping + JIT-disabled rejection (Story 2-2, ticket A1)."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.services.oidc_user import (
    JitProvisioningDisabledError,
    resolve_or_create_oidc_user,
    roles_for_access_token,
)


def test_roles_for_access_token() -> None:
    assert roles_for_access_token(None) == ["pending_assignment"]
    assert roles_for_access_token([]) == ["pending_assignment"]
    assert roles_for_access_token(["deployment_strategist"]) == ["deployment_strategist"]


class _NoRowResult:
    def scalar_one_or_none(self) -> None:
        return None


class _NoRowSession:
    """Fake AsyncSession: the entra_sub lookup finds nothing; writes must not happen."""

    def __init__(self) -> None:
        self.added: list[object] = []

    async def execute(self, *_args: object, **_kwargs: object) -> _NoRowResult:
        return _NoRowResult()

    def add(self, obj: object) -> None:  # pragma: no cover - must not be reached
        self.added.append(obj)


@pytest.mark.asyncio
async def test_resolve_raises_when_jit_disabled_and_user_unknown() -> None:
    fake = _NoRowSession()
    with pytest.raises(JitProvisioningDisabledError):
        await resolve_or_create_oidc_user(
            cast(AsyncSession, fake),
            entra_sub="entra|unknown",
            email="unknown@example.com",
            idp_name="Unknown",
            jit_enabled=False,
        )
    assert fake.added == []
