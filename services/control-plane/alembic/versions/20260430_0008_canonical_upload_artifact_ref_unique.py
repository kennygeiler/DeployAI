"""Partial unique (tenant, source_ref) for upload.artifact idempotency (Story 3-4)."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260430_0008"
down_revision: str | None = "20260429_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Story 3-4: idempotent /complete under concurrency (one row per source_ref per tenant).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_canonical_memory_events_tenant_upload_transcript
        ON canonical_memory_events (tenant_id, source_ref)
        WHERE event_type = 'upload.transcript' AND source_ref IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_canonical_memory_events_tenant_upload_transcript;")
