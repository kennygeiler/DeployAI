"""ORM: lint_flags — substrate integrity flags emitted by the lint worker.

Backed by the ``lint_flags`` table introduced in migration ``20260613_0044``.
The lint worker (``control_plane.workers.wiki_lint``) writes one row per
unresolved integrity issue; strategists + Kenny resolve them by setting
``resolved_at`` via ``/internal/v1/admin/lint/flags/{id}/resolve``.

See scope-v2 §4 and ethos §3.1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

LINT_FLAG_KINDS: tuple[str, ...] = (
    "contradiction",
    "stale",
    "orphan",
    "missing_cite",
    "broken_cite",
)
LINT_FLAG_TARGET_KINDS: tuple[str, ...] = (
    "matrix_insight",
    "matrix_node",
    "matrix_edge",
)


class LintFlag(Base):
    """One integrity flag raised by the lint worker for a single target row."""

    __tablename__ = "lint_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(nullable=False)
    target_kind: Mapped[str] = mapped_column(nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    flagged_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('contradiction','stale','orphan','missing_cite','broken_cite')",
            name="lint_flags_kind_check",
        ),
        Index(
            "lint_flags_open_by_engagement",
            "tenant_id",
            "engagement_id",
            "kind",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("lint_flags_target", "target_kind", "target_id"),
    )


__all__ = [
    "LINT_FLAG_KINDS",
    "LINT_FLAG_TARGET_KINDS",
    "LintFlag",
]
