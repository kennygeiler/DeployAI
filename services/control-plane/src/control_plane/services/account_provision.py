"""Create tenant + initial deployment strategist; verify empty canonical memory (FR70)."""

from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import tenant_session
from control_plane.domain.app_identity.models import AppTenant, AppUser
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.infra.tenant_dek import wrap_tenant_dek
from control_plane.schemas.platform import PlatformAccountCreated

logger = logging.getLogger(__name__)


async def provision_platform_account(
    session: AsyncSession,
    *,
    organization_name: str,
    initial_strategist_email: str,
    actor_sub: str | None,
) -> PlatformAccountCreated:
    tid = uuid.uuid4()
    dek_ct, key_id = wrap_tenant_dek()
    user = AppUser(
        tenant_id=tid,
        scim_external_id=None,
        user_name=initial_strategist_email.strip().lower(),
        email=initial_strategist_email.strip().lower(),
        active=True,
        roles=["deployment_strategist"],
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
    await session.commit()
    await session.refresh(t)
    await session.refresh(user)

    email_hash = hashlib.sha256(initial_strategist_email.encode("utf-8")).hexdigest()[:16]
    logger.info(
        "account.provisioned",
        extra={
            "event": "account.provisioned",
            "tenant_id": str(tid),
            "actor_sub": actor_sub,
            "strategist_email_sha256_16": email_hash,
        },
    )

    async with tenant_session(tid) as ts:
        n = (
            await ts.execute(
                select(func.count())
                .select_from(CanonicalMemoryEvent)
                .where(CanonicalMemoryEvent.tenant_id == tid)
            )
        ).scalar_one()
        if int(n) != 0:
            raise RuntimeError("canonical memory baseline is not empty for new tenant")
    if user.created_at is None:  # pragma: no cover — server_default
        raise RuntimeError("user created_at missing after refresh")
    return PlatformAccountCreated(
        tenant_id=tid,
        initial_strategist_user_id=user.id,
        created_at=user.created_at,
    )
