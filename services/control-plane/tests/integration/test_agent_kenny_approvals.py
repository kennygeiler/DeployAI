"""Integration tests for in-turn HITL approvals (pilot-refresh D4).

LangGraph runtime only — the interrupt/resume mechanic requires the
checkpointed StateGraph. An internal tool is force-flagged via
``DEPLOYAI_AGENT_APPROVAL_TOOLS`` so the flow is exercised without any
external MCP server:

- stream-v2 pauses with an ``approval_required`` frame (no ``done``),
  and an ``agent_approval_requested`` ledger row is committed;
- POST ``/oracle/approvals/{thread_id}`` with ``approved=true`` resumes
  the turn to completion, returns the reply JSON, and ledgers
  ``agent_approval_granted``;
- ``approved=false`` feeds the LLM a denial tool_result, still finishes
  the turn, and ledgers ``agent_approval_denied``;
- scope checks: foreign-tenant thread ids 404, malformed ids 400,
  threads without a pending interrupt 404.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import (
    CapabilityMatrix,
    ChatMessage,
    StopReason,
    TextDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.agent_kenny.checkpointer import close_checkpointer
from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


class _ScriptedLLM:
    """Stub provider: each entry is (text, [tool calls]) per LLM call."""

    id = "approvals-stub"

    def __init__(self) -> None:
        self.script: list[tuple[str, list[dict[str, Any]]]] = []
        self.calls = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = messages, temperature, max_output_tokens
        return "NONE"

    async def chat_complete_async(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        return self.chat_complete(messages, temperature=temperature, max_output_tokens=max_output_tokens)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        yield ""

    async def chat_complete_stream(self, messages: list[ChatMessage], **kwargs: Any) -> AsyncIterator[Any]:
        _ = messages, kwargs
        yield None  # pragma: no cover — v2 uses the tools stream

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, tools, temperature, max_output_tokens
        idx = self.calls
        self.calls += 1
        text_val, tool_calls = self.script[idx] if idx < len(self.script) else ("", [])
        if text_val:
            yield TextDelta(content=text_val)
        for i, call in enumerate(tool_calls):
            block_id = f"toolu_{idx}_{i}"
            yield ToolUseStart(id=block_id, name=str(call["name"]))
            yield ToolUseEnd(id=block_id, name=str(call["name"]), input=dict(call.get("input") or {}))
        yield StopReason(
            reason="tool_use" if tool_calls else "end_turn",
            usage={"input_tokens": 80, "output_tokens": 40},
        )

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def a_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "approvals-test-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    monkeypatch.setenv("DEPLOYAI_AGENT_RUNTIME", "langgraph")
    # Force an internal tool onto the approval list so the interrupt path
    # runs without any external MCP configuration.
    monkeypatch.setenv("DEPLOYAI_AGENT_APPROVAL_TOOLS", "get_engagement_summary")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "approvals-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        await close_checkpointer()
        clear_engine_cache()


@pytest.fixture
def stub_llm() -> Iterator[_ScriptedLLM]:
    stub = _ScriptedLLM()

    def _f() -> _ScriptedLLM:
        return stub

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _ins_tenant_user(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    tid, uid = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'approvals-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {"u": str(uid), "t": str(tid), "n": f"approver-{uid}", "e": f"{uid}@example.test"},
        )
    return tid, uid


async def _new_engagement(client: AsyncClient, tid: uuid.UUID) -> uuid.UUID:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Approvals test"})
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


def _seed_event(engine: Engine, *, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> uuid.UUID:
    ev = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary, detail) "
                "VALUES (:id, :t, :e, now(), 'user', 'manual_capture', 'seed', '{}'::jsonb)"
            ),
            {"id": str(ev), "t": str(tenant_id), "e": str(engagement_id)},
        )
    return ev


def _parse_sse_frames(payload: str) -> list[tuple[str, dict[str, Any]]]:
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in payload.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_text = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_text = line[len("data: ") :].strip()
        if not event_name:
            continue
        try:
            frames.append((event_name, json.loads(data_text) if data_text else {}))
        except json.JSONDecodeError:
            continue
    return frames


def _count(engine: Engine, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


async def _start_paused_turn(
    client: AsyncClient,
    engine: Engine,
    stub: _ScriptedLLM,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, uuid.UUID]:
    """Drive one turn to the approval pause; returns ids + thread_id."""
    tid, uid = _ins_tenant_user(engine)
    eid = await _new_engagement(client, tid)
    seed = _seed_event(engine, tenant_id=tid, engagement_id=eid)
    stub.script = [
        ("", [{"name": "get_engagement_summary", "input": {}}]),
        (f"Summary checked. See [event:{seed}].", []),
    ]
    r = await client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "summarize"},
        headers={"X-DeployAI-Actor-Id": str(uid)},
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events = [n for n, _ in frames]
    assert "approval_required" in events, frames
    assert "done" not in events, frames
    approval = next(p for n, p in frames if n == "approval_required")
    assert approval["tool"] == "get_engagement_summary"
    assert approval["question"]
    thread_id = str(approval["thread_id"])
    assert thread_id.startswith(f"tenant:{tid}:engagement:{eid}:conversation:")
    return tid, eid, uid, thread_id, seed


@pytest.mark.asyncio
async def test_approval_pause_ledgers_request_and_no_turn_persists(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    tid, eid, _uid, _thread_id, _seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_requested") == 1
    # The turn is paused, not persisted.
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 0
    assert _count(postgres_engine, "agent_audit_traces", tenant_id=tid, engagement_id=eid) == 0


@pytest.mark.asyncio
async def test_approve_resumes_turn_and_persists_reply(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    tid, eid, uid, thread_id, seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)

    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/{thread_id}?tenant_id={tid}",
        json={"approved": True, "note": "go ahead"},
        headers={"X-DeployAI-Actor-Id": str(uid)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert str(seed) in body["content"]
    assert uuid.UUID(body["turn_id"])
    assert uuid.UUID(body["conversation_id"])

    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_granted") == 1
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_denied") == 0
    # user + oracle turns persisted; the approved tool actually ran.
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 2
    with postgres_engine.connect() as c:
        row = c.execute(
            text("SELECT tool_calls_count, verified_count FROM agent_audit_traces WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).one()
    assert row[0] == 1
    assert row[1] == 1


@pytest.mark.asyncio
async def test_deny_feeds_denial_result_and_still_finishes(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    tid, eid, uid, thread_id, seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)

    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/{thread_id}?tenant_id={tid}",
        json={"approved": False, "note": "not now"},
        headers={"X-DeployAI-Actor-Id": str(uid)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert str(seed) in body["content"]  # the scripted follow-up reply still lands

    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_denied") == 1
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_granted") == 0
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 2
    # The denied tool never executed but the denial consumed a slot.
    with postgres_engine.connect() as c:
        row = c.execute(
            text("SELECT tool_calls_count FROM agent_audit_traces WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).one()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_resume_scope_and_validation_errors(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    tid, eid, uid, thread_id, _seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)
    headers = {"X-DeployAI-Actor-Id": str(uid)}

    # Foreign engagement in the path → thread scope mismatch → 404.
    other_eid = await _new_engagement(a_client, tid)
    r = await a_client.post(
        f"/internal/v1/engagements/{other_eid}/oracle/approvals/{thread_id}?tenant_id={tid}",
        json={"approved": True},
        headers=headers,
    )
    assert r.status_code == 404, r.text

    # Malformed thread id → 400.
    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/not-a-thread?tenant_id={tid}",
        json={"approved": True},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # Well-formed thread id with no pending interrupt → 404.
    ghost = f"tenant:{tid}:engagement:{eid}:conversation:turn-{uuid.uuid4()}"
    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/{ghost}?tenant_id={tid}",
        json={"approved": True},
        headers=headers,
    )
    assert r.status_code == 404, r.text

    # The real one still resumes fine afterwards.
    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/{thread_id}?tenant_id={tid}",
        json={"approved": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
