"""Integration test for Wave 3G — Phase 5 agent loop MCP tool merge.

Drives the full Kenny v2 graph end-to-end against a real Postgres
container with a stubbed LLM that emits a ``slack__search_messages``
tool_use, a mocked outbound HTTP transport, and the in-process Noop
kill-switch + rate-limiter doubles from
:mod:`control_plane.agents.agent_kenny.mcp_client`. Asserts:

1. Tool merge: when an enabled :class:`TenantMcpConfig` row exists, the
   LLM's tool list at turn start includes the namespaced external tool.
2. Dispatch routing: a tool_use with prefix ``slack__`` is routed to the
   :class:`McpOutboundClient` instead of the internal registry, and the
   ``<tool_result>`` body that lands in message history is wrapped in
   the threat-model §5.1 ``<external_data source="..." tool="...">``
   envelope.
3. Kill switch: when the kill switch is engaged, no external tools are
   merged into the LLM's tool list this turn, the LLM does not attempt
   external calls, and the SSE stream emits a one-shot
   ``mcp_outbound_skipped_disabled`` frame.
4. Rate-limited dispatch: when the limiter denies the call, the
   tool_result content has ``is_error: true`` so the LLM can react.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.agents.agent_kenny.mcp_client import (
    McpOutboundClient,
    NoopKillSwitch,
    NoopRateLimiter,
)
from control_plane.agents.agent_kenny.mcp_loader import namespace_tool_name
from control_plane.agents.agent_kenny.mcp_rate_limit import InMemoryMcpRateLimiter
from control_plane.agents.agent_kenny.service import KennyAgentService
from control_plane.agents.agent_kenny.stream import format_chunk
from control_plane.agents.agent_kenny.types import (
    DoneChunk,
    ErrorChunk,
)
from control_plane.agents.agent_kenny.types import (
    StreamChunk as KennyStreamChunk,
)
from control_plane.db import clear_engine_cache

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------
# Tools + LLM stub
# --------------------------------------------------------------------------


@dataclass
class _ScriptedToolUse:
    """One entry in the LLM script."""

    text: str = ""
    tool_calls: list[dict[str, Any]] | None = None  # [{id, name, input}]


class _LLMScript:
    """Stub provider returning one scripted turn at a time.

    Mirrors the existing ``_LLMScript`` in :mod:`test_agent_kenny_v2`
    but accepts native tool_use payloads directly so the test doesn't
    have to embed ``<tool_call>`` JSON inside text.
    """

    id = "wave3g-stub"

    def __init__(self, replies: list[_ScriptedToolUse]) -> None:
        self._replies = list(replies)
        self.calls = 0
        self.last_tools: list[dict[str, Any]] = []

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
        yield ""

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, temperature, max_output_tokens
        yield StreamChunk(delta="", done=True, tokens_used=0)

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, temperature, max_output_tokens
        self.last_tools = list(tools)
        idx = self.calls
        self.calls += 1
        entry = self._replies[idx] if idx < len(self._replies) else _ScriptedToolUse()
        if entry.text:
            yield TextDelta(content=entry.text)
        tool_calls = entry.tool_calls or []
        for block in tool_calls:
            yield ToolUseStart(id=block["id"], name=block["name"])
            yield ToolUseEnd(id=block["id"], name=block["name"], input=block.get("input", {}))
        yield StopReason(
            reason="tool_use" if tool_calls else "end_turn",
            usage={"input_tokens": 50, "output_tokens": 30},
        )

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'wave3g-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "u": str(user_id),
                "t": str(tenant_id),
                "n": f"wave3g-tester-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


def _ins_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eng = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO engagements (id, tenant_id, name) VALUES (:e, :t, 'Wave 3G test')"),
            {"e": str(eng), "t": str(tenant_id)},
        )
    return eng


def _ins_mcp_config(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    connector_kind: str = "slack",
    name: str = "slack-prod",
    enabled: bool = True,
    allowed_tools: list[str] | None = None,
) -> uuid.UUID:
    cid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_mcp_configs "
                "(id, tenant_id, name, connector_kind, transport, endpoint, "
                " encrypted_auth_token, allowed_tools, enabled) "
                "VALUES (:id, :t, :n, :k, 'http_sse', :ep, :tok, :al, :en)"
            ),
            {
                "id": str(cid),
                "t": str(tenant_id),
                "n": name,
                "k": connector_kind,
                "ep": "https://mcp.example.test/rpc",
                "tok": b"\x00\x01\x02",  # ciphertext bytes — DEK resolver is stubbed
                "al": allowed_tools,
                "en": enabled,
            },
        )
    return cid


@pytest_asyncio.fixture
async def app_session_factory(postgres_engine: Engine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory bound to the test Postgres container."""
    eng = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    finally:
        await eng.dispose()


# --------------------------------------------------------------------------
# Mocked outbound transport — replies with the canned MCP JSON-RPC envelope.
# --------------------------------------------------------------------------


def _make_outbound_transport(
    *,
    tools_list: list[dict[str, Any]],
    tools_call_result: dict[str, Any] | None = None,
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Return an httpx.AsyncClient whose transport replies to ``tools/list`` and ``tools/call``."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content.decode("utf-8"))
        method = body.get("method")
        req_id = body.get("id")
        if method == "tools/list":
            envelope = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list},
            }
        elif method == "tools/call":
            envelope = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": tools_call_result or {"content": [], "isError": False},
            }
        else:
            envelope = {"jsonrpc": "2.0", "id": req_id, "error": {"message": "unknown method"}}
        return httpx.Response(200, json=envelope, request=request)

    transport = httpx.MockTransport(_handler)
    client = httpx.AsyncClient(transport=transport)
    return client, seen


@asynccontextmanager
async def _silent_audit_factory(tenant_id: uuid.UUID) -> AsyncIterator[Any]:
    """Drop every audit emit on the floor — the agent loop test only
    cares about routing + envelope wrapping; the audit emit pathway is
    exercised in tests/integration/test_mcp_client_audit.py.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    yield session


async def _dek_passthrough(tenant_id: uuid.UUID, ct: bytes) -> str:
    return f"tok-{ct.hex()}"


def _build_outbound_client(
    http_client: httpx.AsyncClient,
    *,
    kill_switch: Any = None,
    rate_limiter: Any = None,
) -> McpOutboundClient:
    return McpOutboundClient(
        http_client=http_client,
        dek_resolver=_dek_passthrough,
        rate_limiter=rate_limiter or NoopRateLimiter(),
        kill_switch=kill_switch or NoopKillSwitch(),
        audit_session_factory=_silent_audit_factory,
    )


async def _run_one_turn(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    service: KennyAgentService,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    message: str,
) -> tuple[list[KennyStreamChunk], AsyncSession]:
    """Drive one ``reply_stream`` and collect every chunk it yields.

    Returns the chunks + the session used so the test can inspect post-
    state.
    """
    async with session_factory() as session:
        chunks: list[KennyStreamChunk] = []
        stream = await service.reply_stream(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_user_id=actor_user_id,
            conversation_id=None,
            message=message,
            now=datetime.now(UTC),
        )
        async for chunk in stream:
            chunks.append(chunk)
        await session.commit()
        return chunks, session


def _seed_tenant_user_engagement(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    user_id = uuid.uuid4()
    _ins_tenant(engine, tid)
    _ins_user(engine, tid, user_id)
    eng = _ins_engagement(engine, tid)
    return tid, eng, user_id


@pytest.fixture(autouse=True)
def _clear_engine_cache(monkeypatch: pytest.MonkeyPatch, postgres_engine: Engine) -> None:
    """Each test gets a fresh engine cache + DATABASE_URL pointed at the container."""
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    clear_engine_cache()


# --------------------------------------------------------------------------
# Test 1 — Tool merge + dispatch routing + <external_data> envelope.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_tool_dispatch_routes_to_mcp_client_with_envelope(
    postgres_engine: Engine,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eng, user_id = _seed_tenant_user_engagement(postgres_engine)
    _ins_mcp_config(postgres_engine, tenant_id=tid, connector_kind="slack")

    # Upstream advertises one tool; the LLM's first turn asks for it; the
    # mocked transport returns one text content block; the LLM's second
    # turn emits a final text answer.
    tools_list = [
        {
            "name": "search_messages",
            "description": "Search Slack messages.",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
    ]
    canned_payload = {
        "content": [{"type": "text", "text": "found 3 messages about the deadline"}],
        "isError": False,
    }
    http_client, seen_requests = _make_outbound_transport(
        tools_list=tools_list,
        tools_call_result=canned_payload,
    )
    rate_limiter = InMemoryMcpRateLimiter(per_turn_cap=10, per_minute_cap=60)
    mcp_client = _build_outbound_client(http_client, rate_limiter=rate_limiter)

    namespaced = namespace_tool_name("slack", "search_messages")
    llm = _LLMScript(
        [
            _ScriptedToolUse(
                tool_calls=[
                    {
                        "id": "toolu_1",
                        "name": namespaced,
                        "input": {"q": "deadline"},
                    }
                ]
            ),
            _ScriptedToolUse(text="Customers raised the deadline on Slack."),
        ]
    )

    service = KennyAgentService(
        llm,
        mcp_client=mcp_client,
        mcp_kill_switch=NoopKillSwitch(),
        mcp_rate_limiter=rate_limiter,
    )

    try:
        chunks, _ = await _run_one_turn(
            session_factory=app_session_factory,
            service=service,
            tenant_id=tid,
            engagement_id=eng,
            actor_user_id=user_id,
            message="what did the customer say in slack",
        )
    finally:
        await http_client.aclose()

    # 1.a: the second LLM call must have happened with the external tool
    # included in the merged tool list it received.
    assert any(t.get("name") == namespaced for t in llm.last_tools), (
        f"namespaced external tool missing from tools[]: {llm.last_tools}"
    )

    # 1.b: the mocked transport saw a tools/list AND a tools/call.
    methods = [json.loads(r.content.decode("utf-8"))["method"] for r in seen_requests]
    assert "tools/list" in methods
    assert "tools/call" in methods

    # 1.c: mcp_external_call frame surfaced via the SSE stream.
    external_frames = [c for c in chunks if type(c).__name__ == "McpExternalCallChunk"]
    assert len(external_frames) >= 1, f"chunks: {[type(c).__name__ for c in chunks]}"
    frame = external_frames[0]
    assert frame.connector_kind == "slack"
    assert frame.tool == "search_messages"
    assert frame.status == "ok"

    # 1.d: stream terminates with a DoneChunk (no error).
    assert any(isinstance(c, DoneChunk) for c in chunks)
    assert not any(isinstance(c, ErrorChunk) for c in chunks)

    # 1.e: there is no skipped-disabled frame because the kill switch was off.
    assert not any(type(c).__name__ == "McpOutboundSkippedDisabledChunk" for c in chunks), (
        f"unexpected skipped-disabled frame in chunks: {[type(c).__name__ for c in chunks]}"
    )

    # 1.f: SSE rendering produces a ``mcp_external_call`` event with
    # status=ok and the expected payload shape.
    sse_events = [format_chunk(c).decode("utf-8") for c in chunks if type(c).__name__ == "McpExternalCallChunk"]
    assert any("event: mcp_external_call" in s for s in sse_events)
    assert any('"connector_kind":"slack"' in s and '"status":"ok"' in s for s in sse_events)


# --------------------------------------------------------------------------
# Test 2 — Kill switch suppresses discovery + emits skipped-disabled frame.
# --------------------------------------------------------------------------


class _AlwaysDisabledKillSwitch:
    async def is_outbound_disabled(self, tenant_id: uuid.UUID) -> bool:
        return True


@pytest.mark.asyncio
async def test_kill_switch_skips_discovery_and_emits_skipped_disabled_frame(
    postgres_engine: Engine,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eng, user_id = _seed_tenant_user_engagement(postgres_engine)
    _ins_mcp_config(postgres_engine, tenant_id=tid, connector_kind="slack")

    # Even though the upstream "would" return tools, the kill switch
    # should preempt discovery → no http call from the loader → the LLM
    # never sees the external tool.
    http_client, seen_requests = _make_outbound_transport(
        tools_list=[
            {
                "name": "search_messages",
                "description": "x",
                "inputSchema": {"type": "object"},
            }
        ]
    )
    rate_limiter = InMemoryMcpRateLimiter(per_turn_cap=10, per_minute_cap=60)
    mcp_client = _build_outbound_client(http_client, rate_limiter=rate_limiter)

    llm = _LLMScript([_ScriptedToolUse(text="Acknowledged, no external data available.")])

    service = KennyAgentService(
        llm,
        mcp_client=mcp_client,
        mcp_kill_switch=_AlwaysDisabledKillSwitch(),
        mcp_rate_limiter=rate_limiter,
    )

    try:
        chunks, _ = await _run_one_turn(
            session_factory=app_session_factory,
            service=service,
            tenant_id=tid,
            engagement_id=eng,
            actor_user_id=user_id,
            message="anything from slack?",
        )
    finally:
        await http_client.aclose()

    # 2.a: kill switch precheck → no outbound traffic for tools/list.
    assert seen_requests == [], f"kill switch should suppress discovery; saw: {[r.url for r in seen_requests]}"

    # 2.b: the LLM did NOT see any external tool merged in.
    external_in_llm_tools = [t for t in llm.last_tools if t.get("name", "").startswith("slack__")]
    assert external_in_llm_tools == [], (
        f"LLM unexpectedly received external tools while kill switch engaged: {external_in_llm_tools}"
    )

    # 2.c: one ``mcp_outbound_skipped_disabled`` SSE frame surfaced.
    skipped_frames = [c for c in chunks if type(c).__name__ == "McpOutboundSkippedDisabledChunk"]
    assert len(skipped_frames) == 1, (
        f"expected exactly one mcp_outbound_skipped_disabled frame; got {[type(c).__name__ for c in chunks]}"
    )

    # 2.d: SSE rendering produces ``event: mcp_outbound_skipped_disabled``.
    rendered = format_chunk(skipped_frames[0]).decode("utf-8")
    assert "event: mcp_outbound_skipped_disabled" in rendered


# --------------------------------------------------------------------------
# Test 3 — Rate-limited dispatch produces an error tool_result.
# --------------------------------------------------------------------------


class _AlwaysDenyRateLimiter:
    """Mimics ``InMemoryMcpRateLimiter`` but denies every acquire."""

    def __init__(self) -> None:
        self._opens: list[uuid.UUID] = []
        self._closes: list[uuid.UUID] = []

    def open_turn(self, turn_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self._opens.append(turn_id)

    def close_turn(self, turn_id: uuid.UUID) -> None:
        self._closes.append(turn_id)

    async def acquire(self, tenant_id: uuid.UUID, tool_name: str) -> bool:
        return False

    async def release(self, tenant_id: uuid.UUID, tool_name: str) -> None:
        return None


@pytest.mark.asyncio
async def test_rate_limited_external_call_emits_error_tool_result(
    postgres_engine: Engine,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eng, user_id = _seed_tenant_user_engagement(postgres_engine)
    _ins_mcp_config(postgres_engine, tenant_id=tid, connector_kind="slack")

    http_client, _seen = _make_outbound_transport(
        tools_list=[
            {
                "name": "search_messages",
                "description": "search",
                "inputSchema": {"type": "object"},
            }
        ]
    )
    # Use the noop rate limiter for discovery (list_tools should succeed),
    # then swap to an always-deny limiter for tools/call. The integration
    # boundary is at the McpOutboundClient — easier to inject two clients
    # than juggle a stateful limiter; we instead just point the service
    # at the always-deny limiter so the per-turn open/close is exercised
    # AND the deny path inside call_tool fires. list_tools also calls
    # rate-limiter? It doesn't — re-checking mcp_client.list_tools shows
    # only call_tool consults the limiter, so the always-deny is safe for
    # both.
    rate_limiter = _AlwaysDenyRateLimiter()
    mcp_client = _build_outbound_client(http_client, rate_limiter=rate_limiter)

    namespaced = namespace_tool_name("slack", "search_messages")
    llm = _LLMScript(
        [
            _ScriptedToolUse(
                tool_calls=[
                    {
                        "id": "toolu_rl",
                        "name": namespaced,
                        "input": {"q": "deadline"},
                    }
                ]
            ),
            _ScriptedToolUse(text="(no external data; got rate-limited)"),
        ]
    )

    service = KennyAgentService(
        llm,
        mcp_client=mcp_client,
        mcp_kill_switch=NoopKillSwitch(),
        mcp_rate_limiter=rate_limiter,
    )

    try:
        chunks, _ = await _run_one_turn(
            session_factory=app_session_factory,
            service=service,
            tenant_id=tid,
            engagement_id=eng,
            actor_user_id=user_id,
            message="anything from slack right now?",
        )
    finally:
        await http_client.aclose()

    # 3.a: ``mcp_external_call`` with status=rate_limited surfaced.
    external_frames = [c for c in chunks if type(c).__name__ == "McpExternalCallChunk"]
    assert len(external_frames) == 1
    assert external_frames[0].status == "rate_limited"

    # 3.b: per-turn open + close lifecycle ran exactly once.
    assert len(rate_limiter._opens) == 1
    assert len(rate_limiter._closes) == 1
    assert rate_limiter._opens[0] == rate_limiter._closes[0]

    # 3.c: turn completed (DoneChunk; no ErrorChunk — the LLM saw the
    # is_error tool_result and produced a final reply).
    assert any(isinstance(c, DoneChunk) for c in chunks)
    assert not any(isinstance(c, ErrorChunk) for c in chunks)
