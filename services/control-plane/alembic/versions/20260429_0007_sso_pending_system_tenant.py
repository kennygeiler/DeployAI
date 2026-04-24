# System tenant for first-time OIDC logins (Story 2-2) until a Platform Admin assigns a real tenant.

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# uuid5(NAMESPACE_URL, "https://deployai.dev/system/sso-pending-tenant")
_SSO_PENDING_TENANT: str = "aa67db01-9627-57b8-86dc-8f01ab387fbf"

revision: str = "20260429_0007"
down_revision: str | None = "20260428_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable SCIM token (0005) allows placeholder rows. Literal UUID only (not user data).
    op.execute(
        f"INSERT INTO app_tenants (id, name, scim_bearer_token_hash) "
        f"VALUES ('{_SSO_PENDING_TENANT}'::uuid, 'SSO pending (system)', NULL) "
        f"ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM app_tenants WHERE id = '{_SSO_PENDING_TENANT}'::uuid")
