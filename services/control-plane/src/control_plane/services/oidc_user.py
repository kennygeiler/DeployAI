"""JIT app_users for Microsoft Entra OIDC (Story 2-2)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.auth.sso_tenant import SSO_PENDING_TENANT_ID
from control_plane.domain.app_identity.models import AppUser


def roles_for_access_token(roles_json: object | None) -> list[str]:
    """Map DB JSONB roles to JWT claims. Empty or null becomes ``pending_assignment`` only."""
    if roles_json is None:
        return ["pending_assignment"]
    if not isinstance(roles_json, list):
        return ["pending_assignment"]
    out: list[str] = [x for x in roles_json if isinstance(x, str)]
    return out if out else ["pending_assignment"]


async def resolve_or_create_oidc_user(
    session: AsyncSession,
    *,
    entra_sub: str,
    email: str | None,
    idp_name: str | None,
) -> tuple[AppUser, list[str]]:
    """Return ``(user, roles_for_jwt)``.

    Reuses the first ``app_users`` row with matching ``entra_sub`` (if any) so
    post-provision logins keep tenant + role assignments. Otherwise inserts
    into the system SSO-pending tenant with ``pending_assignment`` only.
    """
    r = await session.execute(
        select(AppUser)
        .where(AppUser.entra_sub == entra_sub)
        .order_by(AppUser.created_at.asc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    uname = email if email else f"{entra_sub}@oidc.local"
    if row is not None:
        if email and row.email != email:
            row.email = email
        if idp_name and (not row.given_name):
            # Store full name in given_name when we do not parse family_name.
            row.given_name = idp_name
        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
        return row, roles_for_access_token(row.roles)

    u = AppUser(
        tenant_id=SSO_PENDING_TENANT_ID,
        scim_external_id=None,
        entra_sub=entra_sub,
        user_name=uname,
        email=email,
        given_name=idp_name,
        family_name=None,
        active=True,
        roles=["pending_assignment"],
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u, roles_for_access_token(u.roles)
