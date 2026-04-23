"""Identity graph — canonical person nodes, attribute history, supersession.

Satisfies FR2 (one canonical person per node), FR3 (supersession link for
duplicate resolution), and DP11 (time-versioned role/title/email).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class IdentityNode(Base):
    """Canonical identity — one row per deduplicated person inside a tenant."""

    __tablename__ = "identity_nodes"

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
    canonical_name: Mapped[str] = mapped_column(nullable=False)
    primary_email_hash: Mapped[str] = mapped_column(nullable=False)
    is_canonical: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("true"),
    )

    __table_args__ = (Index("idx_identity_nodes_tenant_id", "tenant_id"),)


class IdentityAttributeHistory(Base):
    """Time-versioned attribute (role / title / email / display_name) for an identity.

    Exactly one open row (``valid_to IS NULL``) per ``(identity_id,
    attribute_name)`` pair — enforced by the partial-unique index
    ``uq_identity_attribute_history_open`` in migration 20260422_0001.
    """

    __tablename__ = "identity_attribute_history"

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
    identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_nodes.id"),
        nullable=False,
    )
    attribute_name: Mapped[str] = mapped_column(nullable=False)
    attribute_value: Mapped[str] = mapped_column(nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_identity_attribute_history_identity_valid",
            "identity_id",
            "attribute_name",
            text("valid_from DESC"),
        ),
    )


class IdentitySupersession(Base):
    """Supersession link: the superseded identity is resolved to the canonical one (FR3)."""

    __tablename__ = "identity_supersessions"

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
    superseded_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_nodes.id"),
        nullable=False,
    )
    canonical_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_nodes.id"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(nullable=False)
    authority_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "superseded_identity_id <> canonical_identity_id",
            name="different_ids",
        ),
        Index(
            "idx_identity_supersessions_tenant_superseded",
            "tenant_id",
            "superseded_identity_id",
        ),
    )
