"""Per-demo-session oracle conversation scoping (demo-polish fix 5).

# expand-contract: expand — one nullable column + index reshape.

Every demo guest authenticates as the single configured demo user, so the
``(tenant, engagement, actor)`` unique key made all guests share ONE chat
thread on the fixture engagements — each visitor saw previous visitors'
turns. ``oracle_conversations.demo_session_jti`` stamps a demo session's
access-token jti on its conversations (NULL for every normal session); the
lookup keys on it, so each demo mint gets a private thread.

The old three-column UNIQUE constraint becomes two partial unique indexes:

- ``demo_session_jti IS NULL``  → one conversation per (tenant, engagement,
  actor) — the pre-existing invariant for normal sessions, unchanged;
- ``demo_session_jti IS NOT NULL`` → one conversation per (tenant,
  engagement, actor, jti) — one private thread per demo session.

Two partial indexes (not one four-column UNIQUE) because Postgres treats
NULLs as distinct: a plain UNIQUE over the four columns would let normal
sessions accumulate duplicate rows.

The marker also gives the demo reaper a clean identification handle:
``demo_session_jti IS NOT NULL AND last_turn_at < now() - 24h`` bounds the
fixture engagements' conversation accumulation.

Revision ID: 20260814_0063
Revises: 20260813_0062
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0063"
down_revision: str | None = "20260813_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.add_column(
        "oracle_conversations",
        sa.Column("demo_session_jti", sa.Text(), nullable=True),
    )
    # Existing rows all have demo_session_jti NULL, so the partial unique
    # index over NULL rows is exactly the constraint being replaced — no
    # data backfill or dedup needed.
    op.execute(
        "ALTER TABLE public.oracle_conversations DROP CONSTRAINT uq_oracle_conversations_tenant_engagement_actor"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_oracle_conversations_tenant_engagement_actor "
        "ON public.oracle_conversations (tenant_id, engagement_id, actor_user_id) "
        "WHERE demo_session_jti IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_oracle_conversations_demo_session "
        "ON public.oracle_conversations (tenant_id, engagement_id, actor_user_id, demo_session_jti) "
        "WHERE demo_session_jti IS NOT NULL"
    )


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute("DROP INDEX IF EXISTS public.uq_oracle_conversations_demo_session")
    op.execute("DROP INDEX IF EXISTS public.uq_oracle_conversations_tenant_engagement_actor")
    # Demo-scoped rows would collide under the restored constraint — delete
    # them first (demo threads are disposable by definition).
    op.execute("DELETE FROM public.oracle_conversations WHERE demo_session_jti IS NOT NULL")
    op.execute(
        "ALTER TABLE public.oracle_conversations "
        "ADD CONSTRAINT uq_oracle_conversations_tenant_engagement_actor "
        "UNIQUE (tenant_id, engagement_id, actor_user_id)"
    )
    op.drop_column("oracle_conversations", "demo_session_jti")
