"""Unit tests: stub graph + in-memory checkpointer (no Docker)."""

from __future__ import annotations

import uuid

import pytest
from deployai_checkpointer import checkpointer_thread_id
from langgraph.checkpoint.memory import InMemorySaver

from cartographer.stub_graph import build_stub_graph, canned_envelopes


@pytest.mark.asyncio
async def test_stub_graph_three_envelopes_match_canned() -> None:
    app = build_stub_graph().compile(checkpointer=InMemorySaver())
    tid = uuid.uuid4()
    cfg = {"configurable": {"thread_id": checkpointer_thread_id(tenant_id=tid, run_key="unit-1")}}
    out = await app.ainvoke({"step": 0, "envelopes": []}, cfg)
    want = [e.model_dump(mode="json") for e in canned_envelopes()]
    assert out["step"] == 3
    assert out["envelopes"] == want


@pytest.mark.asyncio
async def test_replay_two_runs_bit_identical() -> None:
    """Two isolated runs (fresh checkpointer) with same input produce identical output dicts."""
    tid = uuid.uuid4()
    cfg = {"configurable": {"thread_id": checkpointer_thread_id(tenant_id=tid, run_key="unit-replay")}}
    init = {"step": 0, "envelopes": []}
    o1 = await build_stub_graph().compile(checkpointer=InMemorySaver()).ainvoke(init, cfg)
    o2 = await build_stub_graph().compile(checkpointer=InMemorySaver()).ainvoke(init, cfg)
    assert o1 == o2
    assert o1 == {
        "step": 3,
        "envelopes": [e.model_dump(mode="json") for e in canned_envelopes()],
    }
