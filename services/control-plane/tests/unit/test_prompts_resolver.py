"""Unit tests for ``control_plane.agents.prompts.resolve_tenant_prompt``.

Mirrors the shape of ``test_llm_provider_factory.py``: the helper takes
an AsyncSession, looks up ``tenant_agent_prompts`` by (tenant_id,
agent_name) and either returns the override or the supplied default.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.agents.prompts import resolve_tenant_prompt
from control_plane.domain.app_identity.models import TenantAgentPrompt


def _fake_session_returning(row: TenantAgentPrompt | None) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session = AsyncMock()
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_returns_default_when_no_db_row() -> None:
    session = _fake_session_returning(None)
    out = await resolve_tenant_prompt(session, uuid.uuid4(), "oracle", "the default")
    assert out == "the default"


@pytest.mark.asyncio
async def test_returns_override_when_db_row_present() -> None:
    tid = uuid.uuid4()
    row = TenantAgentPrompt(tenant_id=tid, agent_name="oracle", prompt_text="custom oracle prompt")
    session = _fake_session_returning(row)
    out = await resolve_tenant_prompt(session, tid, "oracle", "the default")
    assert out == "custom oracle prompt"


@pytest.mark.asyncio
async def test_different_agent_names_isolated() -> None:
    tid = uuid.uuid4()
    row = TenantAgentPrompt(tenant_id=tid, agent_name="cartographer", prompt_text="carto override")
    session = _fake_session_returning(row)
    out = await resolve_tenant_prompt(session, tid, "cartographer", "carto default")
    assert out == "carto override"
