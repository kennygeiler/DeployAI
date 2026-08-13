"""FR18: insert canonical memory rows with ``ingestion_dedup_key`` (at-most-once under redelivery)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent


async def try_insert_with_ingestion_dedup(
    t_sess: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    source_ref: str | None,
    payload: dict[str, Any],
    ingestion_dedup_key: str,
    engagement_id: uuid.UUID | None = None,
) -> bool:
    """Return ``True`` if a new row was inserted, ``False`` if deduped (existing row for same key).

    ``engagement_id`` is optional: provider-pull writers (M365/Gmail/Slack)
    land tenant-scoped events and omit it; engagement-scoped writers (email
    intake, Wave 5 IN1) pass it so the extraction chain can find the event.
    """
    ins = (
        insert(CanonicalMemoryEvent)
        .values(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            event_type=event_type,
            occurred_at=occurred_at,
            source_ref=source_ref,
            payload=payload,
            evidence_span={},
            ingestion_dedup_key=ingestion_dedup_key,
        )
        .on_conflict_do_nothing(
            index_elements=[CanonicalMemoryEvent.tenant_id, CanonicalMemoryEvent.ingestion_dedup_key],
            index_where=CanonicalMemoryEvent.ingestion_dedup_key.isnot(None),
        )
        .returning(CanonicalMemoryEvent.id)
    )
    r = await t_sess.execute(ins)
    row = r.fetchone()
    return row is not None


async def insert_snapshot_with_ingestion_dedup(
    t_sess: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    event_type: str,
    occurred_at: datetime,
    source_ref: str | None,
    payload: dict[str, Any],
    ingestion_dedup_key: str,
) -> uuid.UUID | None:
    """Engagement-scoped sibling of :func:`try_insert_with_ingestion_dedup`.

    Returns the new event id, or ``None`` when deduped. Used by snapshot
    batchers (SL1 Slack flush) that need the id to chain extraction.
    """
    ins = (
        insert(CanonicalMemoryEvent)
        .values(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            event_type=event_type,
            occurred_at=occurred_at,
            source_ref=source_ref,
            payload=payload,
            evidence_span={},
            ingestion_dedup_key=ingestion_dedup_key,
        )
        .on_conflict_do_nothing(
            index_elements=[CanonicalMemoryEvent.tenant_id, CanonicalMemoryEvent.ingestion_dedup_key],
            index_where=CanonicalMemoryEvent.ingestion_dedup_key.isnot(None),
        )
        .returning(CanonicalMemoryEvent.id)
    )
    r = await t_sess.execute(ins)
    row = r.fetchone()
    return row[0] if row is not None else None
