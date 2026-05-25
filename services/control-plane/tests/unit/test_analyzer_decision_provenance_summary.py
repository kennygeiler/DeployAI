"""Unit: decision_provenance_summary analyzer (Phase F2.b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence import decision_provenance_summary as mod


class _FakeProvider:
    id = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def chat_complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        self.calls.append(messages)
        return self.reply

    def embed(self, text: str) -> list[float]:
        return []

    def capabilities(self) -> dict[str, bool]:
        return {}

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        return None


def _event(source_kind: str, summary: str) -> LedgerEvent:
    return LedgerEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        occurred_at=datetime(2026, 5, 20, tzinfo=UTC),
        recorded_at=datetime(2026, 5, 20, tzinfo=UTC),
        actor_kind="user",
        actor_id=None,
        source_kind=source_kind,
        source_ref=None,
        summary=summary,
        detail={},
    )


def test_ask_llm_builds_prompt_with_chain_and_anchor() -> None:
    provider = _FakeProvider("Decision driven by prior risk. Two sentences here.")
    anchor = _event("proposal_accepted", "accept decision: vendor change")
    chain = [_event("llm_proposal_created", "extract: vendor change"), _event("insight_opened", "risk: cost overrun")]
    out = mod._ask_llm(provider, chain=chain, anchor=anchor)
    assert out == "Decision driven by prior risk. Two sentences here."
    assert len(provider.calls) == 1
    user_message = provider.calls[0][1]["content"]
    assert "accept decision: vendor change" in user_message
    assert "extract: vendor change" in user_message
    assert "risk: cost overrun" in user_message


def test_ask_llm_returns_none_when_provider_raises() -> None:
    class _Broken:
        id = "broken"

        def chat_complete(self, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("boom")

        def embed(self, text: str) -> list[float]:
            return []

        def capabilities(self) -> dict[str, bool]:
            return {}

        async def chat_stream(self, *args: Any, **kwargs: Any) -> Any:
            return None

    anchor = _event("proposal_accepted", "x")
    out = mod._ask_llm(_Broken(), chain=[_event("x", "y")], anchor=anchor)
    assert out is None


def test_ask_llm_returns_none_when_reply_blank() -> None:
    anchor = _event("proposal_accepted", "x")
    out = mod._ask_llm(_FakeProvider("   "), chain=[_event("x", "y")], anchor=anchor)
    assert out is None
