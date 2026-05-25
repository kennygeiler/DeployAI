"""Unit: extractor_acceptance_drift analyzer compute (Phase F2.b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.extractor_acceptance_drift import compute


def _event(
    source_kind: str,
    *,
    actor_kind: str = "agent:matrix_extractor",
    detail: dict[str, Any] | None = None,
    source_ref: uuid.UUID | None = None,
) -> LedgerEvent:
    return LedgerEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        occurred_at=datetime(2026, 5, 20, tzinfo=UTC),
        recorded_at=datetime(2026, 5, 20, tzinfo=UTC),
        actor_kind=actor_kind,
        actor_id=None,
        source_kind=source_kind,
        source_ref=source_ref,
        summary="x",
        detail=detail or {},
    )


def _created(pid: uuid.UUID) -> LedgerEvent:
    return _event("llm_proposal_created", detail={"proposal_id": str(pid)}, source_ref=pid)


def _accepted(pid: uuid.UUID) -> LedgerEvent:
    return _event("proposal_accepted", actor_kind="user", detail={"proposal_id": str(pid)}, source_ref=pid)


def _ctx() -> dict[str, Any]:
    return {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "window_start": datetime(2026, 5, 10, tzinfo=UTC),
        "window_end": datetime(2026, 5, 24, tzinfo=UTC),
    }


def test_returns_empty_when_window_below_min_proposals() -> None:
    pids = [uuid.uuid4() for _ in range(4)]
    out = compute(
        **_ctx(),
        window_created=[_created(p) for p in pids],
        window_accepted=[],
        baseline_created=[_created(uuid.uuid4()) for _ in range(10)],
        baseline_accepted=[],
    )
    assert out == []


def test_returns_empty_when_baseline_below_min_proposals() -> None:
    window_pids = [uuid.uuid4() for _ in range(10)]
    out = compute(
        **_ctx(),
        window_created=[_created(p) for p in window_pids],
        window_accepted=[_accepted(p) for p in window_pids[:2]],
        baseline_created=[_created(uuid.uuid4()) for _ in range(4)],
        baseline_accepted=[],
    )
    assert out == []


def test_returns_empty_when_drop_below_threshold() -> None:
    window_pids = [uuid.uuid4() for _ in range(10)]
    baseline_pids = [uuid.uuid4() for _ in range(10)]
    out = compute(
        **_ctx(),
        window_created=[_created(p) for p in window_pids],
        window_accepted=[_accepted(p) for p in window_pids[:7]],  # 70%
        baseline_created=[_created(p) for p in baseline_pids],
        baseline_accepted=[_accepted(p) for p in baseline_pids[:8]],  # 80%
    )
    assert out == []


def test_fires_when_drop_exceeds_25pp() -> None:
    window_pids = [uuid.uuid4() for _ in range(10)]
    baseline_pids = [uuid.uuid4() for _ in range(10)]
    out = compute(
        **_ctx(),
        window_created=[_created(p) for p in window_pids],
        window_accepted=[_accepted(p) for p in window_pids[:4]],  # 40%
        baseline_created=[_created(p) for p in baseline_pids],
        baseline_accepted=[_accepted(p) for p in baseline_pids[:8]],  # 80%
    )
    assert len(out) == 1
    insight = out[0]
    assert insight.insight_kind == "extractor_acceptance_drift"
    assert insight.metrics["window_acceptance_rate"] == 0.4
    assert insight.metrics["baseline_acceptance_rate"] == 0.8
    assert insight.metrics["drop_pp"] == 0.4
    assert insight.severity == "medium"


def test_deterministic_id_for_same_window() -> None:
    window_pids = [uuid.uuid4() for _ in range(10)]
    baseline_pids = [uuid.uuid4() for _ in range(10)]
    kwargs: dict[str, Any] = {
        **_ctx(),
        "window_created": [_created(p) for p in window_pids],
        "window_accepted": [_accepted(p) for p in window_pids[:3]],
        "baseline_created": [_created(p) for p in baseline_pids],
        "baseline_accepted": [_accepted(p) for p in baseline_pids[:9]],
    }
    a = compute(**kwargs)[0]
    b = compute(**kwargs)[0]
    assert a.id == b.id
