from __future__ import annotations

import pytest


def test_configure_opentelemetry_is_safe_without_otlp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    from control_plane.otel import configure_opentelemetry

    configure_opentelemetry()
