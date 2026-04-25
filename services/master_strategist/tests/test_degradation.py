"""Story 6-8: degradation types + failure metric counter."""

from __future__ import annotations

from prometheus_client import REGISTRY

from master_strategist.degradation import AgentErrorState, agent_error_to_canonical_payload
from master_strategist.metrics import AGENT_FAILURES, record_agent_failure


def test_payload_shape() -> None:
    a = AgentErrorState(
        error_code="llm_timeout",
        retry_possible=True,
        user_message="Try again",
        detail="read timeout 30s",
    )
    p = agent_error_to_canonical_payload(a)
    assert p["error_code"] == "llm_timeout"
    assert p["retry_possible"] is True
    assert p["has_detail"] is True


def test_record_failure_increments_counter() -> None:
    c = REGISTRY.get_sample_value("agent_failures_total", {"agent": "metric_test", "error_code": "e"})
    if c is None:
        c = 0.0
    before = c or 0.0
    record_agent_failure(agent="metric_test", error_code="e")
    after = REGISTRY.get_sample_value("agent_failures_total", {"agent": "metric_test", "error_code": "e"})
    assert after is not None
    assert after == before + 1.0
    _ = AGENT_FAILURES
