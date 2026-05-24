"""LLM provider factory for control-plane agents (Phase 6.2c + Sprint 1).

Resolution order:
1. Per-tenant DB config (``tenant_llm_configs``) when the route is
   tenant-scoped — looked up via ``resolve_tenant_llm_provider`` from
   inside the route handler.
2. Env defaults (``DEPLOYAI_LLM_PROVIDER`` + ``ANTHROPIC_API_KEY`` /
   ``OPENAI_API_KEY``) — what ``get_llm_provider`` (the FastAPI
   ``Depends`` factory) returns.
3. Stub — when nothing else resolves, keeps local dev / CI green.

Why two functions: FastAPI ``Depends`` happens once per request at
parameter-resolution time and can't peek at path params without
creating a path-param shadow on every consuming route. The tenant
lookup lives in a plain async helper that handlers call after they
have the tenant_id in hand. Tests still override ``get_llm_provider``
via ``app.dependency_overrides`` and the override wins both paths
because the override returns the same instance the helper would
otherwise fall back to.

See ``docs/product/matrix-extraction-agent.md`` §3 and the Sprint 1
LLM-config design.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.openai import OpenAIProvider
from llm_provider_py.stub import create_stub_provider
from llm_provider_py.types import LLMProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.app_identity.models import TenantLlmConfig

_log = logging.getLogger(__name__)


def get_llm_provider() -> LLMProvider:
    """FastAPI ``Depends`` factory — env-default provider.

    Used by routes that are NOT tenant-scoped (none in production
    today, but keeps the seam open) and as the fallback in
    ``resolve_tenant_llm_provider``. Tests override via
    ``app.dependency_overrides[get_llm_provider]``.
    """
    return _from_env()


async def resolve_tenant_llm_provider(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    env_fallback: LLMProvider,
) -> LLMProvider:
    """Resolve the LLM for one tenant: DB config first, then env fallback.

    Route handlers call this after pulling ``tenant_id`` from the path /
    query and injecting ``env_fallback`` via ``Depends(get_llm_provider)``.
    If a test has overridden ``get_llm_provider``, ``env_fallback`` is
    already the fake provider, so the override still wins in tests that
    do not seed a ``tenant_llm_configs`` row.
    """
    r = await session.execute(select(TenantLlmConfig).where(TenantLlmConfig.tenant_id == tenant_id))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        return env_fallback
    return _from_db_config(cfg)


def _from_db_config(cfg: TenantLlmConfig) -> LLMProvider:
    if cfg.provider == "anthropic":
        return _anthropic(api_key=cfg.api_key, model=cfg.model_name)
    if cfg.provider == "openai":
        return _openai(api_key=cfg.api_key, model=cfg.model_name)
    # provider == "stub" → explicit stub selection
    return _stub()


def _from_env() -> LLMProvider:
    choice = os.getenv("DEPLOYAI_LLM_PROVIDER", "").strip().lower()
    if choice == "stub":
        return _stub()
    if choice == "anthropic":
        return _anthropic()
    if choice == "openai":
        return _openai()
    # Key-presence fallback: Anthropic wins when both keys are set, preserving
    # pre-OpenAI-wiring behavior. Use DEPLOYAI_LLM_PROVIDER to override.
    if os.getenv("ANTHROPIC_API_KEY"):
        return _anthropic()
    if os.getenv("OPENAI_API_KEY"):
        return _openai()
    _log.info("get_llm_provider: no DEPLOYAI_LLM_PROVIDER / ANTHROPIC_API_KEY / OPENAI_API_KEY — using stub provider.")
    return _stub()


def _anthropic(api_key: str | None = None, model: str | None = None) -> LLMProvider:
    provider: Any = AnthropicProvider(api_key=api_key, model=model)
    return provider


def _openai(api_key: str | None = None, model: str | None = None) -> LLMProvider:
    provider: Any = OpenAIProvider(api_key=api_key, chat_model=model)
    return provider


def _stub() -> LLMProvider:
    provider: Any = create_stub_provider()
    return provider
