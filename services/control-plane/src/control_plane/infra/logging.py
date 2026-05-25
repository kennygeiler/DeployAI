"""Process-wide logging setup. ``LOG_FORMAT=json`` switches to one-line JSON records."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from control_plane.infra.request_context import request_id_var

_STANDARD_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record. Extra fields passed via ``extra={...}`` are merged in."""

    def format(self, record: logging.LogRecord) -> str:
        # strftime doesn't understand %03d, so build the millis suffix manually
        # from record.msecs (set by the logging module).
        base_ts = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        millis = f".{int(record.msecs):03d}"
        tz_suffix = self.formatTime(record, "%z")
        payload: dict[str, Any] = {
            "ts": f"{base_ts}{millis}{tz_suffix}",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        request_id = request_id_var.get()
        if request_id is not None:
            payload.setdefault("request_id", request_id)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter that prefixes ``[req=<short>]`` when a request id is in scope."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = request_id_var.get()
        if request_id is None:
            return base
        return f"[req={request_id[:8]}] {base}"


def configure_logging() -> None:
    """Install a single stream handler on the root logger. Idempotent across imports."""
    fmt = (os.environ.get("LOG_FORMAT") or "text").strip().lower()
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for existing in list(root.handlers):
        if getattr(existing, "_deployai_managed", False):
            root.removeHandler(existing)

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler._deployai_managed = True  # type: ignore[attr-defined]
    root.addHandler(handler)
