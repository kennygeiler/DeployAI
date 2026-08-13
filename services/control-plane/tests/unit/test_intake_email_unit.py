"""Unit: intake-email pure helpers + webhook gating (Wave 5 IN1).

DB-touching behavior (address mint/regenerate, event write, extraction
chain) lives in ``tests/integration/test_intake_email_flow.py``; this file
covers the session-free pieces: slug/local-part shape, Postmark payload
parsing, dedup keys, and the secret gate (404 when unset, 401 on mismatch).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane.config.settings import clear_settings_cache
from control_plane.main import app
from control_plane.services.intake_email import (
    MAX_TEXT_BYTES,
    content_fingerprint,
    extract_body_text,
    intake_dedup_key,
    mint_local_part,
    naive_html_to_text,
    parse_occurred_at,
    recipient_local_parts,
    slug_for_engagement_name,
)

SECRET = "intake-test-secret"


@pytest.fixture(autouse=True)
def _settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


# --- slug + local part -------------------------------------------------------


def test_slug_lowercases_and_hyphenates() -> None:
    assert slug_for_engagement_name("NYC DOT LiDAR (Phase 2)") == "nyc-dot-lidar-phase-2"


def test_slug_caps_length_and_survives_empty() -> None:
    assert len(slug_for_engagement_name("x" * 200)) <= 30
    assert slug_for_engagement_name("!!! ???") == "engagement"


def test_mint_local_part_has_slug_and_long_token() -> None:
    lp = mint_local_part("Acme Rollout")
    assert lp.startswith("acme-rollout-")
    token = lp.rsplit("-", 1)[-1]
    assert len(token) >= 16
    # two mints never collide
    assert mint_local_part("Acme Rollout") != lp


# --- Postmark payload parsing ------------------------------------------------


def test_recipient_local_parts_prefers_tofull_and_dedups() -> None:
    payload = {
        "ToFull": [{"Email": "acme-abc123@intake.example.com"}, {"Email": "other@example.com"}],
        "CcFull": [{"Email": "acme-abc123@intake.example.com"}],
        "To": '"Deal" <acme-abc123@intake.example.com>, plain@example.com',
    }
    assert recipient_local_parts(payload) == ["acme-abc123", "other", "plain"]


def test_recipient_local_parts_defensive_on_garbage() -> None:
    assert recipient_local_parts({}) == []
    assert recipient_local_parts({"ToFull": "nope", "To": 42}) == []
    assert recipient_local_parts({"ToFull": [None, {"Email": 5}, {}]}) == []


def test_extract_body_text_prefers_text_body() -> None:
    assert extract_body_text({"TextBody": "hello", "HtmlBody": "<p>bye</p>"}) == "hello"


def test_extract_body_text_falls_back_to_html_strip() -> None:
    out = extract_body_text({"HtmlBody": "<div>Line one<br>Line&nbsp;two</div><style>p{}</style>"})
    assert "Line one" in out
    assert "Line two" in out
    assert "style" not in out


def test_naive_html_to_text_drops_scripts() -> None:
    assert "alert" not in naive_html_to_text("<script>alert(1)</script>hi")


def test_parse_occurred_at_rfc2822_and_fallback() -> None:
    dt = parse_occurred_at({"Date": "Wed, 12 Aug 2026 10:30:00 +0200"})
    assert dt.tzinfo is not None
    assert dt.astimezone(UTC).hour == 8
    assert parse_occurred_at({"Date": "not a date"}).tzinfo is not None
    assert parse_occurred_at({}).tzinfo is not None


def test_intake_dedup_key_stable_and_fallbacks() -> None:
    eid = uuid.uuid4()
    a = intake_dedup_key(engagement_id=eid, message_id="m-1", fallback_fingerprint="f")
    assert a == intake_dedup_key(engagement_id=eid, message_id="m-1", fallback_fingerprint="other")
    assert a.startswith("intake:email:")
    # No MessageID → the content fingerprint stands in.
    fp = content_fingerprint(subject="s", sender="a@b", date="d", text="t")
    b = intake_dedup_key(engagement_id=eid, message_id="", fallback_fingerprint=fp)
    assert fp in b
    assert b != a


def test_max_text_bytes_is_500kb() -> None:
    assert MAX_TEXT_BYTES == 500_000


# --- webhook secret gate (no DB reached on rejection) ------------------------


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_webhook_404_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYAI_INTAKE_WEBHOOK_SECRET", raising=False)
    clear_settings_cache()
    async with _client() as c:
        r = await c.post(
            "/internal/v1/intake/email",
            headers={"X-DeployAI-Intake-Secret": "whatever"},
            json={},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_webhook_401_on_wrong_or_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_INTAKE_WEBHOOK_SECRET", SECRET)
    clear_settings_cache()
    async with _client() as c:
        wrong = await c.post(
            "/internal/v1/intake/email",
            headers={"X-DeployAI-Intake-Secret": "nope"},
            json={},
        )
        missing = await c.post("/internal/v1/intake/email", json={})
    assert wrong.status_code == 401
    assert missing.status_code == 401


@pytest.mark.asyncio
async def test_webhook_400_on_non_object_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_INTAKE_WEBHOOK_SECRET", SECRET)
    clear_settings_cache()
    async with _client() as c:
        r = await c.post(
            "/internal/v1/intake/email",
            headers={"X-DeployAI-Intake-Secret": SECRET, "content-type": "application/json"},
            content=b"[1, 2]",
        )
    assert r.status_code == 400
