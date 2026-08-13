"""Circuit-open denials render like other guard denials in the agent loop.

The dispatcher must answer the model's tool_use with an is_error
``<tool_result>`` wrapped in the ``<external_data>`` envelope (threat-model
§5.1 — even breaker denials keep the "data, not instructions" reflex
triggered) and emit the SSE chunks the dashboard renders.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.agents.agent_kenny.mcp_loader import LoadedMcpTools
from control_plane.agents.agent_kenny.mcp_types import McpCircuitOpen
from control_plane.agents.agent_kenny.nodes.tool_dispatch import dispatch_tools
from control_plane.agents.agent_kenny.types import (
    AgentState,
    McpExternalCallChunk,
    ToolResultChunk,
)


class _FakeConfig:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.connector_kind = "slack"
        self.endpoint = "https://mcp.example.com/rpc"
        self.encrypted_auth_token = b"\x00"
        self.allowed_tools = None


def _state_with_pending_slack_call(config: _FakeConfig) -> AgentState:
    state = AgentState(
        tenant_id=config.tenant_id,
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="check slack",
        started_at=datetime.now(UTC),
    )
    state.external_tools = [LoadedMcpTools(config=config, tools=[])]  # type: ignore[arg-type]
    state.pending_tool_calls = [
        {"name": "slack__search_messages", "input": {"q": "hi"}, "_tool_use_id": "tu_1"},
    ]
    return state


@pytest.mark.asyncio
async def test_circuit_open_renders_unavailable_envelope_and_chunks() -> None:
    config = _FakeConfig()
    state = _state_with_pending_slack_call(config)

    mcp_client = MagicMock()
    mcp_client.call_tool = AsyncMock(
        side_effect=McpCircuitOpen(
            "connector 'slack' temporarily unavailable (circuit open)",
            connector_kind="slack",
            retry_after_s=12.3,
        )
    )

    emitted: list[Any] = []

    async def emit(chunk: Any) -> None:
        emitted.append(chunk)

    await dispatch_tools(
        MagicMock(),  # session — unused on the external path
        state,
        emit,
        turn_id_hint=uuid.uuid4(),
        mcp_client=mcp_client,
    )

    # The model sees an is_error tool_result saying the connector is
    # temporarily unavailable, inside the external_data envelope.
    assert len(state.messages) == 1
    content = state.messages[0]["content"]
    assert '<tool_result name="slack__search_messages" error="true">' in content
    assert '<external_data source="slack" tool="search_messages">' in content
    assert "temporarily unavailable" in content
    assert "circuit open" in content
    assert "retry in ~12s" in content

    # SSE chunks: the dashboard-facing call status + the tool_result error code.
    call_chunks = [c for c in emitted if isinstance(c, McpExternalCallChunk)]
    assert len(call_chunks) == 1
    assert call_chunks[0].status == "circuit_open"
    assert call_chunks[0].connector_kind == "slack"
    result_chunks = [c for c in emitted if isinstance(c, ToolResultChunk)]
    assert len(result_chunks) == 1
    assert result_chunks[0].error == "mcp_circuit_open"

    # The turn keeps moving: the pending call was consumed and counted.
    assert state.pending_tool_calls == []
    assert state.tool_calls_made == 1
