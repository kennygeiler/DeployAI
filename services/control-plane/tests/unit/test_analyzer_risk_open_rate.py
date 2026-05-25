"""Unit: risk_open_rate analyzer compute (Phase F1.c)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.risk_open_rate import compute


def _event(source_kind: str) -> LedgerEvent:
    return LedgerEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        occurred_at=datetime(2026, 5, 10, tzinfo=UTC),
        recorded_at=datetime(2026, 5, 10, tzinfo=UTC),
        actor_kind="user",
        actor_id=None,
        source_kind=source_kind,
        source_ref=None,
        summary="x",
        detail={"node_type": "risk"},
    )


def _ctx() -> dict[str, Any]:
    return {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "window_start": datetime(2026, 5, 1, tzinfo=UTC),
        "window_end": datetime(2026, 5, 15, tzinfo=UTC),
    }


def test_no_fire_when_net_below_threshold() -> None:
    out = compute(
        **_ctx(),
        opened=[_event("insight_opened") for _ in range(4)],
        closed=[],
        threshold=5,
    )
    assert out == []


def test_fires_when_net_exceeds_threshold() -> None:
    out = compute(
        **_ctx(),
        opened=[_event("insight_opened") for _ in range(8)],
        closed=[_event("insight_closed") for _ in range(2)],
        threshold=5,
    )
    assert len(out) == 1
    insight = out[0]
    assert insight.insight_kind == "risk_open_rate"
    assert insight.metrics["net"] == 6
    assert insight.severity == "low"


def test_closures_reduce_net_below_threshold() -> None:
    out = compute(
        **_ctx(),
        opened=[_event("insight_opened") for _ in range(8)],
        closed=[_event("insight_closed") for _ in range(8)],
        threshold=5,
    )
    assert out == []


def test_high_severity_when_3x_threshold() -> None:
    out = compute(
        **_ctx(),
        opened=[_event("insight_opened") for _ in range(20)],
        closed=[_event("insight_closed") for _ in range(2)],
        threshold=5,
    )
    assert out[0].severity == "high"


def test_custom_threshold_respected() -> None:
    out = compute(
        **_ctx(),
        opened=[_event("insight_opened") for _ in range(3)],
        closed=[],
        threshold=2,
    )
    assert len(out) == 1
    assert out[0].metrics["threshold"] == 2
