"""Per-tenant agent prompt resolver (Sprint 5).

Resolution order:
1. Per-tenant DB row (``tenant_agent_prompts``) keyed by (tenant_id,
   agent_name) — the customer-edited override.
2. The default prompt the agent module ships with — passed in as
   ``default_prompt`` so the resolver stays a pure helper that does not
   need to import agent modules.

Mirrors the shape of ``resolve_tenant_llm_provider`` in
``control_plane/agents/llm.py``: route handlers call this after pulling
``tenant_id`` from the path and pass the agent's
``_system_prompt()`` as ``default_prompt``.
"""

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
