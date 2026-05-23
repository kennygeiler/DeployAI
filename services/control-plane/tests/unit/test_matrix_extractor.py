"""Unit tests for the Phase 6 matrix extraction agent.

Pure function — no DB, no FastAPI. A fake LLM returns hand-crafted JSON;
the agent parses, validates, and resolves edge titles to existing node ids.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed

from control_plane.agents.matrix_extractor import (
    ExistingNode,
    extract_matrix_proposals,
)


class _FakeLLM:
    """Returns a fixed string; records the last messages it saw."""

    id = "fake"

    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.last_messages: list[ChatMessage] | None = None

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        for chunk in (self.chat_complete(messages),):
            yield chunk

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


class _RaisingLLM(_FakeLLM):
    def chat_complete(self, *args: Any, **kwargs: Any) -> str:
        _ = args, kwargs
        raise RuntimeError("boom")


def _event_args(content: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": uuid.uuid4(),
        "event_source": "meeting_note",
        "event_occurred_at": datetime(2026, 5, 9, 15, 0, tzinfo=UTC),
        "event_payload": {"content": content},
    }


def test_extract_returns_valid_node_and_edge() -> None:
    sys_id = uuid.uuid4()
    risk_id = uuid.uuid4()
    existing = [
        ExistingNode(id=sys_id, title="LiDAR ingest", node_type="system"),
        ExistingNode(id=risk_id, title="Calibration drift", node_type="risk"),
    ]
    llm = _FakeLLM(
        json.dumps(
            [
                {
                    "kind": "node",
                    "node_type": "decision",
                    "title": "Phased rollout",
                    "rationale": "Team agreed to ship in waves.",
                },
                {
                    "kind": "edge",
                    "edge_type": "threatens",
                    "from_title": "Calibration drift",
                    "to_title": "LiDAR ingest",
                    "rationale": "Drift breaks ingest.",
                },
            ]
        )
    )
    drafts = extract_matrix_proposals(
        **_event_args({"text": "Decided phased rollout; calibration drift threatens ingest."}),
        existing_nodes=existing,
        llm=llm,
    )
    assert [d.kind for d in drafts] == ["node", "edge"]
    assert drafts[0].payload == {"node_type": "decision", "title": "Phased rollout"}
    assert drafts[1].payload == {
        "edge_type": "threatens",
        "from_node_id": str(risk_id),
        "to_node_id": str(sys_id),
    }


def test_extract_drops_edge_when_title_does_not_resolve() -> None:
    existing = [ExistingNode(id=uuid.uuid4(), title="LiDAR ingest", node_type="system")]
    llm = _FakeLLM(
        json.dumps(
            [
                {
                    "kind": "edge",
                    "edge_type": "depends_on",
                    "from_title": "LiDAR ingest",
                    "to_title": "Ghost node",
                    "rationale": "won't resolve",
                }
            ]
        )
    )
    drafts = extract_matrix_proposals(
        **_event_args({"text": "x"}),
        existing_nodes=existing,
        llm=llm,
    )
    assert drafts == []


def test_extract_drops_invalid_node_type() -> None:
    llm = _FakeLLM(
        json.dumps(
            [
                {"kind": "node", "node_type": "gremlin", "title": "Bogus"},
                {"kind": "node", "node_type": "risk", "title": "Real risk"},
            ]
        )
    )
    drafts = extract_matrix_proposals(
        **_event_args({"text": "x"}),
        existing_nodes=[],
        llm=llm,
    )
    assert [d.payload["title"] for d in drafts] == ["Real risk"]


def test_extract_returns_empty_on_llm_error() -> None:
    drafts = extract_matrix_proposals(
        **_event_args({"text": "x"}),
        existing_nodes=[],
        llm=_RaisingLLM(),
    )
    assert drafts == []


def test_extract_returns_empty_on_bad_json() -> None:
    drafts = extract_matrix_proposals(
        **_event_args({"text": "x"}),
        existing_nodes=[],
        llm=_FakeLLM("not even close to JSON"),
    )
    assert drafts == []


def test_extract_includes_existing_nodes_in_prompt() -> None:
    existing = [ExistingNode(id=uuid.uuid4(), title="NYC DOT", node_type="organization")]
    llm = _FakeLLM("[]")
    extract_matrix_proposals(
        **_event_args({"text": "x"}),
        existing_nodes=existing,
        llm=llm,
    )
    assert llm.last_messages is not None
    user_content = llm.last_messages[-1]["content"]
    assert "NYC DOT" in user_content
    assert "organization" in user_content
