"""Dispatch for JSON Schema tool definitions (Epic 5, Story 5.3)."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_tool_schema(name: str) -> dict[str, Any]:
    f = resources.files("deployai_runtime").joinpath("tools_data", f"{name}.json")
    return json.loads(f.read_text(encoding="utf-8"))


def handle_describe_entity(node_id: str) -> dict[str, str]:
    return {"node_id": node_id, "label": f"entity:{node_id[:8]}", "ok": "true"}
