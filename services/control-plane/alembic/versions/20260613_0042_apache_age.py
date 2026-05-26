"""v2 Phase 0a — Apache AGE extension + matrix sync triggers.

# expand-contract: expand — additive extension + new triggers; no schema
# changes to existing matrix_nodes / matrix_edges rows or columns.

Installs the Apache AGE extension (when the binary is available on the pg
host) and creates a single ``deployai_matrix`` graph that mirrors writes
on ``matrix_nodes`` and ``matrix_edges`` via AFTER triggers. Tenant +
engagement isolation is enforced *inside* the graph by property filter,
not by separate graphs — there is one graph per cluster, and every node
+ edge carries ``tenant_id`` and ``engagement_id`` properties that every
Cypher query must filter on.

AGE quirk: every session that touches the graph must run::

    LOAD 'age';
    SET search_path = ag_catalog, "\\$user", public;

before invoking the ``cypher(...)`` function. The migration alters the
database default ``search_path`` so future sessions get this for free;
the trigger bodies also issue ``LOAD 'age'`` defensively because
``ALTER DATABASE`` only affects *new* connections.

Testcontainer fallback: the upstream ``pgvector/pgvector:pg16`` image has
no AGE binary on disk. ``CREATE EXTENSION age`` then errors with
``ERROR: extension "age" is not available``. The migration wraps the
extension + graph creation in a DO block that catches that class of
error and continues without installing the graph — the triggers
themselves no-op when ``pg_extension`` lacks ``age``, so the legacy
testcontainer alembic upgrade still succeeds.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from control_plane.domain.canonical_memory.age_sync import (
    EDGE_TRIGGER_ATTACH,
    EDGE_TRIGGER_DROP,
    EDGE_TRIGGER_FN,
    GRAPH_NAME,
    NODE_TRIGGER_ATTACH,
    NODE_TRIGGER_DROP,
    NODE_TRIGGER_FN,
)

revision: str = "20260613_0042"
down_revision: str | None = "20260613_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INSTALL_AGE = f"""
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS age;
    EXCEPTION
        WHEN feature_not_supported THEN
            RAISE WARNING 'Apache AGE binary not available; skipping extension + graph install';
            RETURN;
        WHEN undefined_file THEN
            RAISE WARNING 'Apache AGE binary not available; skipping extension + graph install';
            RETURN;
    END;

    LOAD 'age';
    PERFORM set_config('search_path', 'ag_catalog,"$user",public', true);

    IF NOT EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph WHERE name = '{GRAPH_NAME}'
    ) THEN
        PERFORM ag_catalog.create_graph('{GRAPH_NAME}');
    END IF;
END
$$;
"""


_UNINSTALL_AGE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
        RETURN;
    END IF;
    LOAD 'age';
    PERFORM set_config('search_path', 'ag_catalog,"$user",public', true);

    IF EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = '{GRAPH_NAME}') THEN
        PERFORM ag_catalog.drop_graph('{GRAPH_NAME}', true);
    END IF;
    DROP EXTENSION IF EXISTS age;
END
$$;
"""


def upgrade() -> None:
    op.execute(_INSTALL_AGE)
    op.execute(NODE_TRIGGER_FN)
    op.execute(EDGE_TRIGGER_FN)
    op.execute(NODE_TRIGGER_ATTACH)
    op.execute(EDGE_TRIGGER_ATTACH)


def downgrade() -> None:
    op.execute(EDGE_TRIGGER_DROP)
    op.execute(NODE_TRIGGER_DROP)
    op.execute(_UNINSTALL_AGE)
