"""Integration tests for Agent Kenny v2 (scope-v2 §6).

Stub-LLM driven. Each test installs an ``_LLMScript`` that hands the
graph a deterministic reply sequence, then asserts the persisted state
(turns, audit row, ledger events) matches the expected shape.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import (
    CapabilityMatrix,
    ChatMessage,
    StopReason,
    StreamChunk,
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
from control_plane.domain.llm_budget import DEFAULT_DAILY_CAP
from control_plane.main import app

pytestmark = pytest.mark.integration


_TOOL_CALL_SCRIPT_RE = __import__("re").compile(
    r"<tool_call>(.*?)</tool_call>",
    __import__("re").DOTALL,
)


def _split_reply_for_tool_use(reply: str) -> tuple[str, list[dict[str, Any]]]:
    """Split a legacy scripted reply into (visible_text, tool_use_blocks).

    Existing tests build replies as plain text with embedded
    ``<tool_call>{json}</tool_call>`` segments. We parse them out here so
    the stub can emit them as native ``tool_use`` blocks via the new
    protocol — keeping the script interface stable while the underlying
    transport flips to native tool_use.
    """
    blocks: list[dict[str, Any]] = []
    for idx, m in enumerate(_TOOL_CALL_SCRIPT_RE.finditer(reply)):
        body = m.group(1).strip()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        if not isinstance(name, str):
            continue
        input_obj = payload.get("input", {})
        if not isinstance(input_obj, dict):
            input_obj = {}
        blocks.append({"id": f"toolu_script_{idx}", "name": name, "input": input_obj})
    text_remaining = _TOOL_CALL_SCRIPT_RE.sub("", reply).strip()
    return text_remaining, blocks


class _LLMScript:
    """Stub provider that returns one scripted reply per LLM call.

    The ``_replies`` script remains expressed as text with embedded
    ``<tool_call>{json}</tool_call>`` segments for ergonomic test
    authoring; this stub translates each call into the native tool_use
    chunk sequence the Phase 2 follow-up llm_call node now consumes.
    """

    id = "stub-v2"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0
        self.last_messages: list[ChatMessage] | None = None
        # Per-call capture of the message history sent to the tools endpoint,
        # so tests can assert every tool_use id was answered (Anthropic 400s
        # on dangling ids — the prod tool-cap incident).
        self.tools_messages: list[list[ChatMessage]] = []

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        # adversarial_review uses this; default to NONE if scripts run dry.
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
        text_val = self._replies[self.calls] if self.calls < len(self._replies) else ""
        yield text_val

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        idx = self.calls
        self.calls += 1
        text_val = self._replies[idx] if idx < len(self._replies) else ""
        if text_val:
            yield StreamChunk(delta=text_val, done=False, tokens_used=0)
        yield StreamChunk(delta="", done=True, tokens_used=120)

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = tools, temperature, max_output_tokens
        self.last_messages = messages
        self.tools_messages.append(messages)
        idx = self.calls
        self.calls += 1
        reply = self._replies[idx] if idx < len(self._replies) else ""
        text_val, tool_blocks = _split_reply_for_tool_use(reply)
        if text_val:
            yield TextDelta(content=text_val)
        for block in tool_blocks:
            yield ToolUseStart(id=block["id"], name=block["name"])
            yield ToolUseEnd(id=block["id"], name=block["name"], input=block["input"])
        yield StopReason(
            reason="tool_use" if tool_blocks else "end_turn",
            usage={"input_tokens": 80, "output_tokens": 40},
        )

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'kenny-v2-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "u": str(user_id),
                "t": str(tenant_id),
                "n": f"kenny-v2-tester-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture(params=["legacy", "langgraph"])
async def k_client(
    request: pytest.FixtureRequest, postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """One client per runtime — every test in this module runs against both
    the legacy driver and the LangGraph runtime (pilot-refresh D3 parity)."""
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "kenny-v2-test-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    monkeypatch.setenv("DEPLOYAI_AGENT_RUNTIME", str(request.param))
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "kenny-v2-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        await close_checkpointer()
        clear_engine_cache()


@pytest.fixture
def stub_llm() -> Iterator[_LLMScript]:
    stub = _LLMScript(replies=[])

    def _f() -> _LLMScript:
        return stub

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(client: AsyncClient, engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    _ins_tenant(engine, tid)
    user_id = uuid.uuid4()
    _ins_user(engine, tid, user_id)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Kenny v2 test"})
    assert r.status_code == 201, r.text
    return tid, uuid.UUID(r.json()["id"]), user_id


def _count(engine: Engine, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    summary: str = "seed event",
) -> uuid.UUID:
    ev = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary, detail) "
                "VALUES (:id, :t, :e, now(), 'user', 'manual_capture', :s, '{}'::jsonb)"
            ),
            {"id": str(ev), "t": str(tenant_id), "e": str(engagement_id), "s": summary},
        )
    return ev


def _actor_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"X-DeployAI-Actor-Id": str(user_id)}


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


@pytest.mark.asyncio
async def test_v2_stream_happy_path_persists_turn_and_audit_trace(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    seed = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, summary="risk surfaced")

    # 1st LLM call: tool call. 2nd: final reply citing the seeded event.
    stub_llm._replies = [
        '<tool_call>{"name": "get_engagement_summary", "input": {}}</tool_call>',
        f"Two open risks remain. See [event:{seed}].",
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "what's the state?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events = [name for name, _ in frames]
    assert "tool_call" in events, frames
    assert "tool_result" in events, frames
    assert "citation_verified" in events, frames
    assert "done" in events, frames
    done_payload = next(p for name, p in frames if name == "done")
    assert uuid.UUID(str(done_payload["turn_id"]))
    assert done_payload["tool_calls"] >= 1

    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 2
    assert _count(postgres_engine, "agent_audit_traces", tenant_id=tid, engagement_id=eid) == 1


@pytest.mark.asyncio
async def test_v2_stream_route_is_404_when_flag_off(
    postgres_engine: Engine,
    stub_llm: _LLMScript,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "kenny-v2-flag-off-key")
    monkeypatch.delenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", raising=False)
    clear_engine_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["X-DeployAI-Internal-Key"] = "kenny-v2-flag-off-key"
        tid, eid, user_id = await _new_engagement(client, postgres_engine)
        r = await client.post(
            f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
            json={"conversation_id": None, "message": "hi"},
            headers=_actor_headers(user_id),
        )
        assert r.status_code == 404, r.text
    clear_engine_cache()


@pytest.mark.asyncio
async def test_v2_stream_budget_exhausted_returns_429(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    today = datetime.now(UTC).date()
    with postgres_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tenant_llm_daily_budget (tenant_id, usage_date, tokens_used, daily_cap) "
                "VALUES (:t, :d, :u, :c)"
            ),
            {"t": str(tid), "d": today, "u": DEFAULT_DAILY_CAP, "c": DEFAULT_DAILY_CAP},
        )

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "hi"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "daily LLM budget exhausted"
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 0
    assert _count(postgres_engine, "agent_audit_traces", tenant_id=tid) == 0
    assert stub_llm.calls == 0


@pytest.mark.asyncio
async def test_v2_tool_call_cap_terminates_at_eight(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    # Every reply asks for another tool call → forces the cap.
    forever_tool = '<tool_call>{"name": "get_engagement_summary", "input": {}}</tool_call>'
    stub_llm._replies = [forever_tool] * 20

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "loop forever?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    done = next(p for name, p in frames if name == "done")
    assert done["tool_calls"] == 8


def _assert_every_tool_use_answered(msgs: list[ChatMessage]) -> None:
    """Mimic the Anthropic Messages API validation that 400'd in production:
    every assistant ``tool_use`` id must be answered by a ``tool_result``
    block in the immediately following user message."""
    for i, msg in enumerate(msgs):
        content = msg.get("content")
        if msg.get("role") != "assistant" or not isinstance(content, list):
            continue
        ids = [b["id"] for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not ids:
            continue
        assert i + 1 < len(msgs), f"dangling tool_use ids {ids} at end of history"
        nxt = msgs[i + 1]
        nxt_content = nxt.get("content")
        assert nxt.get("role") == "user" and isinstance(nxt_content, list), (
            f"tool_use ids {ids} not followed by a tool_result user message"
        )
        answered = {b.get("tool_use_id") for b in nxt_content if isinstance(b, dict) and b.get("type") == "tool_result"}
        assert answered == set(ids), f"unanswered tool_use ids: {set(ids) - answered}"


@pytest.mark.asyncio
async def test_v2_cap_truncated_tool_batch_answers_every_tool_use_id(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    """Prod repro (2026-08-11): ONE assistant turn requests 10 tool calls,
    the cap executes only 8 — the follow-up LLM call previously failed with
    Anthropic 400 on dangling tool_use ids and an error frame killed the
    turn. The fix synthesizes is_error tool_results for the truncated tail."""
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    seed = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, summary="cap seed")
    one_call = '<tool_call>{"name": "get_engagement_summary", "input": {}}</tool_call>'
    final_reply = f"All caught up — nothing further to check [event:{seed}]."
    stub_llm._replies = [
        one_call * 10,  # 10 tool_use blocks in a single assistant turn (cap is 8)
        final_reply,
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "check everything"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events = [name for name, _ in frames]
    # (a) no malformed-history explosion: the turn ends in done, not error.
    assert "error" not in events, frames
    done = next(p for name, p in frames if name == "done")
    # (c) the turn completed with the scripted final text.
    assert done["final_text"] == final_reply
    assert done["tool_calls"] == 8
    # Every requested call got a result frame: 8 executed + 2 synthesized.
    assert events.count("tool_call") == 10
    assert events.count("tool_result") == 10
    cap_errors = [p for name, p in frames if name == "tool_result" and p.get("error") == "tool_call_cap_reached"]
    assert len(cap_errors) == 2

    # (b) the follow-up LLM request answered all 10 tool_use ids.
    assert stub_llm.calls >= 2
    follow_up = stub_llm.tools_messages[1]
    assistant = next(m for m in follow_up if m["role"] == "assistant" and isinstance(m["content"], list))
    requested = [b["id"] for b in assistant["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
    assert len(requested) == 10
    for sent in stub_llm.tools_messages:
        _assert_every_tool_use_answered(sent)


@pytest.mark.asyncio
async def test_v2_cross_engagement_leak_rejects_reply(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    tid, eng_a, user_id = await _new_engagement(k_client, postgres_engine)
    # Second engagement in the same tenant — the "leaked" target.
    r2 = await k_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Engagement B"})
    assert r2.status_code == 201, r2.text
    eng_b = uuid.UUID(r2.json()["id"])
    leak_event = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eng_b, summary="leak target")

    stub_llm._replies = [
        f"Risks include this one [event:{leak_event}]."  # cites a B event while scoped to A
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eng_a}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "anything from engagement B?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    done = next(p for name, p in frames if name == "done")
    assert done["final_text"] == "I'm unable to answer that question."
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_cross_engagement_leak") == 1


@pytest.mark.asyncio
async def test_v2_revision_replaces_bad_citation_with_valid(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    good = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, summary="real")
    bogus = uuid.uuid4()

    stub_llm._replies = [
        # initial reply with a bad citation
        f"Look at [event:{bogus}].",
        # revised reply replacing the bad id
        f"Look at [event:{good}].",
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "revise me"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    done = next(p for name, p in frames if name == "done")
    assert done["revision_attempts"] == 1
    assert str(good) in done["final_text"]
    # Audit row should reflect verified > 0 and unverified == 0.
    with postgres_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT verified_count, unverified_count, revision_attempts "
                "FROM agent_audit_traces WHERE tenant_id = :t"
            ),
            {"t": str(tid)},
        ).one()
    assert row[0] >= 1
    assert row[1] == 0
    assert row[2] == 1


@pytest.mark.asyncio
async def test_v2_zero_citation_reply_triggers_revision(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    """GAP 1 (2026-08-11): an uncited factual reply after an evidence-bearing
    tool call must be revised once into a cited reply, on BOTH runtimes
    (the ``k_client`` fixture is parametrized legacy + langgraph)."""
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    seed = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, summary="risk surfaced")

    stub_llm._replies = [
        # 1st call: gather evidence.
        '<tool_call>{"name": "get_engagement_summary", "input": {}}</tool_call>',
        # 2nd call: factual reply with ZERO citation markers (the live failure mode).
        "Two open risks remain and the cutover slipped a sprint.",
        # 3rd call (the revision): same claims, now cited.
        f"Two open risks remain and the cutover slipped a sprint [event:{seed}].",
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "what's the state?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events = [name for name, _ in frames]
    assert "error" not in events, frames
    # The revision fired exactly once and the final reply carries the citation.
    done = next(p for name, p in frames if name == "done")
    assert done["revision_attempts"] == 1
    assert str(seed) in done["final_text"]
    # The verified-citation frame streamed (this is the "receipts" moment).
    verified = [p for name, p in frames if name == "citation_verified"]
    assert {"kind": "event", "id": str(seed)} in verified, frames
    # The corrective rewrite instruction reached the model on the 3rd call.
    assert stub_llm.calls == 3
    revision_call = stub_llm.tools_messages[2]
    assert any(
        isinstance(m.get("content"), str) and "without any [kind:UUID] citation markers" in m["content"]
        for m in revision_call
    ), revision_call


@pytest.mark.asyncio
async def test_v2_refusal_without_citations_is_not_revised(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _LLMScript
) -> None:
    """Negative control: a decline after tool calls ships as-is — no forced
    citation revision, no fabricated markers."""
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)
    _seed_event(postgres_engine, tenant_id=tid, engagement_id=eid, summary="unrelated event")

    refusal = "I don't know — there is no relevant data about that vendor in this engagement."
    stub_llm._replies = [
        '<tool_call>{"name": "get_engagement_summary", "input": {}}</tool_call>',
        refusal,
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "what did the vendor promise?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    done = next(p for name, p in frames if name == "done")
    assert done["revision_attempts"] == 0
    assert done["final_text"] == refusal
    assert stub_llm.calls == 2
