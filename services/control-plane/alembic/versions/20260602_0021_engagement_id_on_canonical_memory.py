"""Phase 5 (increment 5.2a) — engagement_id on the canonical-memory tables.

# expand-contract: expand — additive nullable column + index per table; no
changes to existing columns.

The canonical-memory substrate is tenant-grained — it predates the
engagement entity. This resolves the tenant->engagement grain (the
long-deferred Phase 1 increment 3) so canonical events, identities, and
learnings can be scoped to one engagement within a team's tenant.

The column is **nullable** (the expand step): these tables have existing
fixture rows, and the NOT NULL flip waits until writers populate it. No
foreign key is attached — uniform across all seven tables, and
``canonical_memory_events`` is append-only (an ON DELETE CASCADE/SET NULL
would fight the ``canonical_memory_events_append_only`` trigger). This
mirrors the no-FK posture of ``tombstones.original_node_id``. See
``docs/product/deployment-matrix-model.md`` section 5.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0021"
down_revision: str | None = "20260601_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CANONICAL_TABLES: tuple[str, ...] = (
    "canonical_memory_events",
    "identity_nodes",
    "identity_attribute_history",
    "identity_supersessions",
    "solidified_learnings",
    "learning_lifecycle_states",
    "tombstones",
)


def upgrade() -> None:
    # expand-contract: expand
    for table in _CANONICAL_TABLES:
        op.add_column(table, sa.Column("engagement_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"idx_{table}_engagement_id", table, ["engagement_id"])


def downgrade() -> None:
    for table in _CANONICAL_TABLES:
        op.drop_index(f"idx_{table}_engagement_id", table_name=table)
        op.drop_column(table, "engagement_id")
