"""Create tenant + initial deployment strategist; verify empty canonical memory (FR70)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.app_identity.models import AppTenant, AppUser
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.exceptions import CanonicalBaselineNotEmptyError, UserRecordIncompleteError
from control_plane.infra.tenant_dek import wrap_tenant_dek
from control_plane.schemas.platform import PlatformAccountCreated

logger = logging.getLogger(__name__)


async def provision_platform_account(
    session: AsyncSession,
    *,
    organization_name: str,
    initial_strategist_email: str,
    actor_sub: str | None,
    initial_roles: list[str] | None = None,
    password_hash: str | None = None,
    display_name: str | None = None,
) -> PlatformAccountCreated:
    """Canonical tenant + initial-user provisioning (platform admin AND self-serve
    signup share this path — same DEK wrap, same empty-baseline check, same audit
    log). Defaults keep the Story 2-5 platform route byte-identical; self-serve
    signup passes ``initial_roles=["customer_admin"]`` + the argon2id hash."""
    tid = uuid.uuid4()
    email_norm = initial_strategist_email.strip().lower()
    dek_ct, key_id = wrap_tenant_dek()
    user = AppUser(
        tenant_id=tid,
        scim_external_id=None,
        user_name=email_norm,
        email=email_norm,
        given_name=display_name,
        active=True,
        roles=initial_roles if initial_roles is not None else ["deployment_strategist"],
        password_hash=password_hash,
        password_updated_at=datetime.now(UTC) if password_hash is not None else None,
    )
    t = AppTenant(
        id=tid,
        name=organization_name.strip(),
        scim_bearer_token_hash=None,
        tenant_dek_ciphertext=dek_ct,
        tenant_dek_key_id=key_id,
        users=[user],
    )
    session.add(t)
    await session.flush()
    n = (
        await session.execute(
            select(func.count()).select_from(CanonicalMemoryEvent).where(CanonicalMemoryEvent.tenant_id == tid)
        )
    ).scalar_one()
    if int(n) != 0:
        await session.rollback()
        raise CanonicalBaselineNotEmptyError("canonical memory baseline is not empty for new tenant")
    await session.commit()
    await session.refresh(t)
    await session.refresh(user)

    email_hash = hashlib.sha256(email_norm.encode("utf-8")).hexdigest()[:16]
    logger.info(
        "account.provisioned",
        extra={
            "event": "account.provisioned",
            "tenant_id": str(tid),
            "actor_sub": actor_sub,
            "strategist_email_sha256_16": email_hash,
        },
    )
    if user.created_at is None:  # pragma: no cover — server_default
        raise UserRecordIncompleteError("app_users.created_at missing after refresh")
    return PlatformAccountCreated(
        tenant_id=tid,
        initial_strategist_user_id=user.id,
        created_at=user.created_at,
    )
