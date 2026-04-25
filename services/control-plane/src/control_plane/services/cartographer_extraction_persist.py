"""Persist Cartographer :class:`ExtractionBundle` as an append-only canonical event (Epic 6, Story 6-2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup

CARTOGRAPHER_EXTRACTION_TYPE = "cartographer.extraction"
PAYLOAD_SCHEMA_VERSION = "0.1.0"


def ingestion_dedup_key(*, source_event_id: uuid.UUID, fingerprint: str) -> str:
    """Idempotent re-run of the same logical extraction (FR18 at-most-once)."""
    return f"cartographer:extraction:{source_event_id}:{fingerprint}"


async def persist_cartographer_extraction(
    t_sess: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_event_id: uuid.UUID,
    extraction_payload: dict[str, Any],
    fingerprint: str,
) -> bool:
    """Insert a ``cartographer.extraction`` row. Returns whether a new row was written.

    Callers should pass ``extraction_payload`` as JSON-serializable (from
    :func:`cartographer.extract.extraction_bundle_to_persist_dict`).
    """
    body = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "source_event_id": str(source_event_id),
        "fingerprint": fingerprint,
        "extraction": extraction_payload,
    }
    return await try_insert_with_ingestion_dedup(
        t_sess,
        tenant_id=tenant_id,
        event_type=CARTOGRAPHER_EXTRACTION_TYPE,
        occurred_at=datetime.now(UTC),
        source_ref=f"cartographer:source_event:{source_event_id}",
        payload=body,
        ingestion_dedup_key=ingestion_dedup_key(source_event_id=source_event_id, fingerprint=fingerprint),
    )
