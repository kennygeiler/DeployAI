"""Unit: decision_cycle_slowdown analyzer compute (Phase F1.c)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.decision_cycle_slowdown import compute


def _event(
    source_kind: str,
    occurred_at: datetime,
    *,
    detail: dict[str, Any] | None = None,
    source_ref: uuid.UUID | None = None,
) -> LedgerEvent:
    return LedgerEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        actor_kind="agent:cartographer",
        actor_id=None,
        source_kind=source_kind,
        source_ref=source_ref,
        summary="x",
        detail=detail or {},
    )


def _pair(
    proposal_id: uuid.UUID,
    created_at: datetime,
    accepted_at: datetime,
) -> tuple[LedgerEvent, LedgerEvent]:
    created = _event(
        "llm_proposal_created",
        created_at,
        detail={"node_type": "decision", "proposal_id": str(proposal_id)},
        source_ref=proposal_id,
    )
    accepted = _event(
        "proposal_accepted",
        accepted_at,
        detail={"proposal_id": str(proposal_id)},
        source_ref=proposal_id,
    )
    return created, accepted


def _ctx() -> dict[str, Any]:
    return {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "window_start": datetime(2026, 5, 1, tzinfo=UTC),
        "window_end": datetime(2026, 5, 31, tzinfo=UTC),
    }


def test_no_fire_with_small_samples() -> None:
    base = datetime(2026, 5, 5, tzinfo=UTC)
    cur_created, cur_accepted, prior_created, prior_accepted = [], [], [], []
    for _ in range(2):
        c, a = _pair(uuid.uuid4(), base, base + timedelta(hours=1))
        cur_created.append(c)
        cur_accepted.append(a)
    for _ in range(2):
        c, a = _pair(uuid.uuid4(), base, base + timedelta(hours=1))
        prior_created.append(c)
        prior_accepted.append(a)
    out = compute(
        **_ctx(),
        current_created=cur_created,
        current_accepted=cur_accepted,
        prior_created=prior_created,
        prior_accepted=prior_accepted,
    )
    assert out == []


def test_no_fire_when_growth_below_50_percent() -> None:
    base = datetime(2026, 5, 5, tzinfo=UTC)
    cur_created, cur_accepted, prior_created, prior_accepted = [], [], [], []
    for _ in range(4):
        pid = uuid.uuid4()
        c, a = _pair(pid, base, base + timedelta(hours=6))
        cur_created.append(c)
        cur_accepted.append(a)
    for _ in range(4):
        pid = uuid.uuid4()
        c, a = _pair(pid, base, base + timedelta(hours=5))
        prior_created.append(c)
        prior_accepted.append(a)
    out = compute(
        **_ctx(),
        current_created=cur_created,
        current_accepted=cur_accepted,
        prior_created=prior_created,
        prior_accepted=prior_accepted,
    )
    assert out == []


def test_fires_when_mean_grows_over_50_percent() -> None:
    base = datetime(2026, 5, 5, tzinfo=UTC)
    cur_created, cur_accepted, prior_created, prior_accepted = [], [], [], []
    for _ in range(4):
        pid = uuid.uuid4()
        c, a = _pair(pid, base, base + timedelta(hours=10))
        cur_created.append(c)
        cur_accepted.append(a)
    for _ in range(4):
        pid = uuid.uuid4()
        c, a = _pair(pid, base, base + timedelta(hours=2))
        prior_created.append(c)
        prior_accepted.append(a)
    out = compute(
        **_ctx(),
        current_created=cur_created,
        current_accepted=cur_accepted,
        prior_created=prior_created,
        prior_accepted=prior_accepted,
    )
    assert len(out) == 1
    insight = out[0]
    assert insight.insight_kind == "decision_cycle_slowdown"
    assert insight.metrics["growth"] == 4.0
    assert insight.severity == "high"


def test_ignores_unpaired_events() -> None:
    base = datetime(2026, 5, 5, tzinfo=UTC)
    pid_a = uuid.uuid4()
    pid_b = uuid.uuid4()
    cur_created = [
        _event(
            "llm_proposal_created",
            base,
            detail={"node_type": "decision", "proposal_id": str(pid_a)},
            source_ref=pid_a,
        ),
        _event(
            "llm_proposal_created",
            base,
            detail={"node_type": "decision", "proposal_id": str(pid_b)},
            source_ref=pid_b,
        ),
    ]
    cur_accepted: list[LedgerEvent] = []
    prior_created: list[LedgerEvent] = []
    prior_accepted: list[LedgerEvent] = []
    out = compute(
        **_ctx(),
        current_created=cur_created,
        current_accepted=cur_accepted,
        prior_created=prior_created,
        prior_accepted=prior_accepted,
    )
    assert out == []
