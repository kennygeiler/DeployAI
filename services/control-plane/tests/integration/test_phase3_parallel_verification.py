"""Integration test: Phase 3 parallel citation verification ordering (§5.3).

The streaming driver must emit ``citation_verified`` (or its sibling
``_unverified``) frames BEFORE the terminal ``done`` frame. Phase 3 also
runs verification concurrently so a many-citation reply doesn't add a
serial-DB stall to the wall-clock latency budget.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
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
from control_plane.main import app

pytestmark = pytest.mark.integration


class _StubLLM:
    id = "phase3-parallel-stub"

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

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'phase3-parallel') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"phase3-parallel-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "phase3-parallel-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "phase3-parallel-key"
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
async def test_phase3_citation_verified_frames_arrive_before_done(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    r = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Phase3 parallel"},
    )
    assert r.status_code == 201
    eng = uuid.UUID(r.json()["id"])

    # Seed five events so the verifier has five concurrent lookups to issue.
    seeds = [_seed_event(postgres_engine, tenant_id=tid, engagement_id=eng, summary=f"seed-{i}") for i in range(5)]
    body = " ".join(f"Risk [event:{s}]." for s in seeds)
    stub_llm._replies = [body]

    r = await k_client.post(
        f"/internal/v1/engagements/{eng}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "give me risks"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    event_names = [n for n, _ in frames]

    verified_indexes = [i for i, n in enumerate(event_names) if n == "citation_verified"]
    done_index = event_names.index("done")

    # All five citations must verify, and every verify frame must arrive
    # strictly BEFORE the terminal done frame (scope-v2 §5.3 + §6.3).
    assert len(verified_indexes) == 5
    assert all(i < done_index for i in verified_indexes)


@pytest.mark.asyncio
async def test_phase3_unverified_frame_carries_kind_and_uuid(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    r = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Phase3 unverified"},
    )
    assert r.status_code == 201
    eng = uuid.UUID(r.json()["id"])

    bogus = uuid.uuid4()
    # Two replies: the first cites a fabricated UUID (triggers revision);
    # the second still cites the bogus id so the not_found shows up in
    # the final report (revision attempts are limited to two).
    stub_llm._replies = [
        f"Risks include [event:{bogus}].",
        f"Risks include [event:{bogus}].",
        f"Risks include [event:{bogus}].",
    ]

    r = await k_client.post(
        f"/internal/v1/engagements/{eng}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "tell me a story"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    unverified = [p for n, p in frames if n == "citation_unverified"]
    assert unverified, frames
    # The frame payload must carry the offending kind + UUID per the brief.
    assert unverified[-1]["kind"] == "event"
    assert unverified[-1]["id"] == str(bogus)
    assert unverified[-1]["outcome"] == "not_found"
