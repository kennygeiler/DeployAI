"""Import side effect: install logging + OTel :class:`MeterProvider` before other ``control_plane`` code."""

from __future__ import annotations

from control_plane.infra.logging import configure_logging
from control_plane.otel import configure_opentelemetry

configure_logging()
configure_opentelemetry()
