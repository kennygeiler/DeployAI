"""Unit tests for control_plane.agents.llm.

Covers:
- ``get_llm_provider`` env-default resolution (stub vs anthropic).
- ``resolve_tenant_llm_provider`` falls back to ``env_fallback`` when no
  ``tenant_llm_configs`` row exists, and prefers the DB row when present.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.agents.llm import (
    get_llm_provider,
    resolve_tenant_llm_provider,
)
from control_plane.domain.app_identity.models import TenantLlmConfig


def _fake_session_returning(cfg: TenantLlmConfig | None) -> AsyncMock:
    """Build an AsyncSession stub whose ``execute`` returns a result whose
    ``scalar_one_or_none`` is ``cfg``. Keeps the test a true unit test —
    no DB engine spun up."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = cfg
    session = AsyncMock()
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_resolve_returns_fallback_when_no_db_row() -> None:
    fallback = object()  # opaque sentinel — resolver must not introspect it
    session = _fake_session_returning(None)
    out = await resolve_tenant_llm_provider(session, uuid.uuid4(), fallback)  # type: ignore[arg-type]
    assert out is fallback


@pytest.mark.asyncio
async def test_resolve_returns_stub_when_db_provider_stub() -> None:
    fallback = object()
    cfg = TenantLlmConfig(tenant_id=uuid.uuid4(), provider="stub")
    session = _fake_session_returning(cfg)
    out = await resolve_tenant_llm_provider(session, cfg.tenant_id, fallback)  # type: ignore[arg-type]
    # Stub provider has chat_complete / embed; cheapest assertion is that the
    # resolver did NOT return the env fallback.
    assert out is not fallback
    assert hasattr(out, "chat_complete")


@pytest.mark.asyncio
async def test_resolve_returns_anthropic_when_db_provider_anthropic() -> None:
    fallback = object()
    cfg = TenantLlmConfig(
        tenant_id=uuid.uuid4(),
        provider="anthropic",
        model_name="claude-opus-4-5",
        api_key="sk-test-key",
    )
    session = _fake_session_returning(cfg)
    out = await resolve_tenant_llm_provider(session, cfg.tenant_id, fallback)  # type: ignore[arg-type]
    assert out is not fallback
    # AnthropicProvider exposes the standard LLMProvider surface.
    assert hasattr(out, "chat_complete")


@pytest.mark.asyncio
async def test_resolve_openai_falls_back_to_stub_no_impl() -> None:
    """No OpenAI provider implementation yet — resolver logs + returns stub."""
    fallback = object()
    cfg = TenantLlmConfig(tenant_id=uuid.uuid4(), provider="openai", api_key="sk-x")
    session = _fake_session_returning(cfg)
    out = await resolve_tenant_llm_provider(session, cfg.tenant_id, fallback)  # type: ignore[arg-type]
    assert out is not fallback
    assert hasattr(out, "chat_complete")


def test_get_llm_provider_uses_stub_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYAI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = get_llm_provider()
    assert hasattr(p, "chat_complete")


def test_get_llm_provider_honors_explicit_stub_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_provider_py.anthropic import AnthropicProvider

    monkeypatch.setenv("DEPLOYAI_LLM_PROVIDER", "stub")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-something")  # should be ignored
    p = get_llm_provider()
    # Stub class is built per-call inside the factory so identity check on the
    # type won't work — just assert it's not the Anthropic provider and supports
    # the protocol surface.
    assert not isinstance(p, AnthropicProvider)
    assert hasattr(p, "chat_complete")
