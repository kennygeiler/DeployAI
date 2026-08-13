"""OpenTelemetry metrics + traces SDK wiring with OTLP/HTTP export.

Two configuration surfaces, checked in order:

1. ``DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT`` / ``DEPLOYAI_OTEL_SERVICE_NAME``
   (pydantic settings, docs/ops/tracing.md) — the endpoint is a collector
   base URL; ``/v1/traces`` and ``/v1/metrics`` are appended per the OTLP
   spec's env-var convention.
2. The standard ``OTEL_EXPORTER_OTLP_*`` env vars, honored for operators
   who already drive the SDK the stock way.

Neither set → nothing is installed: ``trace.get_tracer`` /
``metrics.get_meter`` stay bound to the API's no-op providers and every
span helper in ``infra.tracing`` costs a dict lookup.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_log = logging.getLogger(__name__)

# Avoid duplicate exporters / readers on reload or double-import.
_configured: bool = False


def _deployai_otlp_endpoint() -> str | None:
    """Collector base URL from ``DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT``, or None."""
    # Local import: settings pull in pydantic; keep this module importable
    # before the config package during early bootstrap.
    from control_plane.config.settings import get_settings

    endpoint = (get_settings().otel_exporter_otlp_endpoint or "").strip()
    return endpoint or None


def _wants_export() -> bool:
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    if _deployai_otlp_endpoint() is not None:
        return True
    return bool(
        (os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or "").strip()
        or (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
        or (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip(),
    )


def tracing_enabled() -> bool:
    """True when trace export is configured — gates the per-request middleware."""
    return _wants_export()


def _service_name() -> str:
    from control_plane.config.settings import get_settings

    # Stock env var wins for operators driving the SDK the standard way;
    # otherwise the DEPLOYAI_ setting (default "deployai-control-plane").
    return (os.environ.get("OTEL_SERVICE_NAME") or "").strip() or get_settings().otel_service_name


def configure_opentelemetry() -> None:
    """On OTLP config, install :class:`MeterProvider` + :class:`TracerProvider` with OTLP/HTTP export.

    Call as early as possible (before any :mod:`llm_provider_py` usage) so
    :func:`opentelemetry.metrics.get_meter` and :func:`opentelemetry.trace.get_tracer`
    bind to the SDK, not a no-op.
    """
    global _configured
    if _configured:
        return
    if not _wants_export():
        return

    instance_id = (os.environ.get("HOSTNAME") or os.environ.get("COMPUTERNAME") or "local").strip()
    resource = Resource.create(
        {
            "service.name": _service_name(),
            "service.instance.id": instance_id,
        },
    )
    deployai_base = _deployai_otlp_endpoint()
    interval = int((os.environ.get("OTEL_METRIC_EXPORT_INTERVAL") or "5000").strip() or "5000")
    if deployai_base is not None:
        base = deployai_base.rstrip("/")
        metric_exporter = OTLPMetricExporter(endpoint=f"{base}/v1/metrics")
        span_exporter = OTLPSpanExporter(endpoint=f"{base}/v1/traces")
    else:
        metric_exporter = OTLPMetricExporter()  # reads OTEL_EXPORTER_OTLP_* from the environment
        span_exporter = OTLPSpanExporter()
    reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=max(1_000, interval),
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=(reader,),
    )
    metrics.set_meter_provider(meter_provider)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    _configured = True
    _log.info(
        "OpenTelemetry SDK active (OTLP/HTTP; service=%s; metrics every %sms; traces batched)",
        _service_name(),
        interval,
    )


def shutdown_opentelemetry() -> None:
    global _configured
    meter_prov = metrics.get_meter_provider()
    meter_shutdown = getattr(meter_prov, "shutdown", None)
    if meter_shutdown is not None and callable(meter_shutdown):
        try:
            meter_shutdown()
        except Exception:
            _log.exception("OpenTelemetry meter provider shutdown failed")

    tracer_prov = trace.get_tracer_provider()
    tracer_shutdown = getattr(tracer_prov, "shutdown", None)
    if tracer_shutdown is not None and callable(tracer_shutdown):
        try:
            tracer_shutdown()
        except Exception:
            _log.exception("OpenTelemetry tracer provider shutdown failed")

    _configured = False
