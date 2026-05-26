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
from llm_provider_py.types import CapabilityMatrix, ChatMessage, StreamChunk
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.domain.llm_budget import DEFAULT_DAILY_CAP
from control_plane.main import app

pytestmark = pytest.mark.integration


class _LLMScript:
    """Stub provider that returns one scripted reply per ``chat_complete_stream`` call."""

    id = "stub-v2"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0
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
        # adversarial_review uses this; default to NONE if scripts run dry.
        return "NONE"

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
        # Emit a single chunk per call for determinism.
        if text_val:
            yield StreamChunk(delta=text_val, done=False, tokens_used=0)
        yield StreamChunk(delta="", done=True, tokens_used=120)

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


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "kenny-v2-test-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "kenny-v2-test-key"
    try:
        yield client
    finally:
        await client.aclose()
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
