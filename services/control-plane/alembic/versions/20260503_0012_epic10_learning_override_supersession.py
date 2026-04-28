"""Epic 10 Story 10.1 — supersession link from solidified learnings to override events.

Adds nullable FK + evidence array on ``solidified_learnings`` populated when a
learning is moved to ``overridden`` so auditors can reach the canonical
``canonical_memory_events`` row (``event_type = 'override_event'``) and the
new evidence event IDs.

# expand-contract: expand
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260503_0012"
down_revision: str | None = "20260502_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "solidified_learnings",
        sa.Column(
            "supersession_override_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_memory_events.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "solidified_learnings",
        sa.Column(
            "superseding_evidence_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_solidified_learnings_supersession_override",
        "solidified_learnings",
        ["supersession_override_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_solidified_learnings_supersession_override", table_name="solidified_learnings")
    op.drop_column("solidified_learnings", "superseding_evidence_event_ids")
    op.drop_column("solidified_learnings", "supersession_override_event_id")
