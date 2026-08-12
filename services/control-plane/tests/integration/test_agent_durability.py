"""Durable-execution chaos proof (Wave 4 showcase, ticket G7-lite).

The claim under test: **the agent survives process death mid-turn.**

With ``DEPLOYAI_AGENT_RUNTIME=langgraph`` a Kenny turn runs on a
checkpointed StateGraph whose every superstep is persisted to Postgres by
the ``AsyncPostgresSaver`` (migration ``20260811_0054_langgraph_checkpoints``).
When a tool call needs human approval, ``interrupt()`` pauses the turn and
the *only* place the half-finished turn lives is that checkpoint row — no
in-memory object is required to finish it. These tests disrupt the world
between the pause and the resume and prove the turn still completes:

- ``test_turn_survives_process_restart_mid_turn`` — after the pause, every
  in-process runtime handle is torn down (checkpointer pool closed, cached
  SQLAlchemy engine disposed and forgotten) and a **brand-new**
  ``KennyAgentService`` — new graph, new checkpointer pool, new DB
  connections — resumes the thread. This is a faithful in-process stand-in
  for a process restart: the resume path shares zero live state with the
  run that paused.
- ``test_turn_survives_connection_drop_between_pause_and_resume`` — same
  flow, but simulating a transient DB outage: the app engine's connection
  pool is disposed and the checkpointer pool is closed (its documented
  re-init path — ``get_checkpointer()`` lazily rebuilds after
  ``close_checkpointer()``). The resume goes through the normal approvals
  HTTP route on fresh connections.

Both tests assert the full completion contract: the resumed turn reports
``done``, the user + oracle turns are persisted, the approved tool actually
ran, and citation verification ran against the resumed reply
(``agent_audit_traces.verified_count``).

Deliberately NOT covered: restarting the Postgres testcontainer itself —
container teardown discards its volume, which would test data loss, not
durability.
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

from control_plane.agents.agent_kenny import KennyAgentService
from control_plane.agents.agent_kenny.checkpointer import close_checkpointer
from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache, get_engine, tenant_session
from control_plane.main import app

pytestmark = pytest.mark.integration


class _ScriptedLLM:
    """Stub provider: each entry is (text, [tool calls]) per LLM call.

    The call counter lives on the stub object, which — like a real LLM
    provider — survives the simulated restart. The *turn state* is what
    must survive via the checkpoint, and that is what these tests verify.
    """

    id = "durability-stub"

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
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "durability-test-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    monkeypatch.setenv("DEPLOYAI_AGENT_RUNTIME", "langgraph")
    # Force an internal tool onto the approval list so interrupt() fires
    # without any external MCP configuration (same harness as the D4
    # approval tests).
    monkeypatch.setenv("DEPLOYAI_AGENT_APPROVAL_TOOLS", "get_engagement_summary")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "durability-test-key"
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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'durability-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {"u": str(uid), "t": str(tid), "n": f"survivor-{uid}", "e": f"{uid}@example.test"},
        )
    return tid, uid


async def _new_engagement(client: AsyncClient, tid: uuid.UUID) -> uuid.UUID:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Durability test"})
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
    thread_id = str(approval["thread_id"])
    return tid, eid, uid, thread_id, seed


def _assert_turn_completed(engine: Engine, *, tid: uuid.UUID, seed: uuid.UUID, content: str) -> None:
    """The full completion contract for a resumed turn.

    - the scripted final reply (with its citation) came back;
    - both the user turn and the oracle turn were persisted;
    - the approved tool actually executed (tool_calls_count == 1);
    - citation verification ran and verified the seeded event
      (verified_count == 1) — the resumed run went through the whole
      extract/verify pipeline, not a shortcut;
    - the approval decision itself was ledgered.
    """
    assert str(seed) in content
    assert _count(engine, "oracle_chat_turns", tenant_id=tid) == 2
    with engine.connect() as c:
        row = c.execute(
            text("SELECT tool_calls_count, verified_count FROM agent_audit_traces WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).one()
    assert row[0] == 1, "the approved tool should have executed exactly once"
    assert row[1] == 1, "citation verification should have run and verified the seeded event"
    assert _count(engine, "ledger_events", tenant_id=tid, source_kind="agent_approval_granted") == 1


@pytest.mark.asyncio
async def test_turn_survives_process_restart_mid_turn(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    """Chaos proof (a): the agent survives process death mid-turn.

    Sequence: pause a turn at interrupt() → tear down every in-process
    runtime handle (checkpointer pool, cached engine) → resume the same
    thread on a **fresh** ``KennyAgentService`` with a fresh engine and a
    fresh checkpointer pool. Only the Postgres checkpoint connects the two
    halves of the turn.
    """
    tid, _eid, uid, thread_id, seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)

    # The paused turn exists ONLY as a Postgres checkpoint: no reply rows
    # yet, but checkpoint rows for the thread are on disk.
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 0
    assert _count(postgres_engine, "checkpoints", thread_id=thread_id) > 0

    # --- simulated process restart -------------------------------------
    # Close the checkpointer's psycopg pool and dispose + forget the cached
    # SQLAlchemy engine. After this, nothing in memory can finish the turn:
    # the next actor must rebuild graph, pools, and connections from
    # scratch — exactly what a restarted process would do.
    await close_checkpointer()
    old_engine = get_engine()
    clear_engine_cache()
    await old_engine.dispose()

    # Fresh service instance: new graph on resume, new checkpointer pool
    # (get_checkpointer() lazily rebuilds), new engine via tenant_session.
    fresh_service = KennyAgentService(stub_llm)
    async with tenant_session(tid) as session:
        outcome = await fresh_service.resume_approval(
            session,
            thread_id=thread_id,
            approved=True,
            note="approved after restart",
            actor_user_id=uid,
        )
        await session.commit()

    assert outcome.status == "done"
    assert outcome.done is not None
    _assert_turn_completed(postgres_engine, tid=tid, seed=seed, content=outcome.done.final_text)


@pytest.mark.asyncio
async def test_turn_survives_connection_drop_between_pause_and_resume(
    a_client: AsyncClient, postgres_engine: Engine, stub_llm: _ScriptedLLM
) -> None:
    """Chaos proof (b): the agent tolerates a transient DB outage mid-turn.

    Sequence: pause a turn at interrupt() → dispose the app engine's
    connection pool and close the checkpointer pool (its documented
    re-init path: ``close_checkpointer()`` then lazy rebuild inside
    ``get_checkpointer()``) → resume through the normal approvals HTTP
    route. Every DB conversation after the drop happens on brand-new
    connections; the turn still completes with citations verified.
    """
    tid, eid, uid, thread_id, seed = await _start_paused_turn(a_client, postgres_engine, stub_llm)

    # --- simulated transient DB outage recovery ------------------------
    # Kill every pooled connection the app holds. The engine object stays
    # cached (the process did NOT restart) — its pool simply has to
    # re-establish connections, which is what recovery from a dropped
    # DB connection looks like. The checkpointer pool has no transparent
    # re-open, so we exercise its documented re-init path.
    await get_engine().dispose()
    await close_checkpointer()

    r = await a_client.post(
        f"/internal/v1/engagements/{eid}/oracle/approvals/{thread_id}?tenant_id={tid}",
        json={"approved": True, "note": "approved after connection drop"},
        headers={"X-DeployAI-Actor-Id": str(uid)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    _assert_turn_completed(postgres_engine, tid=tid, seed=seed, content=body["content"])
