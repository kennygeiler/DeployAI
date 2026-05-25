"""Unit: engagement_silence analyzer compute (Phase F1.c)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.intelligence.engagement_silence import compute


def _ctx() -> dict[str, Any]:
    return {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "window_start": datetime(2026, 5, 1, tzinfo=UTC),
        "window_end": datetime(2026, 5, 15, tzinfo=UTC),
    }


def test_fires_info_when_engagement_has_zero_events() -> None:
    out = compute(**_ctx(), event_count=0)
    assert len(out) == 1
    insight = out[0]
    assert insight.insight_kind == "engagement_silence"
    assert insight.severity == "info"
    assert insight.metrics["event_count"] == 0
    assert insight.metrics["window_days"] == 14


def test_no_fire_when_events_present() -> None:
    out = compute(**_ctx(), event_count=1)
    assert out == []


def test_skips_tenant_scope() -> None:
    ctx = _ctx()
    ctx["engagement_id"] = None
    out = compute(**ctx, event_count=0)
    assert out == []


def test_deterministic_insight_id_for_same_window() -> None:
    ctx = _ctx()
    a = compute(**ctx, event_count=0)[0]
    b = compute(**ctx, event_count=0)[0]
    assert a.id == b.id
