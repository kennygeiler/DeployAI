"""LLM provider factory for control-plane agents (Phase 6.2c).

Used as a FastAPI ``Depends`` for routes that call an LLM. Tests override
this dependency via ``app.dependency_overrides[get_llm_provider] = …`` to
inject a stub or hand-crafted fake; production resolves to Anthropic.

Selection:
- ``DEPLOYAI_LLM_PROVIDER=stub`` → ``create_stub_provider()`` (offline,
  deterministic).
- ``DEPLOYAI_LLM_PROVIDER=anthropic`` or unset *with* ``ANTHROPIC_API_KEY``
  present → ``AnthropicProvider()``.
- Otherwise → stub (keeps local dev / CI green without secrets).

See ``docs/product/matrix-extraction-agent.md`` §3.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.stub import create_stub_provider
from llm_provider_py.types import LLMProvider

_log = logging.getLogger(__name__)


def get_llm_provider() -> LLMProvider:
    choice = os.getenv("DEPLOYAI_LLM_PROVIDER", "").strip().lower()
    if choice == "stub":
        return _stub()
    if choice == "anthropic":
        return _anthropic()
    if os.getenv("ANTHROPIC_API_KEY"):
        return _anthropic()
    _log.info("get_llm_provider: no DEPLOYAI_LLM_PROVIDER / ANTHROPIC_API_KEY — using stub provider.")
    return _stub()


def _anthropic() -> LLMProvider:
    provider: Any = AnthropicProvider()
    return provider


def _stub() -> LLMProvider:
    provider: Any = create_stub_provider()
    return provider
