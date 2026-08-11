"""Ticket D0: adversarial_review must use the async provider path.

The node runs inside the request event loop; the sync ``chat_complete``
would block it for the whole provider round trip, so the call site awaits
``chat_complete_async`` instead. The fake here only implements the async
method — if the node ever regresses to the sync call, this test fails
with an AttributeError.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from llm_provider_py.types import ChatMessage

from control_plane.agents.agent_kenny.nodes.adversarial import adversarial_review
from control_plane.agents.agent_kenny.types import AgentState


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="q",
        started_at=datetime.now(UTC),
        accumulated_text="draft reply",
    )


class _AsyncOnlyProvider:
    id = "async-only-fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    async def chat_complete_async(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.calls.append(messages)
        return self.reply


@pytest.mark.asyncio
async def test_adversarial_review_awaits_async_provider() -> None:
    provider = _AsyncOnlyProvider("- claim has no evidence\n- unstated assumption about scope")
    state = _state()

    out: Any = await adversarial_review(provider, state)  # type: ignore[arg-type]

    assert len(provider.calls) == 1
    assert [c.severity for c in out.adversarial_concern_objs] == ["blocking", "warning"]
    assert out.adversarial_concerns == [
        "claim has no evidence",
        "unstated assumption about scope",
    ]


@pytest.mark.asyncio
async def test_adversarial_review_none_reply_yields_no_concerns() -> None:
    provider = _AsyncOnlyProvider("NONE")
    state = _state()

    out: Any = await adversarial_review(provider, state)  # type: ignore[arg-type]

    assert out.adversarial_concerns == []
    assert out.adversarial_concern_objs == []
