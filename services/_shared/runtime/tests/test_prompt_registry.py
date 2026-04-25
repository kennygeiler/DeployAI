from deployai_runtime.prompt_registry import PromptRegistry


def test_render_cartographer_v1() -> None:
    r = PromptRegistry()
    out = r.render(
        version="v1",
        name="cartographer/extract_v1",
        variables={
            "phase": "P2_discovery",
            "tenant_id": "t-1",
            "event_excerpt": "hello world",
        },
    )
    assert "P2_discovery" in out
    assert "hello world" in out


def test_phase_modulator() -> None:
    from deployai_runtime.phase_modulator import apply_phase_weights, alert_confidence_floor

    s1 = apply_phase_weights("P2_discovery", [("a", 0.5), ("b", 0.4)])
    s2 = apply_phase_weights("P5_pilot", [("a", 0.5), ("b", 0.4)])
    assert s1[0][1] != s2[0][1]
    assert alert_confidence_floor("P5_pilot") > alert_confidence_floor("P2_discovery")
