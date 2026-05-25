"""Unit tests for the perf-budget Prometheus metrics + middleware."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane.infra import metrics as metrics_mod


def _counter_value(counter: Any, **labels: str) -> float:
    sample = counter.labels(**labels) if labels else counter
    return float(sample._value.get())


def _histogram_sum(histogram: Any, **labels: str) -> float:
    return float(histogram.labels(**labels)._sum.get())


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(metrics_mod.PrometheusMiddleware)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(metrics_mod.SLOW_REQUEST_SECONDS + 0.05)
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_middleware_observes_histogram_with_route_template() -> None:
    app = _build_app()
    route = "/items/{item_id}"
    before = _histogram_sum(
        metrics_mod.http_request_duration_seconds,
        route=route,
        method="GET",
        status="200",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/items/abc-123")

    assert response.status_code == 200
    after = _histogram_sum(
        metrics_mod.http_request_duration_seconds,
        route=route,
        method="GET",
        status="200",
    )
    assert after > before


@pytest.mark.asyncio
async def test_slow_request_counter_fires_when_over_budget() -> None:
    app = _build_app()
    route = "/slow"
    before = _counter_value(metrics_mod.slow_request_total, route=route)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        response = await client.get("/slow")

    assert response.status_code == 200
    assert _counter_value(metrics_mod.slow_request_total, route=route) == before + 1


@pytest.mark.asyncio
async def test_audit_emit_failure_increments_counter() -> None:
    from control_plane.audit import emit_audit_event

    before = _counter_value(metrics_mod.audit_emit_failures_total)

    session = AsyncMock()
    session.add = MagicMock()

    with pytest.raises(ValueError):
        await emit_audit_event(
            session,
            tenant_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            category="Bad.Caps",
            summary="x",
            detail={},
        )

    assert _counter_value(metrics_mod.audit_emit_failures_total) == before + 1


@pytest.mark.asyncio
async def test_install_db_statement_listener_is_idempotent() -> None:
    from sqlalchemy import event

    engine = create_async_engine("postgresql+psycopg://stub:stub@localhost/stub")
    try:
        metrics_mod.install_db_statement_listener(engine)
        metrics_mod.install_db_statement_listener(engine)
        assert event.contains(
            engine.sync_engine,
            "after_cursor_execute",
            metrics_mod._after_cursor_execute,
        )
        assert event.contains(
            engine.sync_engine,
            "engine_connect",
            metrics_mod._on_engine_connect,
        )
    finally:
        await engine.dispose()


def test_after_cursor_execute_uses_connection_info_labels() -> None:
    route = "/internal/v1/test-route"
    method = "POST"
    before = _counter_value(metrics_mod.db_statements_total, route=route, method=method)

    fake_conn = MagicMock()
    fake_conn.info = {
        "deployai_route": route,
        "deployai_method": method,
    }
    fake_context = MagicMock()
    fake_context.connection = fake_conn

    metrics_mod._after_cursor_execute(None, None, "SELECT 1", None, fake_context, False)

    after = _counter_value(metrics_mod.db_statements_total, route=route, method=method)
    assert after == before + 1


def test_after_cursor_execute_falls_back_to_unknown_labels_without_info() -> None:
    before = _counter_value(metrics_mod.db_statements_total, route="unknown", method="UNKNOWN")

    fake_conn = MagicMock()
    fake_conn.info = {}
    fake_context = MagicMock()
    fake_context.connection = fake_conn

    metrics_mod._after_cursor_execute(None, None, "SELECT 1", None, fake_context, False)

    after = _counter_value(metrics_mod.db_statements_total, route="unknown", method="UNKNOWN")
    assert after == before + 1


@pytest.mark.asyncio
async def test_engine_connect_copies_contextvars_to_connection_info() -> None:
    """End-to-end: middleware ContextVars → engine_connect → connection.info → after_cursor_execute."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metrics_mod.install_db_statement_listener(engine)

    route = "/internal/v1/db-attribution-test"
    method = "GET"
    before = _counter_value(metrics_mod.db_statements_total, route=route, method=method)

    route_token = metrics_mod._route_var.set(route)
    method_token = metrics_mod._method_var.set(method)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT 2"))
    finally:
        metrics_mod._route_var.reset(route_token)
        metrics_mod._method_var.reset(method_token)
        await engine.dispose()

    after = _counter_value(metrics_mod.db_statements_total, route=route, method=method)
    assert after == before + 2


@pytest.mark.asyncio
async def test_middleware_propagates_labels_to_db_statements() -> None:
    """Full stack: a request hitting the app produces correctly labelled db_statements."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metrics_mod.install_db_statement_listener(engine)

    route = "/widgets/{widget_id}"
    method = "GET"
    before = _counter_value(metrics_mod.db_statements_total, route=route, method=method)

    app = FastAPI()
    app.add_middleware(metrics_mod.PrometheusMiddleware)

    @app.get(route)
    async def get_widget(widget_id: str) -> dict[str, str]:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"id": widget_id}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/widgets/xyz")
            assert response.status_code == 200
    finally:
        await engine.dispose()

    after = _counter_value(metrics_mod.db_statements_total, route=route, method=method)
    assert after == before + 1


def test_all_metrics_appear_in_default_registry() -> None:
    from prometheus_client import REGISTRY

    names = {family.name for family in REGISTRY.collect()}
    expected = {
        "deployai_db_statements",
        "deployai_http_request_duration_seconds",
        "deployai_audit_emit_failures",
        "deployai_slow_request",
    }
    for stem in expected:
        assert any(name.startswith(stem) for name in names), f"missing metric stem {stem}"
