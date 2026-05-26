"""Mr. Oracle chat SSE streaming endpoint — integration tests (Phase G1.b)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

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


_STREAM_WORDS = ("Two ", "open ", "risks ", "remain.")


class _StubStreamLLM:
    id = "stub-stream"

    def __init__(self) -> None:
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
        return "".join(_STREAM_WORDS)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        for w in _STREAM_WORDS:
            yield w

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = temperature, max_output_tokens
        self.calls += 1
        self.last_messages = messages
        for w in _STREAM_WORDS:
            yield StreamChunk(delta=w, done=False, tokens_used=0)
        yield StreamChunk(delta="", done=True, tokens_used=123)

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'oracle-stream-test') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"oracle-stream-tester-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture
async def o_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "oracle-stream-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "oracle-stream-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def stub_llm() -> Iterator[_StubStreamLLM]:
    stub = _StubStreamLLM()
    app.dependency_overrides[get_llm_provider] = lambda: stub
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(client: AsyncClient, engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    _ins_tenant(engine, tid)
    user_id = uuid.uuid4()
    _ins_user(engine, tid, user_id)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Oracle stream test"})
    assert r.status_code == 201, r.text
    return tid, uuid.UUID(r.json()["id"]), user_id


def _count(engine: Engine, table: str, **filters: object) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


def _actor_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"X-DeployAI-Actor-Id": str(user_id)}


def _parse_sse_frames(payload: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for block in payload.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: "):
            continue
        data = block[len("data: ") :]
        frames.append(json.loads(data))
    return frames


@pytest.mark.asyncio
async def test_stream_returns_sse_with_deltas_and_done(
    o_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubStreamLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)

    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream?tenant_id={tid}",
        json={"conversation_id": None, "message": "Where are the risks?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream"), r.headers

    frames = _parse_sse_frames(r.text)
    deltas = [f for f in frames if f.get("done") is False]
    dones = [f for f in frames if f.get("done") is True]

    assert len(deltas) >= 1, frames
    assert len(dones) == 1, frames
    done = dones[0]
    assert "error" not in done
    assert "turn_id" in done and uuid.UUID(str(done["turn_id"]))
    assert "conversation_id" in done and uuid.UUID(str(done["conversation_id"]))
    assert isinstance(done.get("tokens_used"), int)
    assert int(done["tokens_used"]) > 0  # type: ignore[arg-type]

    combined = "".join(str(f.get("delta", "")) for f in deltas)
    assert combined.strip() == "Two open risks remain."

    # Persistence matches the JSON route: two turns + oracle ledger event.
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 2
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="oracle_chat_turn") == 1
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="oracle_conversation_started") == 1
    assert _count(postgres_engine, "oracle_conversations", tenant_id=tid, engagement_id=eid) == 1
    assert stub_llm.calls == 1


@pytest.mark.asyncio
async def test_stream_budget_exhausted_returns_429_before_any_frame(
    o_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubStreamLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)
    today = datetime.now(UTC).date()
    with postgres_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tenant_llm_daily_budget (tenant_id, usage_date, tokens_used, daily_cap) "
                "VALUES (:t, :d, :u, :c)"
            ),
            {"t": str(tid), "d": today, "u": DEFAULT_DAILY_CAP, "c": DEFAULT_DAILY_CAP},
        )

    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream?tenant_id={tid}",
        json={"conversation_id": None, "message": "hi"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "daily LLM budget exhausted"
    assert "retry_after_iso" in detail
    assert stub_llm.calls == 0
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 0


@pytest.mark.asyncio
async def test_stream_missing_conversation_returns_404(
    o_client: AsyncClient, postgres_engine: Engine, stub_llm: _StubStreamLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)
    bogus = uuid.uuid4()
    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream?tenant_id={tid}",
        json={"conversation_id": str(bogus), "message": "hi"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 404, r.text
    assert stub_llm.calls == 0


@pytest.mark.asyncio
async def test_stream_missing_internal_key_returns_401(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, stub_llm: _StubStreamLLM
) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "oracle-stream-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        eid = uuid.uuid4()
        tid = uuid.uuid4()
        r = await client.post(
            f"/internal/v1/engagements/{eid}/oracle/chat/stream?tenant_id={tid}",
            json={"conversation_id": None, "message": "hi"},
            headers={"X-DeployAI-Actor-Id": str(uuid.uuid4())},
        )
        assert r.status_code == 401, r.text
    clear_engine_cache()
