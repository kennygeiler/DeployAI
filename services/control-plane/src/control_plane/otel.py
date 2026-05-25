"""OpenTelemetry metrics + traces SDK wiring with OTLP/HTTP export."""

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


def _wants_export() -> bool:
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    return bool(
        (os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or "").strip()
        or (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
        or (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip(),
    )


def configure_opentelemetry() -> None:
    """On OTLP env, install :class:`MeterProvider` + :class:`TracerProvider` with OTLP/HTTP export.

    Call as early as possible (before any :mod:`llm_provider_py` usage) so
    :func:`opentelemetry.metrics.get_meter` and :func:`opentelemetry.trace.get_tracer`
    bind to the SDK, not a no-op.
    """
    global _configured
    if _configured:
        return
    if not _wants_export():
        return

    service_name = (os.environ.get("OTEL_SERVICE_NAME") or "deployai-control-plane").strip()
    instance_id = (os.environ.get("HOSTNAME") or os.environ.get("COMPUTERNAME") or "local").strip()
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.instance.id": instance_id,
        },
    )
    interval = int((os.environ.get("OTEL_METRIC_EXPORT_INTERVAL") or "5000").strip() or "5000")
    metric_exporter = OTLPMetricExporter()  # reads OTEL_EXPORTER_OTLP_* from the environment
    reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=max(1_000, interval),
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=(reader,),
    )
    metrics.set_meter_provider(meter_provider)

    span_exporter = OTLPSpanExporter()
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    _configured = True
    _log.info(
        "OpenTelemetry SDK active (OTLP/HTTP; service=%s; metrics every %sms; traces batched)",
        service_name,
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
