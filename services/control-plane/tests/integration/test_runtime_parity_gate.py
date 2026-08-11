"""Pilot-refresh D6 — legacy vs LangGraph runtime parity gate.

Runs a representative golden subset (8 questions from
``tests/golden/agent_kenny/questions.yaml``: 4 direct lookups, 2 negative,
2 cross-engagement) against BOTH runtimes with the stub provider and the
seeded BlueState-XL scenario, and asserts the cutover conditions from the
backlog ticket:

- citation-verification behaviour equal-or-better on LangGraph
  (verified >= legacy, unverified <= legacy, per question);
- shipped cross-engagement leak count is zero on both runtimes (every
  leaking reply is replaced with the rejection text);
- the tool-call cap is respected on both runtimes;
- overall pass count on LangGraph >= legacy.

This module gates the future deletion of the hand-rolled driver — the
legacy driver stays until this gate has soaked (deletion is explicitly
out of scope for Wave 2).
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

from control_plane.agents.agent_kenny.checkpointer import close_checkpointer
from control_plane.agents.agent_kenny.types import MAX_TOOL_CALLS_PER_TURN
from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.scenarios.bluestate_xl import ENGAGEMENT_ID as XL_ENGAGEMENT_ID
from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario
from tests.golden.agent_kenny.runner import load_questions, run_question
from tests.golden.agent_kenny.types import Question, QuestionResult

pytestmark = pytest.mark.integration

_SECURITY_REJECT_REPLY = "I'm unable to answer that question."

# Representative subset: 4 direct lookups + 2 negative + 2 cross-engagement.
_SUBSET_IDS: tuple[str, ...] = (
    "q-001",
    "q-003",
    "q-004",
    "q-006",
    "q-017",
    "q-018",
    "q-023",
    "q-024",
)

_IDK_REPLY = "I don't know — no matching records in this engagement's data."


class _ScriptedLLM:
    """One canned reply per LLM tools-stream call, in order."""

    id = "parity-gate-stub"

    def __init__(self) -> None:
        self.replies: list[str] = []
        self.calls = 0

    def reset(self, replies: list[str]) -> None:
        self.replies = list(replies)
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

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, temperature, max_output_tokens
        yield StreamChunk(delta="", done=True, tokens_used=0)  # pragma: no cover

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
        body = self.replies[idx] if idx < len(self.replies) else _IDK_REPLY
        if body:
            yield TextDelta(content=body)
        yield StopReason(reason="end_turn", usage={"input_tokens": 80, "output_tokens": 40})

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def parity_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "parity-gate-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "parity-gate-key"
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


@pytest_asyncio.fixture
async def seeded_xl(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> uuid.UUID:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    engine = create_async_engine(_async_url(postgres_engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    async with session_factory() as session:
        await apply_bluestate_xl_scenario(session, tenant_id=tenant_id, days=30)
        await session.commit()
    await engine.dispose()
    return tenant_id


def _seed_actor(engine: Engine, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, 'parity-gate', 'parity@example.test') ON CONFLICT (id) DO NOTHING"
            ),
            {"u": str(actor_id), "t": str(tenant_id)},
        )


def _raise_daily_budget(engine: Engine, tenant_id: uuid.UUID) -> None:
    """16 stub turns x 4000-token pre-charge outruns the default daily cap."""
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tenant_llm_daily_budget (tenant_id, usage_date, tokens_used, daily_cap) "
                "VALUES (:t, CURRENT_DATE, 0, 10000000) "
                "ON CONFLICT (tenant_id, usage_date) DO UPDATE SET daily_cap = 10000000"
            ),
            {"t": str(tenant_id)},
        )


def _node_id(engine: Engine, tenant_id: uuid.UUID, engagement_id: uuid.UUID, *, title_like: str) -> uuid.UUID:
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT id FROM matrix_nodes WHERE tenant_id = :t AND engagement_id = :e "
                "AND title ILIKE :q ORDER BY id LIMIT 1"
            ),
            {"t": str(tenant_id), "e": str(engagement_id), "q": f"%{title_like}%"},
        ).one_or_none()
    assert row is not None, f"seeded BlueState-XL node matching {title_like!r} not found"
    return uuid.UUID(str(row[0]))


def _foreign_event(engine: Engine, tenant_id: uuid.UUID, *, engagement_id: uuid.UUID) -> uuid.UUID:
    """A ledger event in a different engagement — the leak target."""
    ev = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary, detail) "
                "VALUES (:id, :t, :e, now(), 'user', 'manual_capture', 'foreign engagement fact', '{}'::jsonb)"
            ),
            {"id": str(ev), "t": str(tenant_id), "e": str(engagement_id)},
        )
    return ev


def _scripted_replies(questions: list[Question], reply_by_id: dict[str, str]) -> list[str]:
    return [reply_by_id[q.id] for q in questions]


async def _run_subset(
    client: AsyncClient,
    questions: list[Question],
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict[str, QuestionResult]:
    out: dict[str, QuestionResult] = {}
    for q in questions:
        out[q.id] = await run_question(
            client,
            q,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_user_id=actor_id,
        )
    return out


@pytest.mark.asyncio
async def test_parity_gate_langgraph_equal_or_better_than_legacy(
    parity_client: AsyncClient,
    postgres_engine: Engine,
    seeded_xl: uuid.UUID,
    stub_llm: _ScriptedLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = seeded_xl
    engagement_id = uuid.UUID(XL_ENGAGEMENT_ID)
    actor_id = uuid.uuid4()
    _seed_actor(postgres_engine, tenant_id, actor_id)
    _raise_daily_budget(postgres_engine, tenant_id)

    questions = [q for q in load_questions() if q.id in _SUBSET_IDS]
    assert len(questions) == len(_SUBSET_IDS)
    by_category = {q.id: q.category for q in questions}
    assert sum(1 for c in by_category.values() if c == "negative") == 2
    assert sum(1 for c in by_category.values() if c == "cross_engagement") == 2

    # Grounded citations from the deterministic seed for the direct lookups.
    sponsor = _node_id(postgres_engine, tenant_id, engagement_id, title_like="Patricia Vance")
    strategist = _node_id(postgres_engine, tenant_id, engagement_id, title_like="Sarah Chen")
    security = _node_id(postgres_engine, tenant_id, engagement_id, title_like="David Liu")

    # A second engagement's event — the cross-engagement leak target.
    r = await parity_client.post(
        f"/internal/v1/engagements?tenant_id={tenant_id}", json={"name": "Parity foreign engagement"}
    )
    assert r.status_code == 201, r.text
    foreign_eng = uuid.UUID(r.json()["id"])
    leak_event = _foreign_event(postgres_engine, tenant_id, engagement_id=foreign_eng)

    # Replies are one-per-turn in question order; every DB citation is
    # verifiable so no revision loop consumes extra scripted replies
    # (revision parity is separately enforced by the parametrized
    # test_v2_revision_replaces_bad_citation_with_valid).
    reply_by_id: dict[str, str] = {
        # The account fact is grounded on the sponsor stakeholder node —
        # the seed has no standalone account node; the classifier needs the
        # substring plus at least one verified citation.
        "q-001": f"The customer account is BlueState Health [node:{sponsor}].",
        "q-003": f"Patricia Vance is the executive sponsor [node:{sponsor}].",
        "q-004": f"Sarah Chen is the deployment strategist of record [node:{strategist}].",
        "q-006": f"David Liu holds the VP IT Security role [node:{security}].",
        "q-017": _IDK_REPLY,
        "q-018": _IDK_REPLY,
        # Leaking replies: cite another engagement's event — the security
        # gate must strip these on BOTH runtimes.
        "q-023": f"Acme Bank decided to roll out MFA in Q2 [event:{leak_event}].",
        "q-024": f"Globex risks include churn [event:{leak_event}].",
    }

    results: dict[str, dict[str, QuestionResult]] = {}
    for runtime in ("legacy", "langgraph"):
        monkeypatch.setenv("DEPLOYAI_AGENT_RUNTIME", runtime)
        stub_llm.reset(_scripted_replies(questions, reply_by_id))
        results[runtime] = await _run_subset(
            parity_client,
            questions,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_id=actor_id,
        )

    legacy, langgraph = results["legacy"], results["langgraph"]

    shipped_leaks = 0
    for q in questions:
        old, new = legacy[q.id], langgraph[q.id]
        assert old.error is None, f"{q.id} legacy error: {old.error}"
        assert new.error is None, f"{q.id} langgraph error: {new.error}"

        # Ticket gate 1: citation verification equal-or-better.
        assert new.citations_verified >= old.citations_verified, q.id
        assert new.citations_unverified <= old.citations_unverified, q.id

        # Ticket gate 2: tool-call cap respected on both runtimes.
        assert old.tool_calls <= MAX_TOOL_CALLS_PER_TURN, q.id
        assert new.tool_calls <= MAX_TOOL_CALLS_PER_TURN, q.id

        # Ticket gate 3: zero shipped leaks. A caught leak replaces the
        # reply with the rejection text; anything else that still cites
        # the foreign event id counts as shipped.
        for result in (old, new):
            if str(leak_event) in result.final_text:
                shipped_leaks += 1
        if q.category == "cross_engagement":
            assert old.cross_engagement_leak and old.final_text == _SECURITY_REJECT_REPLY, q.id
            assert new.cross_engagement_leak and new.final_text == _SECURITY_REJECT_REPLY, q.id

        # Stronger-than-ticket sanity: identical canned input should
        # classify identically across runtimes.
        assert new.idk == old.idk, q.id
        assert new.expected_pass == old.expected_pass, q.id

    assert shipped_leaks == 0

    # Ticket gate 4: aggregate pass count equal-or-better.
    old_passes = sum(1 for r in legacy.values() if r.expected_pass)
    new_passes = sum(1 for r in langgraph.values() if r.expected_pass)
    assert new_passes >= old_passes
    # And the canned subset should actually pass on both drivers.
    assert old_passes == len(questions)
    assert new_passes == len(questions)
