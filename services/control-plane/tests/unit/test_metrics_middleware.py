"""Unit tests for the perf-budget Prometheus metrics + middleware."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+psycopg://stub:stub@localhost/stub")
    try:
        metrics_mod.install_db_statement_listener(engine)
        metrics_mod.install_db_statement_listener(engine)
        assert event.contains(
            engine.sync_engine,
            "after_cursor_execute",
            metrics_mod._after_cursor_execute,
        )
    finally:
        await engine.dispose()


def test_after_cursor_execute_increments_unlabelled_counter() -> None:
    before = _counter_value(metrics_mod.db_statements_total)
    metrics_mod._after_cursor_execute(None, None, "SELECT 1", None, None, False)
    after = _counter_value(metrics_mod.db_statements_total)
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
