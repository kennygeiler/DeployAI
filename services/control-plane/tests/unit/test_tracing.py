"""Unit tests for explicit OTel tracing (infra.tracing + agent-node spans).

A local :class:`TracerProvider` with an ``InMemorySpanExporter`` is wired
through :func:`set_tracer_provider_override` — the process-global provider
(``trace.set_tracer_provider`` is once-per-process) is never touched, so
the no-op tests keep observing the default no-op behaviour.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import (
    ChatMessage,
    StopReason,
    TextDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from control_plane.agents.agent_kenny.nodes import tool_dispatch as tool_dispatch_mod
from control_plane.agents.agent_kenny.nodes.citations import verify_citations_parallel
from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.nodes.tool_dispatch import dispatch_tools
from control_plane.agents.agent_kenny.types import AgentState
from control_plane.agents.tools import ToolResult
from control_plane.infra.request_context import RequestIdMiddleware
from control_plane.infra.tracing import (
    TracingMiddleware,
    inject_trace_context,
    set_tracer_provider_override,
    tracer,
)

_INBOUND_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_INBOUND_SPAN_ID = "b7ad6b7169203331"
_INBOUND_TRACEPARENT = f"00-{_INBOUND_TRACE_ID}-{_INBOUND_SPAN_ID}-01"


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider_override(provider)
    try:
        yield exporter
    finally:
        set_tracer_provider_override(None)


def _span_named(spans: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    matches = [s for s in spans if s.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} span, got {[s.name for s in spans]}"
    return matches[0]


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "yes"}

    # Same relative order as main.py: RequestIdMiddleware outermost so the
    # request id ContextVar is populated before the span is opened.
    app.add_middleware(TracingMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


async def test_middleware_extracts_traceparent_and_stamps_request_id(
    span_exporter: InMemorySpanExporter,
) -> None:
    request_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        r = await client.get(
            "/ping",
            headers={"traceparent": _INBOUND_TRACEPARENT, "X-Request-ID": request_id},
        )
    assert r.status_code == 200

    span = _span_named(span_exporter.get_finished_spans(), "GET /ping")
    # Child of the inbound W3C context, not a new root.
    assert format(span.context.trace_id, "032x") == _INBOUND_TRACE_ID
    assert span.parent is not None
    assert format(span.parent.span_id, "016x") == _INBOUND_SPAN_ID
    assert span.attributes is not None
    assert span.attributes["http.method"] == "GET"
    assert span.attributes["http.route"] == "/ping"
    assert span.attributes["http.status_code"] == 200
    assert span.attributes["deployai.request_id"] == request_id


async def test_middleware_without_traceparent_starts_new_root(
    span_exporter: InMemorySpanExporter,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        r = await client.get("/ping")
    assert r.status_code == 200
    span = _span_named(span_exporter.get_finished_spans(), "GET /ping")
    assert span.parent is None
    assert span.attributes is not None
    # RequestIdMiddleware generates an id even when none is inbound.
    assert span.attributes["deployai.request_id"]


class _FakeProvider:
    """Scripted ToolStreamChunk sequences, one list per llm_call."""

    id = "fake-model"

    def __init__(self, scripts: list[list[ToolStreamChunk]]) -> None:
        self._scripts = scripts
        self.calls = 0

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
        tool_choice: dict[str, Any] | None = None,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, tools, temperature, max_output_tokens, tool_choice
        idx = self.calls
        self.calls += 1
        for chunk in self._scripts[idx] if idx < len(self._scripts) else []:
            yield chunk


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what changed?",
        started_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


async def test_stubbed_turn_produces_expected_span_tree(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """turn → llm_call x2 / tool_dispatch / citations, with node attributes."""
    state = _state()
    provider = _FakeProvider(
        scripts=[
            [
                ToolUseStart(id="toolu_1", name="get_engagement_summary"),
                ToolUseEnd(id="toolu_1", name="get_engagement_summary", input={}),
                StopReason(reason="tool_use", usage={"input_tokens": 10, "output_tokens": 4}),
            ],
            [
                # Unknown kinded prefix → unverified without any DB lookup.
                TextDelta(content="All good [bogus:abc123]."),
                StopReason(reason="end_turn", usage={"input_tokens": 12, "output_tokens": 6}),
            ],
        ]
    )

    async def _stub_summary(_session: Any, **_kwargs: Any) -> ToolResult:
        return ToolResult(name="get_engagement_summary", rows=[{"total_nodes": 1}])

    monkeypatch.setitem(tool_dispatch_mod._INVOKERS, "get_engagement_summary", _stub_summary)

    # Mirror the service driver's parent span (service._run_graph is
    # @traced("agent_kenny.turn")); the nodes hang their spans off it.
    with tracer().start_as_current_span("agent_kenny.turn"):
        await call_llm_with_tools(provider, state, emit=None)
        await dispatch_tools(None, state, emit=None)  # type: ignore[arg-type]
        await call_llm_with_tools(provider, state, emit=None)
        await verify_citations_parallel(None, state, emit=None)  # type: ignore[arg-type]

    spans = span_exporter.get_finished_spans()
    turn = _span_named(spans, "agent_kenny.turn")
    llm_calls = [s for s in spans if s.name == "agent_kenny.llm_call"]
    dispatch = _span_named(spans, "agent_kenny.tool_dispatch")
    citations = _span_named(spans, "agent_kenny.citations")

    assert len(llm_calls) == 2
    for child in (*llm_calls, dispatch, citations):
        assert child.parent is not None
        assert child.parent.span_id == turn.context.span_id
        assert child.context.trace_id == turn.context.trace_id

    first_llm = min(llm_calls, key=lambda s: s.start_time or 0)
    assert first_llm.attributes is not None
    assert first_llm.attributes["llm.model"] == "fake-model"
    assert first_llm.attributes["llm.input_tokens"] == 10
    assert first_llm.attributes["llm.output_tokens"] == 4
    assert first_llm.attributes["llm.stop_reason"] == "tool_use"
    assert first_llm.attributes["llm.tool_use_count"] == 1

    assert dispatch.attributes is not None
    assert dispatch.attributes["tool.name"] == "get_engagement_summary"
    assert dispatch.attributes["tool.row_count"] == 1

    assert citations.attributes is not None
    assert citations.attributes["citations.verified"] == 0
    assert citations.attributes["citations.unverified"] == 1


async def test_unset_endpoint_is_noop_and_exports_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No DEPLOYAI/OTEL endpoint → pipeline not installed, spans non-recording."""
    from control_plane import otel
    from control_plane.config.settings import clear_settings_cache

    for var in (
        "DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_SDK_DISABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    clear_settings_cache()
    try:
        assert otel.tracing_enabled() is False
        otel.configure_opentelemetry()
        assert otel._configured is False

        # No provider override, no global SDK provider → non-recording spans,
        # zero exported data, no exceptions from any helper.
        with tracer().start_as_current_span("noop") as span:
            assert span.is_recording() is False
            headers: dict[str, str] = {}
            inject_trace_context(headers)
            assert "traceparent" not in headers

        async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
            r = await client.get("/ping", headers={"traceparent": _INBOUND_TRACEPARENT})
        assert r.status_code == 200
    finally:
        clear_settings_cache()


async def test_tracing_enabled_via_deployai_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from control_plane import otel
    from control_plane.config.settings import clear_settings_cache

    monkeypatch.setenv("DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    clear_settings_cache()
    try:
        assert otel.tracing_enabled() is True
    finally:
        clear_settings_cache()


async def test_inject_trace_context_writes_w3c_traceparent(
    span_exporter: InMemorySpanExporter,
) -> None:
    with tracer().start_as_current_span("outbound") as span:
        headers: dict[str, str] = {}
        inject_trace_context(headers)
    ctx = span.get_span_context()
    assert headers["traceparent"] == f"00-{format(ctx.trace_id, '032x')}-{format(ctx.span_id, '016x')}-01"
