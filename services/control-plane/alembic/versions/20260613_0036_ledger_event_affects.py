"""Phase F1.a — ledger_event_affects: polymorphic event→matrix-entity edges.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §3.3: records which matrix node, edge,
insight, or recommendation a ledger event touched. Polymorphic on
``entity_kind`` (no FK) so the same junction table covers all four entity
families without per-kind tables; tenant isolation is enforced by the parent
``ledger_events`` row, not here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0036"
down_revision: str | None = "20260613_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_event_affects",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_kind", sa.String(length=40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "entity_kind", "entity_id"),
    )
    op.create_index(
        "ix_ledger_affects_entity",
        "ledger_event_affects",
        ["entity_kind", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_affects_entity", table_name="ledger_event_affects")
    op.drop_table("ledger_event_affects")
