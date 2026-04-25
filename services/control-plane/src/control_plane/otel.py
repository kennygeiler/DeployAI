"""OpenTelemetry metrics SDK + OTLP HTTP exporter (e.g. ``llm_provider_py`` token counters)."""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

_log = logging.getLogger(__name__)


def _wants_export() -> bool:
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    return bool(
        (os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or "").strip()
        or (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip(),
    )


def configure_opentelemetry() -> None:
    """On OTLP env, install :class:`MeterProvider` with periodic OTLP/HTTP export.

    Call as early as possible (before any :mod:`llm_provider_py` usage) so
    :func:`opentelemetry.metrics.get_meter` binds to the SDK, not a no-op.
    """
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
    exporter = OTLPMetricExporter()  # reads OTEL_EXPORTER_OTLP_* from the environment
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=max(1_000, interval),
    )
    provider = MeterProvider(
        resource=resource,
        metric_readers=(reader,),
    )
    metrics.set_meter_provider(provider)
    _log.info(
        "OpenTelemetry SDK metrics active (OTLP/HTTP; service=%s; export every %sms)",
        service_name,
        interval,
    )


def shutdown_opentelemetry() -> None:
    prov = metrics.get_meter_provider()
    fn = getattr(prov, "shutdown", None)
    if fn is not None and callable(fn):
        try:
            fn()
        except Exception:
            _log.exception("OpenTelemetry meter provider shutdown failed")
