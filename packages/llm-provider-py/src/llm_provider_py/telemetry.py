"""OpenTelemetry token metrics (API-only: no-op until an SDK exporter is installed)."""

from __future__ import annotations

from typing import Any

from opentelemetry import metrics

_meter: Any = None
_input_counter: Any = None
_output_counter: Any = None


def _counters() -> tuple[Any, Any]:
    global _meter, _input_counter, _output_counter
    if _input_counter is None or _output_counter is None:
        _meter = metrics.get_meter("deployai.llm_provider", "0.0.0")
        _input_counter = _meter.create_counter(
            "deployai.llm.input_tokens",
            unit="{token}",
            description="Input / prompt tokens sent to the LLM",
        )
        _output_counter = _meter.create_counter(
            "deployai.llm.output_tokens",
            unit="{token}",
            description="Output / completion tokens from the LLM",
        )
    return _input_counter, _output_counter


def _token_counts(usage: dict[str, Any], provider: str) -> tuple[int, int]:
    p = provider.lower()
    if p == "anthropic":
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    if p == "openai":
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    it = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    ot = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return it, ot


def emit_llm_usage_metrics(payload: dict[str, Any]) -> None:
    """Emit token counters for a ``record_usage`` payload (idempotent, safe if SDK absent)."""
    provider = str(payload.get("provider") or "unknown")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    inp, out = _token_counts(usage, provider)
    if inp == 0 and out == 0:
        return
    attrs: dict[str, str] = {
        "llm.provider": provider,
        "llm.model": str(payload.get("model") or ""),
        "tenant.id": str(payload.get("tenant_id") or ""),
        "agent.name": str(payload.get("agent_name") or ""),
    }
    inc_in, inc_out = _counters()
    if inp:
        inc_in.add(inp, attrs)
    if out:
        inc_out.add(out, attrs)
