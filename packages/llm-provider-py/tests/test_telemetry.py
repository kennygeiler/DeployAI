from __future__ import annotations

import pytest


def test_emit_llm_usage_metrics_anthropic_no_crash() -> None:
    from llm_provider_py.telemetry import emit_llm_usage_metrics

    emit_llm_usage_metrics(
        {
            "provider": "anthropic",
            "model": "claude-x",
            "tenant_id": "t1",
            "agent_name": "a1",
            "usage": {"input_tokens": 3, "output_tokens": 5},
        },
    )


def test_record_usage_triggers_telemetry_without_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[dict] = []

    def fake_emit(p: dict) -> None:
        called.append(p)

    monkeypatch.setattr("llm_provider_py.telemetry.emit_llm_usage_metrics", fake_emit)
    from llm_provider_py.util import record_usage

    record_usage(
        None,
        {
            "provider": "openai",
            "model": "gpt-4o",
            "tenant_id": "t",
            "agent_name": "agent",
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
        },
    )
    assert len(called) == 1
    assert called[0]["provider"] == "openai"
