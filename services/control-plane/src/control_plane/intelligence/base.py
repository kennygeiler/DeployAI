"""Analyzer Protocol + TemporalInsightWrite dataclass (design §5.1)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

_INSIGHT_NAMESPACE = uuid.UUID("c4e7c4b3-8a4a-4f6f-9c8e-1e3f8a0b4c11")


@dataclass(slots=True)
class TemporalInsightWrite:
    """One insight to upsert. Idempotent via deterministic `id`."""

    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    insight_kind: str
    severity: str
    title: str
    narrative: str
    window_start: datetime
    window_end: datetime
    evidence_event_ids: list[uuid.UUID] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> uuid.UUID:
        """Deterministic id: SHA-256 of (kind, engagement, window) → UUIDv5 namespace."""
        key = "|".join(
            [
                self.insight_kind,
                str(self.engagement_id) if self.engagement_id is not None else "tenant",
                self.window_start.isoformat(),
                self.window_end.isoformat(),
            ]
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return uuid.uuid5(_INSIGHT_NAMESPACE, digest)


@runtime_checkable
class Analyzer(Protocol):
    """Pure, idempotent producer of temporal insights for a single window."""

    insight_kind: str
    default_window: timedelta

    async def run(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> list[TemporalInsightWrite]: ...
