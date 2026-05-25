"""Phase F1.a — ledger_event_causes: many-to-many causality edges.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §3.2: separate junction table so both
directions of the causal graph index efficiently (forward = "what did this
trigger", reverse = "what caused this"). Cascade on delete to keep edges
consistent if a ledger row is ever admin-deleted (Phase F4 soft-delete uses
``redacted_at`` instead; hard delete remains the admin escape hatch).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0035"
down_revision: str | None = "20260613_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_event_causes",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "caused_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", "caused_by_id"),
        sa.CheckConstraint("event_id != caused_by_id", name="ledger_event_causes_no_self_link"),
    )
    op.create_index("ix_ledger_cause_forward", "ledger_event_causes", ["event_id"])
    op.create_index("ix_ledger_cause_reverse", "ledger_event_causes", ["caused_by_id"])


def downgrade() -> None:
    op.drop_index("ix_ledger_cause_reverse", table_name="ledger_event_causes")
    op.drop_index("ix_ledger_cause_forward", table_name="ledger_event_causes")
    op.drop_table("ledger_event_causes")
