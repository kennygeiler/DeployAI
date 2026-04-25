from control_plane.solidification.classifier import classify_candidate


def test_structured_class_a() -> None:
    assert classify_candidate(source_kind="calendar", confidence=0.95) == "class_A_auto_solidify"


def test_pattern_class_b() -> None:
    assert classify_candidate(source_kind="inferred_pattern", confidence=0.75) == "class_B_weekly_review"


def test_low_stays() -> None:
    assert classify_candidate(source_kind="x", confidence=0.2) == "stay_candidate"
