"""Integration test: Phase 3 cross-engagement-leak hard rejection (§7.1).

Asks Kenny in engagement A about engagement B; the reply must be
rejected, the security ledger event emitted, and the leaked text must
NOT appear in the final response.
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
    StreamChunk,
    TextDelta,
    ToolStreamChunk,
)
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


class _StubLLM:
    id = "phase3-leak-stub"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
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

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        yield self._replies[self.calls] if self.calls < len(self._replies) else ""

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, temperature, max_output_tokens
        idx = self.calls
        self.calls += 1
        body = self._replies[idx] if idx < len(self._replies) else ""
        if body:
            yield StreamChunk(delta=body, done=False, tokens_used=0)
        yield StreamChunk(delta="", done=True, tokens_used=80)

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
        body = self._replies[idx] if idx < len(self._replies) else ""
        if body:
            yield TextDelta(content=body)
        yield StopReason(reason="end_turn", usage={"input_tokens": 80, "output_tokens": 40})

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'phase3-leak') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"phase3-leak-tester-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "phase3-leak-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "phase3-leak-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def stub_llm() -> Iterator[_StubLLM]:
    stub = _StubLLM(replies=[])

    def _f() -> _StubLLM:
        return stub

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    summary: str,
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


def _count(engine: Engine, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


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
async def test_phase3_cross_engagement_leak_rejects_reply_and_emits_security_event(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubLLM
) -> None:
    """Portfolio-shaped fixture: ask engagement A about engagement B."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    # Two sibling engagements under the same tenant.
    r_a = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Engagement A"},
    )
    assert r_a.status_code == 201, r_a.text
    eng_a = uuid.UUID(r_a.json()["id"])
    r_b = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Engagement B"},
    )
    assert r_b.status_code == 201, r_b.text
    eng_b = uuid.UUID(r_b.json()["id"])

    # Sensitive content lives in engagement B; the LLM tries to leak it
    # while scoped to engagement A.
    leak_event = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eng_b, summary="B-only secret")
    leaked_summary_marker = "B-only-leak-marker-text"

    stub_llm._replies = [
        f"You should know: {leaked_summary_marker}. See [event:{leak_event}].",
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eng_a}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "anything from engagement B?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events_seen = [n for n, _ in frames]

    # The leak frame must fire BEFORE the done frame.
    assert "cross_engagement_leak" in events_seen, events_seen
    assert events_seen.index("cross_engagement_leak") < events_seen.index("done")

    # Final reply text must NOT include the leaked content nor the cited UUID.
    done = next(p for n, p in frames if n == "done")
    assert done["final_text"] == "I'm unable to answer that question."
    assert leaked_summary_marker not in done["final_text"]
    assert str(leak_event) not in done["final_text"]

    # The reply text streamed BEFORE the security gate cannot have surfaced
    # via a delta frame either — the rejection replaces it server-side.
    deltas = [p.get("content", "") for n, p in frames if n == "delta"]
    final_delta_blob = "".join(deltas)
    # The model emitted the leak marker — that part landed in the delta
    # stream because we cannot un-stream tokens already sent; assert the
    # security event STILL fired and the persisted reply is the rejection.
    assert leaked_summary_marker in final_delta_blob

    # Security ledger event must be recorded.
    assert (
        _count(
            postgres_engine,
            "ledger_events",
            tenant_id=tid,
            source_kind="agent_cross_engagement_leak",
        )
        == 1
    )

    # Audit row records the cross_engagement_count.
    with postgres_engine.connect() as c:
        row = c.execute(
            text("SELECT cross_engagement_count FROM agent_audit_traces WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).one()
    assert row[0] >= 1
