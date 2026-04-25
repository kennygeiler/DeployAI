"""Story 6-6: Master Strategist arbitration and queue routing."""

from __future__ import annotations

import uuid

import pytest

from master_strategist.arbitrate import (
    IncomingProposal,
    StrategistArbitrationConfig,
    arbitrate_proposals,
    strategist_score,
)


def test_routing_bands() -> None:
    cfg = StrategistArbitrationConfig(queue_threshold=0.6, low_threshold=0.35, max_override_scale=3.0)
    p_high = IncomingProposal(
        proposal_id=uuid.uuid4(),
        source="cartographer",
        confidence=0.9,
        phase_fit=0.9,
        user_override_count=0,
    )
    p_mid = IncomingProposal(
        proposal_id=uuid.uuid4(),
        source="oracle",
        confidence=0.45,
        phase_fit=0.45,
        user_override_count=0,
    )
    p_low = IncomingProposal(
        proposal_id=uuid.uuid4(),
        source="cartographer",
        confidence=0.1,
        phase_fit=0.05,
        user_override_count=0,
    )
    r = arbitrate_proposals((p_high, p_mid, p_low), cfg=cfg)
    assert len(r.action_queue) == 1
    assert len(r.user_validation_queue) == 1
    assert len(r.suppressed) == 1
    assert r.action_queue[0].proposal is p_high
    assert r.user_validation_queue[0].proposal is p_mid
    assert r.suppressed[0].proposal is p_low
    assert len(r.audit_suppressions) == 1


def test_fifty_mixed_proposals_distribute() -> None:
    cfg = StrategistArbitrationConfig(queue_threshold=0.55, low_threshold=0.30, max_override_scale=4.0)
    props: list[IncomingProposal] = []
    for i in range(50):
        props.append(
            IncomingProposal(
                proposal_id=uuid.uuid4(),
                source="cartographer" if i % 2 == 0 else "oracle",
                confidence=(i % 11) / 10.0,
                phase_fit=((5 * i) % 9) / 10.0,
                user_override_count=i % 4,
            ),
        )
    r = arbitrate_proposals(props, cfg=cfg)
    n_action = len(r.action_queue)
    n_val = len(r.user_validation_queue)
    n_sup = len(r.suppressed)
    assert n_action + n_val + n_sup == 50
    assert n_action >= 1 and n_val >= 1 and n_sup >= 1
    assert n_sup == len(r.audit_suppressions)


def test_strategist_score_is_bounded() -> None:
    cfg = StrategistArbitrationConfig()
    p = IncomingProposal(
        proposal_id=uuid.uuid4(),
        source="oracle",
        confidence=0.0,
        phase_fit=0.0,
        user_override_count=0,
    )
    assert 0.0 <= strategist_score(p, cfg) <= 1.0


def test_config_invalid() -> None:
    with pytest.raises(ValueError, match="low_threshold"):
        StrategistArbitrationConfig(queue_threshold=0.2, low_threshold=0.4)
