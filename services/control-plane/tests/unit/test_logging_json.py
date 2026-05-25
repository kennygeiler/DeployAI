"""``LOG_FORMAT=json`` produces parseable JSON records with the documented fields."""

from __future__ import annotations

import importlib
import io
import json
import logging
from collections.abc import Generator
from types import ModuleType

import pytest


@pytest.fixture(autouse=True)
def _reset_root_handlers() -> Generator[None]:
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    root.handlers.clear()
    yield
    root.handlers.clear()
    for h in saved:
        root.addHandler(h)
    root.setLevel(saved_level)


def _reload_logging_module() -> ModuleType:
    import control_plane.infra.logging as mod

    return importlib.reload(mod)


def test_json_format_emits_one_object_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    mod = _reload_logging_module()
    mod.configure_logging()

    buffer = io.StringIO()
    handler = logging.StreamHandler(stream=buffer)
    handler.setFormatter(mod.JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    logger = logging.getLogger("test.json")
    logger.info("hello world", extra={"tenant": "t-1", "count": 7})

    raw = buffer.getvalue().strip()
    assert raw, "expected at least one JSON line"
    payload = json.loads(raw.splitlines()[0])
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json"
    assert payload["tenant"] == "t-1"
    assert payload["count"] == 7
    assert "ts" in payload


def test_text_format_default_does_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    mod = _reload_logging_module()
    mod.configure_logging()

    root = logging.getLogger()
    assert root.handlers, "configure_logging must install a handler"
    formatter = root.handlers[-1].formatter
    assert not isinstance(formatter, mod.JsonFormatter)


def test_json_format_includes_request_id_when_context_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    mod = _reload_logging_module()
    mod.configure_logging()

    from control_plane.infra.request_context import request_id_var

    buffer = io.StringIO()
    handler = logging.StreamHandler(stream=buffer)
    handler.setFormatter(mod.JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    token = request_id_var.set("11111111-2222-3333-4444-555555555555")
    try:
        logging.getLogger("test.req").info("scoped log")
    finally:
        request_id_var.reset(token)

    payload = json.loads(buffer.getvalue().splitlines()[0])
    assert payload["request_id"] == "11111111-2222-3333-4444-555555555555"
    assert payload["message"] == "scoped log"


def test_json_format_omits_request_id_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    mod = _reload_logging_module()
    mod.configure_logging()

    from control_plane.infra.request_context import request_id_var

    buffer = io.StringIO()
    handler = logging.StreamHandler(stream=buffer)
    handler.setFormatter(mod.JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    assert request_id_var.get() is None
    logging.getLogger("test.req").info("ambient log")

    payload = json.loads(buffer.getvalue().splitlines()[0])
    assert "request_id" not in payload
