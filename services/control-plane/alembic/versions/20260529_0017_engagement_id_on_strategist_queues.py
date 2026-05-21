"""Phase 1 — engagement_id on the strategist queue tables.

# expand-contract: expand — additive nullable FK column; no changes to
existing columns. Engagement-scopes the strategist operator queues from
``20260527_0015``. The column is nullable during the transition; the
internal API filters by it when supplied. See
``docs/product/deployai-source-of-truth-spec.md`` section 16 (Phase 1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260529_0017"
down_revision: str | None = "20260528_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_QUEUE_TABLES: tuple[str, ...] = (
    "strategist_action_queue_items",
    "strategist_validation_queue_items",
    "strategist_solidification_queue_items",
)


def upgrade() -> None:
    for table in _QUEUE_TABLES:
        op.add_column(table, sa.Column("engagement_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_engagement_id",
            table,
            "engagements",
            ["engagement_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"idx_{table}_engagement_id", table, ["engagement_id"])


def downgrade() -> None:
    for table in _QUEUE_TABLES:
        op.drop_index(f"idx_{table}_engagement_id", table_name=table)
        op.drop_constraint(f"fk_{table}_engagement_id", table, type_="foreignkey")
        op.drop_column(table, "engagement_id")
