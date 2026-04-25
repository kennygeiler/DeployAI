from __future__ import annotations

from llm_provider_py.stub import create_stub_provider
from llm_provider_py.util import DEFAULT_CAPS


def test_stub_meets_all_capability_flags() -> None:
    p = create_stub_provider()
    assert p.capabilities() == DEFAULT_CAPS


def test_determinism() -> None:
    p = create_stub_provider()
    t = p.chat_complete([{"role": "user", "content": "abc"}])
    assert t.startswith("stub:")
    e = p.embed("yz")
    assert len(e) == 16
