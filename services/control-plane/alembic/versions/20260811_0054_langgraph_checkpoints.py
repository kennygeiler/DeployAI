"""Pilot-refresh D1 — LangGraph checkpoint tables for the Agent Kenny runtime.

# expand-contract: expand — four new tables; no changes to existing tables.

Creates the tables ``langgraph_checkpoint_postgres``'s ``AsyncPostgresSaver``
reads and writes (``checkpoints``, ``checkpoint_blobs``, ``checkpoint_writes``)
plus the library's own ``checkpoint_migrations`` version table. The DDL is the
library's ``BasePostgresSaver.MIGRATIONS`` sequence (langgraph-checkpoint-postgres
3.1.2) captured verbatim so the migrate-then-serve invariant holds: the app
process never runs the saver's runtime ``setup()``; schema always arrives via
Alembic before serving.

Two deliberate deviations from the captured sequence:

- ``CREATE INDEX CONCURRENTLY`` becomes plain ``CREATE INDEX`` — Alembic runs
  inside a transaction where CONCURRENTLY is illegal, and these are brand-new
  empty tables so there is no live traffic to avoid locking.
- The version rows 0..9 are pre-inserted into ``checkpoint_migrations`` so a
  stray runtime ``setup()`` call (e.g. from a notebook) is a no-op instead of
  re-running DDL.

Thread scoping: the runtime builds ``thread_id`` strings of the form
``tenant:{tenant_id}:engagement:{engagement_id}:conversation:{key}`` (see
``control_plane/agents/agent_kenny/runtime.py``), so tenant isolation is
carried in the key. These tables hold serialized graph state, not
tenant-queryable business rows, and are not RLS-scoped — access goes through
the saver with a fully-qualified thread_id only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0054"
down_revision: str | None = "20260811_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# BasePostgresSaver.MIGRATIONS (langgraph-checkpoint-postgres 3.1.2), flattened
# into the final DDL. Indexes 4 ("ALTER ... DROP NOT NULL") and 9 ("ADD COLUMN
# task_path") are folded into the CREATE TABLE statements; index 5 is a SELECT 1
# no-op; indexes 6-8 lose CONCURRENTLY (see module docstring).
_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS checkpoint_migrations (
        v INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        type TEXT,
        checkpoint JSONB NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoint_blobs (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL,
        version TEXT NOT NULL,
        type TEXT NOT NULL,
        blob BYTEA,
        PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        type TEXT,
        blob BYTEA NOT NULL,
        task_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
    )
    """,
    "CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
)

# Library migration indexes covered by the DDL above. setup() compares against
# MAX(v), so pre-seeding all of them makes a runtime setup() call a no-op.
_LIBRARY_MIGRATION_VERSIONS: tuple[int, ...] = tuple(range(10))


def upgrade() -> None:
    for stmt in _DDL:
        op.execute(sa.text(stmt))
    for v in _LIBRARY_MIGRATION_VERSIONS:
        op.execute(
            sa.text("INSERT INTO checkpoint_migrations (v) VALUES (:v) ON CONFLICT (v) DO NOTHING").bindparams(v=v)
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_writes"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_blobs"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoints"))
    op.execute(sa.text("DROP TABLE IF EXISTS checkpoint_migrations"))
