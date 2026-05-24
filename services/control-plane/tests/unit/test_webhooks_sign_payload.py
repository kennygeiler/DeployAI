"""Unit tests for the webhook payload signer (Sprint 8)."""

from __future__ import annotations

import hashlib
import hmac

from control_plane.webhooks.dispatcher import WEBHOOK_EVENTS, sign_payload


def test_sign_payload_returns_sha256_prefixed_hex() -> None:
    sig = sign_payload("topsecret", b'{"event":"insight.created"}')
    assert sig.startswith("sha256=")
    body = b'{"event":"insight.created"}'
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"


def test_sign_payload_is_deterministic() -> None:
    body = b'{"a":1}'
    assert sign_payload("k", body) == sign_payload("k", body)


def test_sign_payload_differs_per_secret() -> None:
    body = b'{"a":1}'
    assert sign_payload("k1", body) != sign_payload("k2", body)


def test_webhook_events_includes_required_set() -> None:
    assert "insight.created" in WEBHOOK_EVENTS
    assert "proposal.added" in WEBHOOK_EVENTS
    assert "extraction.completed" in WEBHOOK_EVENTS
