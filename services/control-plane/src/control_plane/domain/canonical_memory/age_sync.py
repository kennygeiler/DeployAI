"""Apache AGE sync triggers for matrix_nodes and matrix_edges.

Houses the raw DDL strings used by alembic ``0043_apache_age`` to install
the AFTER INSERT/UPDATE/DELETE triggers that mirror canonical matrix writes
into the ``deployai_matrix`` AGE graph. Kept out of the migration file so
the SQL is reviewable in isolation and so future bugfixes can land here
without forcing a no-op migration revision.

The trigger bodies guard on ``pg_extension`` membership so a Postgres
instance without the AGE binary loaded (legacy testcontainer, certain
managed providers) silently no-ops the mirror — the canonical
``matrix_nodes`` / ``matrix_edges`` writes still commit. Production pg
images ship AGE; the no-op path is a fallback, not the contract.

AGE quirk: every session that touches the graph must run ``LOAD 'age'``
plus ``SET search_path = ag_catalog, "$user", public;`` before calling
``cypher(...)``. The migration sets these via ``ALTER DATABASE`` so the
preload happens automatically; the trigger also runs ``LOAD`` defensively
because ``ALTER DATABASE`` only affects *new* connections.
"""

from __future__ import annotations

GRAPH_NAME = "deployai_matrix"


NODE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION matrix_nodes_age_sync_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
DECLARE
    cypher_stmt text;
    safe_title text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    LOAD 'age';
    PERFORM set_config('search_path', 'ag_catalog,"$user",public', true);

    IF (TG_OP = 'DELETE') THEN
        cypher_stmt := format(
            'MATCH (n:matrix_node {id: %L}) DETACH DELETE n',
            OLD.id::text
        );
        EXECUTE format(
            'SELECT * FROM cypher(%L, $$%s$$) AS (n agtype)',
            'deployai_matrix',
            cypher_stmt
        );
        RETURN OLD;
    END IF;

    safe_title := replace(NEW.title, '''', '\\''');

    cypher_stmt := format(
        'MERGE (n:matrix_node {id: %L}) '
        || 'SET n.tenant_id = %L, '
        || '    n.engagement_id = %L, '
        || '    n.node_type = %L, '
        || '    n.title = %L',
        NEW.id::text,
        NEW.tenant_id::text,
        NEW.engagement_id::text,
        NEW.node_type,
        safe_title
    );
    EXECUTE format(
        'SELECT * FROM cypher(%L, $$%s$$) AS (n agtype)',
        'deployai_matrix',
        cypher_stmt
    );
    RETURN NEW;
END;
$fn$;
"""


EDGE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION matrix_edges_age_sync_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
DECLARE
    cypher_stmt text;
    edge_label text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    LOAD 'age';
    PERFORM set_config('search_path', 'ag_catalog,"$user",public', true);

    IF (TG_OP = 'DELETE') THEN
        cypher_stmt := format(
            'MATCH ()-[r {id: %L}]->() DELETE r',
            OLD.id::text
        );
        EXECUTE format(
            'SELECT * FROM cypher(%L, $$%s$$) AS (r agtype)',
            'deployai_matrix',
            cypher_stmt
        );
        RETURN OLD;
    END IF;

    -- Edge labels are limited to the curated MATRIX_EDGE_TYPES catalog
    -- (lowercased identifiers) so direct interpolation is safe.
    edge_label := lower(NEW.edge_type);

    IF (TG_OP = 'UPDATE') THEN
        cypher_stmt := format(
            'MATCH ()-[r {id: %L}]->() DELETE r',
            OLD.id::text
        );
        EXECUTE format(
            'SELECT * FROM cypher(%L, $$%s$$) AS (r agtype)',
            'deployai_matrix',
            cypher_stmt
        );
    END IF;

    cypher_stmt := format(
        'MATCH (a:matrix_node {id: %L}), (b:matrix_node {id: %L}) '
        || 'MERGE (a)-[r:%s {id: %L}]->(b) '
        || 'SET r.edge_type = %L, '
        || '    r.tenant_id = %L, '
        || '    r.engagement_id = %L',
        NEW.from_node_id::text,
        NEW.to_node_id::text,
        edge_label,
        NEW.id::text,
        NEW.edge_type,
        NEW.tenant_id::text,
        NEW.engagement_id::text
    );
    EXECUTE format(
        'SELECT * FROM cypher(%L, $$%s$$) AS (r agtype)',
        'deployai_matrix',
        cypher_stmt
    );
    RETURN NEW;
END;
$fn$;
"""


NODE_TRIGGER_ATTACH = """
DROP TRIGGER IF EXISTS matrix_nodes_age_sync ON matrix_nodes;
CREATE TRIGGER matrix_nodes_age_sync
AFTER INSERT OR UPDATE OR DELETE ON matrix_nodes
FOR EACH ROW EXECUTE FUNCTION matrix_nodes_age_sync_trigger();
"""


EDGE_TRIGGER_ATTACH = """
DROP TRIGGER IF EXISTS matrix_edges_age_sync ON matrix_edges;
CREATE TRIGGER matrix_edges_age_sync
AFTER INSERT OR UPDATE OR DELETE ON matrix_edges
FOR EACH ROW EXECUTE FUNCTION matrix_edges_age_sync_trigger();
"""


NODE_TRIGGER_DROP = """
DROP TRIGGER IF EXISTS matrix_nodes_age_sync ON matrix_nodes;
DROP FUNCTION IF EXISTS matrix_nodes_age_sync_trigger();
"""


EDGE_TRIGGER_DROP = """
DROP TRIGGER IF EXISTS matrix_edges_age_sync ON matrix_edges;
DROP FUNCTION IF EXISTS matrix_edges_age_sync_trigger();
"""
