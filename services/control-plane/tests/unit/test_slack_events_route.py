"""ASGI tests for ``POST /integrations/slack/events`` (no Slack, no DB writes).

Covers the fail-closed posture: when ``DEPLOYAI_SLACK_SIGNING_SECRET`` is
unset, ``event_callback`` payloads are rejected instead of processed. The
URL-verification challenge keeps working without a secret so a Slack app
can still be pointed at the endpoint before the secret is provisioned.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane.config.settings import clear_settings_cache
from control_plane.main import app

_SECRET = "test-signing-secret"


def _sign(body: bytes, *, secret: str, timestamp: int | None = None) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    base = f"v0:{ts}:{body.decode('utf-8')}"
    dig = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": f"v0={dig}",
        "Content-Type": "application/json",
    }


def _event_callback_body() -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "team_id": "T123",
            "event": {"type": "message", "channel": "C1", "user": "U1", "text": "hi", "ts": "1.0"},
        }
    ).encode("utf-8")


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[pytest.MonkeyPatch]:
    monkeypatch.delenv("DEPLOYAI_SLACK_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("DEPLOYAI_SLACK_ALLOW_UNSIGNED", raising=False)
    clear_settings_cache()
    yield monkeypatch
    clear_settings_cache()


def _stub_ingest(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the real Slack-event ingest with a recorder so no DB rows land."""
    calls: list[dict[str, Any]] = []

    async def _fake(session: Any, *, data: dict[str, Any]) -> dict[str, Any]:
        calls.append(data)
        return {"ingested": 1}

    monkeypatch.setattr(
        "control_plane.api.routes.integrations_slack.process_slack_event_envelope",
        _fake,
    )
    return calls


async def _post_events(body: bytes, headers: dict[str, str] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(
            "/integrations/slack/events",
            content=body,
            headers=headers or {"Content-Type": "application/json"},
        )


@pytest.mark.asyncio
async def test_event_callback_rejected_when_secret_unset(_clean_env: pytest.MonkeyPatch) -> None:
    """Fail closed: no signing secret means events are never processed."""
    calls = _stub_ingest(_clean_env)
    r = await _post_events(_event_callback_body())
    assert r.status_code == 503
    assert calls == []


@pytest.mark.asyncio
async def test_url_verification_challenge_works_without_secret(_clean_env: pytest.MonkeyPatch) -> None:
    body = json.dumps({"type": "url_verification", "challenge": "chal-123"}).encode("utf-8")
    r = await _post_events(body)
    assert r.status_code == 200
    assert r.text == "chal-123"


@pytest.mark.asyncio
async def test_event_callback_with_valid_signature_is_processed(_clean_env: pytest.MonkeyPatch) -> None:
    _clean_env.setenv("DEPLOYAI_SLACK_SIGNING_SECRET", _SECRET)
    clear_settings_cache()
    calls = _stub_ingest(_clean_env)
    body = _event_callback_body()
    r = await _post_events(body, headers=_sign(body, secret=_SECRET))
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert len(calls) == 1
    assert calls[0]["type"] == "event_callback"


@pytest.mark.asyncio
async def test_event_callback_with_bad_signature_is_401(_clean_env: pytest.MonkeyPatch) -> None:
    _clean_env.setenv("DEPLOYAI_SLACK_SIGNING_SECRET", _SECRET)
    clear_settings_cache()
    calls = _stub_ingest(_clean_env)
    body = _event_callback_body()
    r = await _post_events(body, headers=_sign(body, secret="wrong-secret"))
    assert r.status_code == 401
    assert calls == []


@pytest.mark.asyncio
async def test_event_callback_with_stale_timestamp_is_401(_clean_env: pytest.MonkeyPatch) -> None:
    _clean_env.setenv("DEPLOYAI_SLACK_SIGNING_SECRET", _SECRET)
    clear_settings_cache()
    calls = _stub_ingest(_clean_env)
    body = _event_callback_body()
    stale = int(time.time()) - 60 * 60
    r = await _post_events(body, headers=_sign(body, secret=_SECRET, timestamp=stale))
    assert r.status_code == 401
    assert calls == []


@pytest.mark.asyncio
async def test_dev_flag_allows_unsigned_event_callback(_clean_env: pytest.MonkeyPatch) -> None:
    """DEPLOYAI_SLACK_ALLOW_UNSIGNED=1 is the explicit, default-off dev bypass."""
    _clean_env.setenv("DEPLOYAI_SLACK_ALLOW_UNSIGNED", "1")
    clear_settings_cache()
    calls = _stub_ingest(_clean_env)
    r = await _post_events(_event_callback_body())
    assert r.status_code == 200, r.text
    assert len(calls) == 1
