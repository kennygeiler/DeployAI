"""Import side effect: install OTel :class:`MeterProvider` before other ``control_plane`` code."""

from __future__ import annotations

from control_plane.otel import configure_opentelemetry

configure_opentelemetry()
