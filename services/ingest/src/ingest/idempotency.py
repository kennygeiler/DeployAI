"""Stable idempotency key for provider pulls (FR18, Story 3-6; at-most-once canonical writes)."""

from __future__ import annotations


def canonical_ingestion_dedup_key(*, provider: str, source_id: str, version: str) -> str:
    """Return a stable deduplication string ``<provider>:<source_id>:<version>``.

    Ingestion workers should use this (or a hash of it) to UPSERT or skip duplicate
    canonical rows when a provider or queue redelivers the same logical item.
    """
    p, s, v = (provider or "").strip(), (source_id or "").strip(), (version or "").strip()
    if not p or not s:
        raise ValueError("provider and source_id are required for ingestion dedup key")
    return f"{p}:{s}:{v}"
