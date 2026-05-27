"""Integration smoke test for the golden eval runner (Phase 6 Wave A).

One direct-lookup question, driven end-to-end against:

- A real Postgres testcontainer (via the session-scoped ``postgres_engine``).
- A FastAPI app mounted via ``ASGITransport`` — same transport
  ``test_phase3_*`` uses, so the SSE plumbing is exercised in-band.
- A stubbed LLM provider returning a canned, cited answer.
- The BlueState-XL seed fixture, called via the existing
  ``apply_bluestate_xl_scenario`` runner (NO inline re-seed — hard constraint).

Asserts the :class:`QuestionResult` shape + that the runner classifies a
known-good answer as ``expected_pass=True``.
"""

from __future__ import annotations

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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.scenarios.bluestate_xl import (
    ENGAGEMENT_ID as XL_ENGAGEMENT_ID,
)
from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario
from tests.golden.agent_kenny.runner import run_question
from tests.golden.agent_kenny.types import Question, QuestionResult

pytestmark = pytest.mark.integration


# --- Stub LLM (matches the test_phase3_* pattern) -----------------------------


class _StubLLM:
    id = "golden-smoke-stub"

    def __init__(self, reply: str) -> None:
        self._reply = reply
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
        yield self._reply

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, temperature, max_output_tokens
        self.calls += 1
        if self._reply:
            yield StreamChunk(delta=self._reply, done=False, tokens_used=0)
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
        self.calls += 1
        if self._reply:
            yield TextDelta(content=self._reply)
        yield StopReason(reason="end_turn", usage={"input_tokens": 80, "output_tokens": 40})

    def embed(self, text: str) -> list[float]:
        _ = text
        return pseudo_embed("eval", 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


# --- Fixtures -----------------------------------------------------------------


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def golden_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "golden-smoke-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "golden-smoke-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest_asyncio.fixture
async def seeded_xl(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    """Seed BlueState-XL into the test container via the official runner.

    Uses a small ``days=30`` snapshot horizon so the smoke test stays well
    under the integration-suite latency budget. The runner accepts an
    explicit ``tenant_id`` so we can ensure cross-test isolation.
    """
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    engine = create_async_engine(_async_url(postgres_engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    async with session_factory() as session:
        await apply_bluestate_xl_scenario(session, tenant_id=tenant_id, days=30)
        await session.commit()
    await engine.dispose()
    return tenant_id


@pytest.fixture
def stub_llm() -> Iterator[_StubLLM]:
    # The reply cites a node UUID — the runner stream classifier only
    # counts ``citation_verified`` frames, which the Phase 3 citation node
    # emits when the cited UUID exists in this tenant/engagement. Using a
    # bogus UUID still produces an ``citation_unverified`` frame; that's
    # fine for asserting the shape of the QuestionResult (the smoke test
    # is about plumbing, not Kenny's answer quality).
    canned = "Patricia Vance is the executive sponsor for BlueState Health. [node:00000000-0000-4000-8000-000000000abc]"
    stub = _StubLLM(reply=canned)

    def _f() -> _StubLLM:
        return stub

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_actor(engine: Engine, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Ensure the smoke-test actor exists in app_users for the seeded tenant."""
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "u": str(actor_id),
                "t": str(tenant_id),
                "n": "golden-smoke",
                "e": "golden-smoke@example.test",
            },
        )


# --- The smoke test ----------------------------------------------------------


@pytest.mark.asyncio
async def test_golden_smoke_runs_one_direct_lookup_against_seeded_bluestate_xl(
    golden_client: AsyncClient,
    postgres_engine: Engine,
    seeded_xl: uuid.UUID,
    stub_llm: _StubLLM,
) -> None:
    actor = uuid.uuid4()
    _seed_actor(postgres_engine, seeded_xl, actor)

    question = Question(
        id="q-smoke-001",
        category="direct_lookup",
        question="Who is the executive sponsor on the BlueState account?",
        expected_answer_contains=["Patricia Vance"],
        expected_min_citations=1,
        expected_kinds=["node"],
        should_idk=False,
    )

    result = await run_question(
        golden_client,
        question,
        tenant_id=seeded_xl,
        engagement_id=uuid.UUID(XL_ENGAGEMENT_ID),
        actor_user_id=actor,
    )

    # Shape assertions — these are what Wave B/C will read.
    assert isinstance(result, QuestionResult)
    assert result.id == "q-smoke-001"
    assert result.category == "direct_lookup"
    assert result.latency_ms >= 0
    assert result.error is None, result.error
    assert result.final_text  # the stub canned a non-empty reply
    assert "Patricia Vance" in result.final_text
    assert result.expected_pass is True
    assert result.idk is False
    # The stub LLM was actually invoked.
    assert stub_llm.calls >= 1
    # Serialises cleanly so Wave B can dump it to disk.
    payload = result.model_dump_json()
    assert "q-smoke-001" in payload
