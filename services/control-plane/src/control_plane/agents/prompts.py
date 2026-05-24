"""Per-tenant agent system-prompt resolver — DB override wins, otherwise caller-provided default."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.app_identity.models import TenantAgentPrompt


async def resolve_tenant_prompt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    agent_name: str,
    default_prompt: str,
) -> str:
    """Return the tenant's override prompt for ``agent_name``, else default."""
    r = await session.execute(
        select(TenantAgentPrompt).where(
            TenantAgentPrompt.tenant_id == tenant_id,
            TenantAgentPrompt.agent_name == agent_name,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        return default_prompt
    return row.prompt_text
