"""Integration test: Phase 5 Wave 1C external citation SSE stream (§9.3).

Drives a stubbed LLM reply that mixes one internal ``[event:UUID]``
citation (verified against the seeded ledger) with one external
``[slack:msg-...]`` citation. Asserts:

- SSE frames include ``citation_verified`` for the internal id.
- SSE frames include ``citation_external`` for the slack id.
- The slack id is NOT echoed as ``citation_unverified`` or ``citation_verified``.
- The persisted ledger event for the turn records both citations
  (external_count > 0 and an ``external_citations`` payload).

The ``_StubLLM`` mirrors the Phase 3 pattern (TextDelta + StopReason
"end_turn") so the native tool_use loop in ``llm_call.py`` resolves
without dispatching any tools.
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
    id = "phase5-external-stub"

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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'phase5-external') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"phase5-external-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "phase5-external-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "phase5-external-key"
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
async def test_external_citation_emits_citation_external_alongside_verified_internal(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    r = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Phase5 external"},
    )
    assert r.status_code == 201
    eng = uuid.UUID(r.json()["id"])

    internal_event = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eng,
        summary="customer pinged about deadline",
    )
    slack_ref = "msg-abc-123"
    reply_text = f"Customer raised it on Slack [slack:{slack_ref}], matching ledger event [event:{internal_event}]."
    stub_llm._replies = [reply_text]

    r = await k_client.post(
        f"/internal/v1/engagements/{eng}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "what did the customer say"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    event_names = [n for n, _ in frames]

    # Internal citation produces ``citation_verified``.
    verified = [p for n, p in frames if n == "citation_verified"]
    assert len(verified) == 1, frames
    assert verified[0]["kind"] == "event"
    assert verified[0]["id"] == str(internal_event)

    # External slack citation produces ``citation_external``.
    external = [p for n, p in frames if n == "citation_external"]
    assert len(external) == 1, frames
    assert external[0]["kind"] == "slack"
    assert external[0]["id"] == slack_ref

    # External MUST NOT be echoed as verified or unverified.
    assert not any(p.get("id") == slack_ref for n, p in frames if n == "citation_verified")
    assert not any(p.get("id") == slack_ref for n, p in frames if n == "citation_unverified")

    # Both citation frames must arrive before the terminal ``done``.
    done_idx = event_names.index("done")
    assert event_names.index("citation_verified") < done_idx
    assert event_names.index("citation_external") < done_idx

    # The persisted ledger event captures both citations: external_count=1
    # and a structured ``external_citations`` payload naming the provider.
    with postgres_engine.begin() as c:
        rows = c.execute(
            text(
                "SELECT detail FROM ledger_events "
                "WHERE tenant_id = :t AND engagement_id = :e "
                "AND source_kind = 'oracle_chat_turn' "
                "ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"t": str(tid), "e": str(eng)},
        ).all()
    assert rows, "expected one oracle_chat_turn ledger event for the turn"
    detail = rows[0][0]
    if isinstance(detail, str):
        detail = json.loads(detail)
    assert detail.get("external_count") == 1
    assert detail.get("verified_count") == 1
    external_payload = detail.get("external_citations") or []
    assert len(external_payload) == 1
    assert external_payload[0]["kind"] == "slack"
    assert external_payload[0]["external_kind"] == "slack"
    assert external_payload[0]["id"] == slack_ref
