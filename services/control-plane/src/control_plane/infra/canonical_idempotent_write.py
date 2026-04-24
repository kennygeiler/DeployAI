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
) -> bool:
    """Return ``True`` if a new row was inserted, ``False`` if deduped (existing row for same key)."""
    ins = (
        insert(CanonicalMemoryEvent)
        .values(
            tenant_id=tenant_id,
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
