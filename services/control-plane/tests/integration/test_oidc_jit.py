"""Integration: OIDC JIT user on system SSO-pending tenant (Story 2-2)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.auth.sso_tenant import SSO_PENDING_TENANT_ID
from control_plane.services.oidc_user import resolve_or_create_oidc_user

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_jit_user_inserts_on_pending_tenant(postgres_engine: Engine) -> None:
    eid = f"entra|{uuid.uuid4()}"
    url = _async_database_url_from_engine(postgres_engine)
    eng = create_async_engine(url, future=True)
    mk = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with mk() as session:
            u, r = await resolve_or_create_oidc_user(
                session, entra_sub=eid, email="jit@example.com", idp_name="JIT Test"
            )
        assert u.tenant_id == SSO_PENDING_TENANT_ID
        assert u.entra_sub == eid
        assert u.email == "jit@example.com"
        assert r == ["pending_assignment"]
    finally:
        await eng.dispose()
