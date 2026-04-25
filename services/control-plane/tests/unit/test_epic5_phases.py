from control_plane.phases.machine import can_transition, default_phase, DEPLOYMENT_PHASES


def test_can_only_step_forward_one_phase() -> None:
    assert can_transition("P1_pre_engagement", "P2_discovery")
    assert not can_transition("P1_pre_engagement", "P3_ecosystem_mapping")
    assert not can_transition("P2_discovery", "P1_pre_engagement")


def test_order_length() -> None:
    assert len(DEPLOYMENT_PHASES) == 7
    assert default_phase == "P1_pre_engagement"
