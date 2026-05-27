"""v2 Phase 5.5 Wave A — pgvector embedding columns + enqueue queue.

# expand-contract: expand — adds one nullable ``embedding vector(1024)``
# column per source table (no rewrite, no backfill required at deploy),
# four HNSW indexes (built empty at migration time — cheap), one new
# ``embedding_jobs`` queue table, and per-table AFTER INSERT/UPDATE
# triggers that upsert into the queue. Downgrade reverses everything.

This Wave A lands the *schema only*. The Voyage-3 embedder worker that
drains ``embedding_jobs`` is Wave B; the ``vector_search`` tool that
queries the new HNSW indexes is Wave C. The columns and indexes are
created in this migration so Wave B can stream embeddings into them
the moment it lands without a follow-up migration.

See ``docs/agent-kenny/scope-v2.md`` §10 (Phase 5.5 — pgvector fuzzy
fallback) and ``docs/agent-kenny/ethos.md`` (vector search is the
*fallback* path, not the hot retrieval path).

Design notes
------------

- **Dimension (1024).** Voyage-3 returns 1024-dim embeddings. The
  column is fixed-width per pgvector requirement; widening later means a
  rewrite, so the dim is locked in here.
- **HNSW over IVFFlat.** HNSW does not require a training step or a
  rebuild after data lands, so the indexes can be created empty here
  and stay correct as Wave B backfills. Cosine ops (``vector_cosine_ops``)
  matches the similarity metric Voyage-3 is normalized for.
- **Queue table over LISTEN/NOTIFY.** A durable table survives worker
  crashes and Postgres restarts; the worker can resume by polling
  ``status = 'queued'`` ordered by ``created_at``. The unique
  ``(source_table, source_id)`` constraint ensures one job per row —
  an UPDATE that lands while a previous embed is still queued just
  bumps the existing row back to ``queued`` (handled by the trigger's
  ``ON CONFLICT … DO UPDATE``).
- **Trigger on INSERT and UPDATE.** Every mutation enqueues a fresh
  embedding job. This is intentionally aggressive — if the source
  text didn't change, the worker still re-embeds. Wave B may opt to
  short-circuit identical content via a content hash; that's a worker
  optimization and not a schema concern.
- **CASCADE from app_tenants.** Killing a tenant must also drain its
  pending embedding work; otherwise the worker would forever try to
  embed orphan rows. The FK ``ON DELETE CASCADE`` handles this
  declaratively.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0050"
down_revision: str | None = "20260613_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The four source tables that earn an ``embedding`` column. Names are
# load-bearing — they appear verbatim in the CHECK constraint on
# ``embedding_jobs.source_table`` and in the trigger names.
SOURCE_TABLES: tuple[str, ...] = (
    "ledger_events",
    "matrix_nodes",
    "oracle_chat_turns",
    "matrix_insights",
)

EMBEDDING_DIM = 1024

JOBS_TABLE = "embedding_jobs"

JOB_STATUSES: tuple[str, ...] = ("queued", "running", "done", "failed")


def upgrade() -> None:
    # 0042 sets the database-level search_path to ag_catalog,"$user",public
    # for new connections so AGE Cypher works without per-statement config.
    # Pin DDL to public so every object lands where the rest of the schema
    # lives.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    # ------------------------------------------------------------------
    # 1. pgvector extension (testcontainer bootstraps it pre-migrate; in
    #    production it's installed by infra/compose/postgres/init. Both
    #    paths use IF NOT EXISTS so this is idempotent.)
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # 2. embedding columns + HNSW indexes on each source table.
    # ------------------------------------------------------------------
    for table in SOURCE_TABLES:
        op.execute(f"ALTER TABLE public.{table} ADD COLUMN embedding vector({EMBEDDING_DIM})")
        # HNSW with cosine ops — matches Voyage-3's normalized similarity.
        # Index name pattern mirrors ``idx_<table>_<column>_hnsw`` used by
        # the surrounding migrations.
        op.execute(
            f"CREATE INDEX idx_{table}_embedding_hnsw ON public.{table} USING hnsw (embedding vector_cosine_ops)"
        )

    # ------------------------------------------------------------------
    # 3. embedding_jobs queue table.
    # ------------------------------------------------------------------
    op.create_table(
        JOBS_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source_table IN (" + ", ".join(f"'{t}'" for t in SOURCE_TABLES) + ")",
            name="ck_embedding_jobs_source_table",
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in JOB_STATUSES) + ")",
            name="ck_embedding_jobs_status",
        ),
        sa.UniqueConstraint(
            "source_table",
            "source_id",
            name="uq_embedding_jobs_source",
        ),
    )

    # Worker poll path: "give me the oldest queued jobs". Status + created_at
    # makes this an index-only scan when paging through the backlog.
    op.create_index(
        "idx_embedding_jobs_status_created_at",
        JOBS_TABLE,
        ["status", "created_at"],
    )

    # ------------------------------------------------------------------
    # 4. Enqueue trigger function + per-table AFTER INSERT/UPDATE triggers.
    #
    # The function is generic: it reads NEW.tenant_id (present on every
    # one of the four source tables — verified in the ORMs) and the
    # TG_TABLE_NAME to compose the upsert. On UPDATE we always reset to
    # 'queued' + attempts=0 so the worker re-embeds the freshest content;
    # ``content_hash`` short-circuiting is a Wave B optimization, not a
    # schema constraint.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION deployai_enqueue_embedding_job()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO public.embedding_jobs
                (tenant_id, source_table, source_id, status, attempts, updated_at)
            VALUES
                (NEW.tenant_id, TG_TABLE_NAME, NEW.id, 'queued', 0, now())
            ON CONFLICT (source_table, source_id) DO UPDATE
                SET status = 'queued',
                    attempts = 0,
                    last_error = NULL,
                    updated_at = now();
            RETURN NEW;
        END;
        $$;
        """
    )

    for table in SOURCE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_enqueue_embedding
            AFTER INSERT OR UPDATE ON public.{table}
            FOR EACH ROW EXECUTE FUNCTION deployai_enqueue_embedding_job();
            """
        )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")

    # 1. Drop triggers + function (function depends on no other objects, so
    #    once every trigger is gone the function can drop cleanly).
    for table in SOURCE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_enqueue_embedding ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS deployai_enqueue_embedding_job()")

    # 2. Drop the queue table (cascades the unique constraint + indexes).
    op.drop_table(JOBS_TABLE)

    # 3. Drop the embedding columns (cascades the HNSW indexes).
    for table in SOURCE_TABLES:
        op.execute(f"ALTER TABLE public.{table} DROP COLUMN IF EXISTS embedding")

    # 4. Leave the ``vector`` extension installed — other infra (test
    #    bootstrap, prod compose init) already assumes it's present, and a
    #    naked DROP EXTENSION here would race those.
