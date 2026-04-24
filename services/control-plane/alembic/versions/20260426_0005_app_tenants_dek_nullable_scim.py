# expand-contract: expand (Story 2-5) — DEK material + optional SCIM token until provisioned.

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260426_0005"
down_revision: str | None = "20260425_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_tenants", sa.Column("tenant_dek_ciphertext", sa.Text(), nullable=True))
    op.add_column("app_tenants", sa.Column("tenant_dek_key_id", sa.Text(), nullable=True))
    op.alter_column("app_tenants", "scim_bearer_token_hash", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("app_tenants", "scim_bearer_token_hash", existing_type=sa.Text(), nullable=False)
    op.drop_column("app_tenants", "tenant_dek_key_id")
    op.drop_column("app_tenants", "tenant_dek_ciphertext")
