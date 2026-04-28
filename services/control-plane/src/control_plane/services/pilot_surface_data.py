"""Tenant-scoped pilot digest/evidence payloads (Epic 16 vertical slice until canonical query APIs land)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def clear_pilot_surface_cache() -> None:
    _pilot_surface_document.cache_clear()


@lru_cache(maxsize=1)
def _pilot_surface_document() -> dict[str, Any]:
    raw = os.environ.get("DEPLOYAI_PILOT_SURFACE_DATA_PATH", "").strip()
    if not raw:
        return {"digests": {}, "evidence": {}}
    p = Path(raw)
    if not p.is_file():
        return {"digests": {}, "evidence": {}}
    try:
        with p.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"digests": {}, "evidence": {}}
    if not isinstance(doc, dict):
        return {"digests": {}, "evidence": {}}
    dig = doc.get("digests")
    ev = doc.get("evidence")
    if not isinstance(dig, dict):
        dig = {}
    if not isinstance(ev, dict):
        ev = {}
    return {"digests": dig, "evidence": ev}


def pilot_digest_items_for_tenant(tenant_id: str) -> list[Any] | None:
    """Return digest rows for tenant, or None if tenant has no mapped data (empty list = valid explicit empty)."""
    doc = _pilot_surface_document()
    dig = doc["digests"]
    if tenant_id not in dig:
        return None
    raw = dig[tenant_id]
    if not isinstance(raw, list):
        return None
    return raw


def pilot_evidence_item_for_tenant(tenant_id: str, node_id: str) -> dict[str, Any] | None:
    doc = _pilot_surface_document()
    ev = doc["evidence"]
    tmap = ev.get(tenant_id)
    if not isinstance(tmap, dict):
        return None
    item = tmap.get(node_id)
    if not isinstance(item, dict):
        return None
    return item
