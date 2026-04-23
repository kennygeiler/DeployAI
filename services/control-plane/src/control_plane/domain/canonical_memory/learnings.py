"""Solidified-learning library + lifecycle-state log.

The lifecycle state is a Postgres enum (``learning_state_t``) created in
migration ``20260422_0001``. Transitions are tracked append-only in
``learning_lifecycle_states`` so the library's history is reconstructable
without mutating ``solidified_learnings`` in place.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class LearningState(StrEnum):
    """Lifecycle states for a solidified learning (epic AC literal set)."""

    CANDIDATE = "candidate"
    SOLIDIFIED = "solidified"
    OVERRIDDEN = "overridden"
    TOMBSTONED = "tombstoned"


LEARNING_STATES: tuple[str, ...] = tuple(s.value for s in LearningState)


_learning_state_enum = SAEnum(
    LearningState,
    name="learning_state_t",
    values_callable=lambda members: [m.value for m in members],
    native_enum=True,
    create_type=False,
)


class SolidifiedLearning(Base):
    """A first-class learning: belief + evidence + application trigger + state."""

    __tablename__ = "solidified_learnings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    belief: Mapped[str] = mapped_column(nullable=False)
    evidence_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
    )
    application_trigger: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    state: Mapped[LearningState] = mapped_column(
        _learning_state_enum,
        nullable=False,
        server_default=text("'candidate'"),
    )

    __table_args__ = (Index("idx_solidified_learnings_tenant_id", "tenant_id"),)


class LearningLifecycleState(Base):
    """Append-only transition log for a solidified learning."""

    __tablename__ = "learning_lifecycle_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    learning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("solidified_learnings.id"),
        nullable=False,
    )
    state: Mapped[LearningState] = mapped_column(_learning_state_enum, nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "idx_learning_lifecycle_states_learning",
            "learning_id",
            text("transitioned_at DESC"),
        ),
    )
