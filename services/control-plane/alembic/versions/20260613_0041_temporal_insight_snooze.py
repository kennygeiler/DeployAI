"""Phase G4.b — temporal_insights snooze: add snoozed_until + 'snoozed' status.

# expand-contract: expand — additive column + widened CHECK; no data loss.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0041"
down_revision: str | None = "20260613_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "temporal_insights",
        sa.Column("snoozed_until", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.drop_constraint("temporal_status_enum", "temporal_insights", type_="check")
    op.create_check_constraint(
        "temporal_status_enum",
        "temporal_insights",
        "status IN ('open','acknowledged','dismissed','resolved','snoozed')",
    )


def downgrade() -> None:
    op.execute("UPDATE temporal_insights SET status = 'open' WHERE status = 'snoozed'")
    op.drop_constraint("temporal_status_enum", "temporal_insights", type_="check")
    op.create_check_constraint(
        "temporal_status_enum",
        "temporal_insights",
        "status IN ('open','acknowledged','dismissed','resolved')",
    )
    op.drop_column("temporal_insights", "snoozed_until")
