"""Phase 4 (increment 4.3) — author_role on engagement_log_entries.

# expand-contract: expand — one additive nullable column; no backfill.

Records the team role (fde / deployment_strategist / biz_dev) of whoever
logged the entry, captured at write time. Backs the role lenses and the
cross-role activity breakdown on the engagement detail page. Nullable:
entries written before this migration have no recorded role. See
``docs/product/deployai-source-of-truth-spec.md`` section 16 (Phase 4).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260531_0019"
down_revision: str | None = "20260530_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engagement_log_entries",
        sa.Column("author_role", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("engagement_log_entries", "author_role")
