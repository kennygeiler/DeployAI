"""ORM: ledger_events + cause/affect edges + temporal_insights (Phase F1.a).

The ledger is an append-only, tenant-scoped log that consolidates every
existing surface (email/meeting ingest, matrix proposals + CRUD, audit
emits, oracle insights) into one queryable causal graph. See
``docs/design/timeline-ledger.md`` §3 for the schema and §4 for the write
path; the four migrations 0034-0037 ship the tables this module maps onto.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, PrimaryKeyConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class LedgerEvent(Base):
    """One immutable, timestamped row in the engagement causal timeline."""

    __tablename__ = "ledger_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    actor_kind: Mapped[str] = mapped_column(String(length=40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(length=200), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(length=80), nullable=False)
    source_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 500",
            name="ledger_summary_len",
        ),
        Index("ix_ledger_tenant_occurred", "tenant_id", text("occurred_at DESC")),
        Index(
            "ix_ledger_engagement_occurred",
            "engagement_id",
            text("occurred_at DESC"),
            postgresql_where=text("engagement_id IS NOT NULL"),
        ),
        Index("ix_ledger_source_kind", "source_kind"),
        Index("ix_ledger_actor", "actor_kind", "actor_id"),
        Index(
            "ix_ledger_detail_gin",
            "detail",
            postgresql_using="gin",
            postgresql_ops={"detail": "jsonb_path_ops"},
        ),
    )


class LedgerEventCause(Base):
    """Junction: ``event_id`` was caused by ``caused_by_id`` (both in ledger_events)."""

    __tablename__ = "ledger_event_causes"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    caused_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_events.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("event_id", "caused_by_id"),
        CheckConstraint("event_id != caused_by_id", name="ledger_event_causes_no_self_link"),
        Index("ix_ledger_cause_forward", "event_id"),
        Index("ix_ledger_cause_reverse", "caused_by_id"),
    )


class LedgerEventAffects(Base):
    """Junction: ledger event ``event_id`` touched matrix entity ``(entity_kind, entity_id)``."""

    __tablename__ = "ledger_event_affects"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_kind: Mapped[str] = mapped_column(String(length=40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("event_id", "entity_kind", "entity_id"),
        Index("ix_ledger_affects_entity", "entity_kind", "entity_id"),
    )


class TemporalInsight(Base):
    """A time-window-derived insight produced by an analyzer (Phase F intelligence layer)."""

    __tablename__ = "temporal_insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id"),
        nullable=True,
    )
    insight_kind: Mapped[str] = mapped_column(String(length=80), nullable=False)
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    title: Mapped[str] = mapped_column(String(length=200), nullable=False)
    narrative: Mapped[str] = mapped_column(Text(), nullable=False)
    window_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    evidence_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        server_default=text("'open'"),
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("window_end >= window_start", name="temporal_window_ordering"),
        CheckConstraint(
            "severity IN ('info','low','medium','high','critical')",
            name="temporal_severity_enum",
        ),
        CheckConstraint(
            "status IN ('open','acknowledged','dismissed','resolved','snoozed')",
            name="temporal_status_enum",
        ),
        Index(
            "ix_temporal_tenant_engagement",
            "tenant_id",
            "engagement_id",
            "status",
            "severity",
        ),
        Index("ix_temporal_kind", "insight_kind"),
        Index("ix_temporal_window", "window_start", "window_end"),
    )


# source_kind catalog — kept in lockstep with docs/design/timeline-ledger.md
# §4.3. The emitter (sibling slice F1.b) validates writes against this set.
LEDGER_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "email_ingest",
        "meeting_webhook",
        "manual_capture",
        "llm_proposal_created",
        "proposal_accepted",
        "proposal_rejected",
        "matrix_node_created",
        "matrix_node_updated",
        "matrix_node_deleted",
        "matrix_edge_created",
        "matrix_edge_deleted",
        "insight_opened",
        "insight_closed",
        "recommendation_emitted",
        "recommendation_actioned",
        "engagement_phase_change",
        "member_added",
        "member_removed",
        "settings_change",
        "audit_other",
    }
)

LEDGER_AFFECTS_ENTITY_KINDS: frozenset[str] = frozenset({"matrix_node", "matrix_edge", "insight", "recommendation"})

TEMPORAL_SEVERITIES: tuple[str, ...] = ("info", "low", "medium", "high", "critical")
TEMPORAL_STATUSES: tuple[str, ...] = ("open", "acknowledged", "dismissed", "resolved", "snoozed")

__all__ = [
    "LEDGER_AFFECTS_ENTITY_KINDS",
    "LEDGER_SOURCE_KINDS",
    "TEMPORAL_SEVERITIES",
    "TEMPORAL_STATUSES",
    "LedgerEvent",
    "LedgerEventAffects",
    "LedgerEventCause",
    "TemporalInsight",
]
