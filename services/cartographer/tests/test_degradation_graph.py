"""Story 6-8: LangGraph agent_error path."""

from __future__ import annotations

from cartographer.degradation_graph import build_degradation_graph


def test_happy_path_no_error() -> None:
    g = build_degradation_graph()
    app = g.compile()
    out = app.invoke({"step": 0, "fail": False})
    assert out.get("fail") is False
    assert "error" not in out


def test_failure_terminates_with_agent_error() -> None:
    g = build_degradation_graph()
    app = g.compile()
    out = app.invoke({"step": 0, "fail": True})
    assert out.get("error") is not None
    assert out["error"]["error_code"] == "llm_timeout"
    assert out["error"]["retry_possible"] is True
