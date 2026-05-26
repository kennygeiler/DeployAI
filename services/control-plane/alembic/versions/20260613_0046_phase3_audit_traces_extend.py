"""v2 Phase 3 — agent_audit_traces extension for structured concerns + verified counter.

# expand-contract: expand — additive columns with safe defaults, no
# changes to existing rows or constraints.

Two new columns on ``agent_audit_traces``:

- ``adversarial_concerns_text`` (jsonb, default ``'[]'``) — structured
  ``AdversarialConcern[]`` payload from the Phase 3 reviewer so the
  hallucination dashboard can render concern severity inline without
  re-aggregating across ledger rows.
- ``verified_concerns_count`` (int, default 0) — number of concerns that
  did NOT cross the keyword severity bar (``info`` only); used by the
  dashboard's noise-floor card. See scope-v2 §7.5.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0046"
down_revision: str | None = "20260613_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.add_column(
        "agent_audit_traces",
        sa.Column(
            "adversarial_concerns_text",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "agent_audit_traces",
        sa.Column(
            "verified_concerns_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.drop_column("agent_audit_traces", "verified_concerns_count")
    op.drop_column("agent_audit_traces", "adversarial_concerns_text")
