"""Webhook subscriptions internal API (integration) — Sprint 8."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.webhooks import dispatcher as dispatcher_module

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'webhooks-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest_asyncio.fixture
async def w_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "w-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "w-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


# --- CRUD --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_webhook_auto_generates_secret_and_returns_once(
    w_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await w_client.post(
        f"/internal/v1/webhooks?tenant_id={tid}",
        json={
            "name": "ops slack",
            "url": "https://example.com/hook",
            "events": ["insight.created"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ops slack"
    assert body["url"] == "https://example.com/hook"
    assert body["events"] == ["insight.created"]
    assert body["active"] is True
    assert body["has_secret"] is True
    assert body["secret"] and len(body["secret"]) >= 32
    assert body["secret_masked"] is not None
    # GET should mask the secret, not return raw.
    g = await w_client.get(f"/internal/v1/webhooks/{body['id']}?tenant_id={tid}")
    assert g.status_code == 200
    assert "secret" not in g.json()
    assert g.json()["secret_masked"] is not None
    assert g.json()["has_secret"] is True


@pytest.mark.asyncio
async def test_create_webhook_accepts_localhost_http(w_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await w_client.post(
        f"/internal/v1/webhooks?tenant_id={tid}",
        json={
            "name": "local",
            "url": "http://localhost:9999/hook",
            "events": [],
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_create_webhook_rejects_plain_http_url(w_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await w_client.post(
        f"/internal/v1/webhooks?tenant_id={tid}",
        json={
            "name": "bad",
            "url": "http://example.com/hook",
            "events": [],
        },
    )
    assert r.status_code == 422
    assert "https" in r.text


@pytest.mark.asyncio
async def test_create_webhook_rejects_unknown_event(w_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await w_client.post(
        f"/internal/v1/webhooks?tenant_id={tid}",
        json={
            "name": "bad",
            "url": "https://example.com/hook",
            "events": ["bogus.event"],
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_update_delete_webhook(w_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    created = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={"name": "one", "url": "https://a.example/h", "events": ["insight.created"]},
        )
    ).json()
    wid = created["id"]

    listed = await w_client.get(f"/internal/v1/webhooks?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    upd = await w_client.put(
        f"/internal/v1/webhooks/{wid}?tenant_id={tid}",
        json={"name": "renamed", "events": ["insight.created", "proposal.added"], "active": False},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "renamed"
    assert upd.json()["active"] is False
    assert sorted(upd.json()["events"]) == sorted(["insight.created", "proposal.added"])

    dr = await w_client.delete(f"/internal/v1/webhooks/{wid}?tenant_id={tid}")
    assert dr.status_code == 204
    listed2 = await w_client.get(f"/internal/v1/webhooks?tenant_id={tid}")
    assert listed2.json() == []


@pytest.mark.asyncio
async def test_get_webhook_not_found(w_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await w_client.get(f"/internal/v1/webhooks/{uuid.uuid4()}?tenant_id={tid}")
    assert r.status_code == 404


# --- Dispatcher fires + retries once -----------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, text_body: str = "ok") -> None:
        self.status_code = status_code
        self.text = text_body


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient used by the dispatcher.

    Holds class-level state so the test can program a queue of responses
    or exceptions, and inspect what was posted.
    """

    responses: ClassVar[list[Any]] = []
    calls: ClassVar[list[tuple[str, bytes, dict[str, str]]]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        _FakeAsyncClient.calls.append((url, content, headers))
        if not _FakeAsyncClient.responses:
            return _FakeResponse(200)
        nxt = _FakeAsyncClient.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


async def _wait_for(predicate: Any, *, deadline_seconds: float = 2.0) -> None:
    """Poll ``predicate`` (a callable returning bool) until True or timeout."""
    deadline = asyncio.get_event_loop().time() + deadline_seconds
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out waiting for predicate")


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[type[_FakeAsyncClient]]:
    _FakeAsyncClient.responses = []
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(dispatcher_module.httpx, "AsyncClient", _FakeAsyncClient)
    yield _FakeAsyncClient
    _FakeAsyncClient.responses = []
    _FakeAsyncClient.calls = []


@pytest.fixture
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the 30s retry delay so tests don't sleep."""
    monkeypatch.setattr(dispatcher_module, "_RETRY_DELAY_SECONDS", 0.01)


@pytest.mark.asyncio
async def test_dispatch_fires_post_to_subscribed_webhook(
    w_client: AsyncClient,
    postgres_engine: Engine,
    fake_httpx: type[_FakeAsyncClient],
    fast_retry: None,
) -> None:
    import uuid as _uuid

    from control_plane.db import _get_app_session_maker
    from control_plane.webhooks.dispatcher import dispatch

    tid = _uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    created = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={"name": "h", "url": "https://example.com/x", "events": ["insight.created"]},
        )
    ).json()
    wid = created["id"]

    async with _get_app_session_maker()() as session:
        await dispatch(session, tid, "insight.created", {"foo": "bar"})

    await _wait_for(lambda: len(_FakeAsyncClient.calls) >= 1)
    url, body, headers = _FakeAsyncClient.calls[0]
    assert url == "https://example.com/x"
    assert headers["X-DeployAI-Signature"].startswith("sha256=")
    assert b'"event":"insight.created"' in body

    # Delivery row recorded as succeeded.
    await _wait_for(
        lambda: _delivery_status(postgres_engine, _uuid.UUID(wid)) == "succeeded",
        deadline_seconds=2.0,
    )


def _delivery_status(engine: Engine, webhook_id: uuid.UUID) -> str | None:
    with engine.begin() as c:
        r = c.execute(
            text("SELECT status FROM webhook_deliveries WHERE webhook_id = :w ORDER BY created_at DESC LIMIT 1"),
            {"w": str(webhook_id)},
        )
        row = r.first()
    return row[0] if row else None


def _delivery_attempts(engine: Engine, webhook_id: uuid.UUID) -> int:
    with engine.begin() as c:
        r = c.execute(
            text("SELECT attempts FROM webhook_deliveries WHERE webhook_id = :w ORDER BY created_at DESC LIMIT 1"),
            {"w": str(webhook_id)},
        )
        row = r.first()
    return int(row[0]) if row else 0


@pytest.mark.asyncio
async def test_dispatch_retries_once_after_failure(
    w_client: AsyncClient,
    postgres_engine: Engine,
    fake_httpx: type[_FakeAsyncClient],
    fast_retry: None,
) -> None:
    import uuid as _uuid

    from control_plane.db import _get_app_session_maker
    from control_plane.webhooks.dispatcher import dispatch

    tid = _uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    created = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={"name": "h", "url": "https://example.com/x", "events": ["insight.created"]},
        )
    ).json()
    wid = _uuid.UUID(created["id"])

    # First call 500, second call 200 — should succeed after retry.
    _FakeAsyncClient.responses = [_FakeResponse(500, "boom"), _FakeResponse(200, "ok")]

    async with _get_app_session_maker()() as session:
        await dispatch(session, tid, "insight.created", {"foo": "bar"})

    await _wait_for(lambda: _delivery_status(postgres_engine, wid) == "succeeded", deadline_seconds=3.0)
    assert _delivery_attempts(postgres_engine, wid) == 2
    assert len(_FakeAsyncClient.calls) == 2


@pytest.mark.asyncio
async def test_dispatch_marks_failed_when_both_attempts_fail(
    w_client: AsyncClient,
    postgres_engine: Engine,
    fake_httpx: type[_FakeAsyncClient],
    fast_retry: None,
) -> None:
    import uuid as _uuid

    from control_plane.db import _get_app_session_maker
    from control_plane.webhooks.dispatcher import dispatch

    tid = _uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    created = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={"name": "h", "url": "https://example.com/x", "events": ["insight.created"]},
        )
    ).json()
    wid = _uuid.UUID(created["id"])

    _FakeAsyncClient.responses = [_FakeResponse(500, "boom"), _FakeResponse(503, "still broken")]

    async with _get_app_session_maker()() as session:
        await dispatch(session, tid, "insight.created", {"foo": "bar"})

    await _wait_for(lambda: _delivery_status(postgres_engine, wid) == "failed", deadline_seconds=3.0)
    assert _delivery_attempts(postgres_engine, wid) == 2


@pytest.mark.asyncio
async def test_dispatch_skips_inactive_or_unsubscribed_webhooks(
    w_client: AsyncClient,
    postgres_engine: Engine,
    fake_httpx: type[_FakeAsyncClient],
    fast_retry: None,
) -> None:
    import uuid as _uuid

    from control_plane.db import _get_app_session_maker
    from control_plane.webhooks.dispatcher import dispatch

    tid = _uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    # subscribed but inactive
    inactive = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={
                "name": "off",
                "url": "https://example.com/off",
                "events": ["insight.created"],
                "active": False,
            },
        )
    ).json()
    # active but not subscribed to insight.created
    not_subbed = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={
                "name": "other",
                "url": "https://example.com/other",
                "events": ["proposal.added"],
            },
        )
    ).json()

    async with _get_app_session_maker()() as session:
        await dispatch(session, tid, "insight.created", {})

    # Give any spurious tasks a chance to fire.
    await asyncio.sleep(0.05)
    assert _FakeAsyncClient.calls == []
    # No deliveries recorded for either.
    with postgres_engine.begin() as c:
        rows = c.execute(text("SELECT COUNT(*) FROM webhook_deliveries")).scalar_one()
    assert rows == 0
    _ = inactive, not_subbed


@pytest.mark.asyncio
async def test_list_deliveries_returns_recent_first(
    w_client: AsyncClient,
    postgres_engine: Engine,
    fake_httpx: type[_FakeAsyncClient],
    fast_retry: None,
) -> None:
    import uuid as _uuid

    from control_plane.db import _get_app_session_maker
    from control_plane.webhooks.dispatcher import dispatch

    tid = _uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    created = (
        await w_client.post(
            f"/internal/v1/webhooks?tenant_id={tid}",
            json={"name": "h", "url": "https://example.com/x", "events": ["insight.created"]},
        )
    ).json()
    wid = created["id"]
    async with _get_app_session_maker()() as session:
        await dispatch(session, _uuid.UUID(str(tid)), "insight.created", {"n": 1})
    await _wait_for(lambda: _delivery_status(postgres_engine, _uuid.UUID(wid)) is not None, deadline_seconds=2.0)

    listed = await w_client.get(f"/internal/v1/webhooks/{wid}/deliveries?tenant_id={tid}&limit=10")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) >= 1
    assert items[0]["event_name"] == "insight.created"
