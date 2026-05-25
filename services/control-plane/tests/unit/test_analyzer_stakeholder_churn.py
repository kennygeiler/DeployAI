"""Unit: stakeholder_churn analyzer compute (Phase F1.c)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.stakeholder_churn import compute


def _event(source_kind: str, **detail: Any) -> LedgerEvent:
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
        detail=detail,
    )


def _ctx() -> dict[str, Any]:
    return {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "window_start": datetime(2026, 5, 1, tzinfo=UTC),
        "window_end": datetime(2026, 5, 31, tzinfo=UTC),
    }


def test_no_fire_when_current_below_two() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed")],
        prior_events=[],
    )
    assert out == []


def test_no_fire_when_ratio_below_2x() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed") for _ in range(3)],
        prior_events=[_event("member_removed") for _ in range(2)],
    )
    assert out == []


def test_fires_when_ratio_above_2x() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed") for _ in range(6)],
        prior_events=[_event("member_removed") for _ in range(2)],
    )
    assert len(out) == 1
    insight = out[0]
    assert insight.insight_kind == "stakeholder_churn"
    assert insight.metrics["ratio"] == 3.0
    assert insight.severity == "medium"


def test_node_deleted_only_counts_when_node_type_is_stakeholder() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("matrix_node_deleted", node_type="stakeholder") for _ in range(4)],
        prior_events=[_event("matrix_node_deleted", node_type="stakeholder")],
    )
    assert len(out) == 1
    assert out[0].metrics["current_window_count"] == 4


def test_high_severity_when_ratio_ge_5x() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed") for _ in range(6)],
        prior_events=[_event("member_removed")],
    )
    assert out[0].severity == "high"


def test_cold_start_requires_floor() -> None:
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed") for _ in range(2)],
        prior_events=[],
    )
    assert out == []
    out = compute(
        **_ctx(),
        current_events=[_event("member_removed") for _ in range(4)],
        prior_events=[],
    )
    assert len(out) == 1
