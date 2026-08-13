"""SL1 — pure helpers of the Slack channel-intake pipeline (no DB, no Slack)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from control_plane.services.slack_event_ingest import process_slack_event_envelope
from control_plane.services.slack_snapshot_flush import batch_unit_key, unit_fingerprint


def test_batch_unit_key_prefers_thread() -> None:
    dt = datetime(2026, 8, 13, 9, 30, tzinfo=UTC)
    assert batch_unit_key(thread_ts="1755075000.000100", occurred_at=dt) == "t1755075000.000100"


def test_batch_unit_key_falls_back_to_utc_day() -> None:
    dt = datetime(2026, 8, 13, 23, 59, tzinfo=UTC)
    assert batch_unit_key(thread_ts=None, occurred_at=dt) == "d2026-08-13"
    assert batch_unit_key(thread_ts="", occurred_at=dt) == "d2026-08-13"


def test_unit_fingerprint_is_order_insensitive_and_content_sensitive() -> None:
    a = unit_fingerprint(["2.0", "1.0"])
    b = unit_fingerprint(["1.0", "2.0"])
    c = unit_fingerprint(["1.0", "2.0", "3.0"])
    assert a == b
    assert a != c
    assert len(a) == 20


@pytest.mark.asyncio
async def test_envelope_ignores_non_event_callback() -> None:
    # Early return before any DB access — session may be a placeholder.
    session: Any = None
    out = await process_slack_event_envelope(session, data={"type": "url_verification"})
    assert out == {"action": "ignore", "reason": "not_event_callback"}


@pytest.mark.asyncio
async def test_envelope_ignores_missing_team_id() -> None:
    session: Any = None
    out = await process_slack_event_envelope(session, data={"type": "event_callback"})
    assert out == {"action": "ignore", "reason": "no_team_id"}
