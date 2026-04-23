# expand-contract: expand (Story 1-17) — new columns for Cartographer review surface; non-breaking add-only.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260424_0003"
down_revision: str | None = "20260422_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("schema_proposals", sa.Column("proposer_agent", sa.Text(), nullable=True))
    op.add_column("schema_proposals", sa.Column("proposed_field_path", sa.Text(), nullable=True))
    op.add_column("schema_proposals", sa.Column("proposed_type", sa.Text(), nullable=True))
    op.add_column("schema_proposals", sa.Column("sample_evidence", JSONB(), nullable=True))
    op.add_column("schema_proposals", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    # expand-contract: contract
    op.drop_column("schema_proposals", "rejection_reason")
    op.drop_column("schema_proposals", "sample_evidence")
    op.drop_column("schema_proposals", "proposed_type")
    op.drop_column("schema_proposals", "proposed_field_path")
    op.drop_column("schema_proposals", "proposer_agent")
