"""v2 Phase 0a — Apache AGE extension + matrix sync trigger integration.

These tests need the locally-built ``deployai/postgres:local-dev`` image
because the upstream ``pgvector/pgvector:pg16`` base used by the default
``postgres_engine`` fixture has no AGE binary on disk. Build it once with
``docker compose -f infra/compose/docker-compose.yml build postgres``
(or simply ``make dev`` — the image lands as a side effect).

When the image is not available the suite skips, matching the same
"docker / artifact missing → skip" pattern used by the redis-backed
integration tests in this directory.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from alembic import command

try:
    import docker
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    docker = None  # type: ignore[assignment]
    PostgresContainer = None  # type: ignore[assignment,misc]

pytestmark = pytest.mark.integration


_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _SERVICE_ROOT / "alembic.ini"
_AGE_IMAGE = "deployai/postgres:local-dev"
_GRAPH = "deployai_matrix"


def _docker_available() -> bool:
    if docker is None:
        return False
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _image_available() -> bool:
    if not _docker_available():
        return False
    try:
        docker.from_env().images.get(_AGE_IMAGE)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def age_postgres_engine() -> Generator[Engine]:
    """Fresh AGE-enabled testcontainer with a clean schema upgrade.

    Module-scoped: building the AGE base image is expensive, and AGE
    requires an alembic upgrade from scratch (the default session-scoped
    ``postgres_engine`` runs against pgvector-only and has no graph).
    """

    if PostgresContainer is None:
        pytest.skip("testcontainers[postgres] not installed")
    if not _docker_available():
        pytest.skip("Docker daemon unreachable")
    if not _image_available():
        pytest.skip(
            f"{_AGE_IMAGE} not built locally; run `docker compose -f "
            "infra/compose/docker-compose.yml build postgres` first"
        )
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not in PATH")

    container = PostgresContainer(
        image=_AGE_IMAGE,
        username="deployai",
        password="deployai-test",
        dbname="deployai",
    )
    container.start()
    try:
        raw_url = container.get_connection_url()
        sync_url = raw_url.replace("postgresql+psycopg2", "postgresql+psycopg")
        if "+psycopg" not in sync_url:
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1)

        bootstrap = create_engine(sync_url, future=True)
        try:
            with bootstrap.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        finally:
            bootstrap.dispose()

        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("script_location", str(_SERVICE_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", sync_url)
        command.upgrade(cfg, "head")

        engine = create_engine(sync_url, future=True)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        container.stop()


def _age_session_setup(conn: Any) -> None:
    conn.execute(text("LOAD 'age'"))
    conn.execute(text('SET search_path = ag_catalog, "$user", public'))


def _seed_tenant_and_engagement(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> None:
    conn.execute(
        text(
            "INSERT INTO app_tenants (id, name, scim_bearer_token_hash) "
            "VALUES (:id, 'AGE Test Tenant', NULL) ON CONFLICT DO NOTHING"
        ),
        {"id": str(tenant_id)},
    )
    conn.execute(
        text(
            "INSERT INTO engagements (id, tenant_id, name) "
            "VALUES (:id, :tenant_id, 'AGE Engagement') ON CONFLICT DO NOTHING"
        ),
        {"id": str(engagement_id), "tenant_id": str(tenant_id)},
    )


def _insert_node(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str = "stakeholder",
    title: str = "Test Node",
) -> uuid.UUID:
    row = conn.execute(
        text(
            "INSERT INTO matrix_nodes "
            "  (tenant_id, engagement_id, node_type, title) "
            "VALUES (:t, :e, :nt, :ti) "
            "RETURNING id"
        ),
        {"t": tenant_id, "e": engagement_id, "nt": node_type, "ti": title},
    ).one()
    return row.id


def _insert_edge(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    edge_type: str,
    from_node_id: uuid.UUID,
    to_node_id: uuid.UUID,
) -> uuid.UUID:
    row = conn.execute(
        text(
            "INSERT INTO matrix_edges "
            "  (tenant_id, engagement_id, edge_type, from_node_id, to_node_id) "
            "VALUES (:t, :e, :et, :f, :to_id) "
            "RETURNING id"
        ),
        {
            "t": tenant_id,
            "e": engagement_id,
            "et": edge_type,
            "f": from_node_id,
            "to_id": to_node_id,
        },
    ).one()
    return row.id


def _count_graph_nodes(conn: Any, *, engagement_id: uuid.UUID) -> int:
    _age_session_setup(conn)
    sql = (
        f"SELECT count(*) AS c FROM cypher('{_GRAPH}', $$ "
        f"MATCH (n:matrix_node {{engagement_id: '{engagement_id}'}}) RETURN n "
        "$$) AS (n agtype)"
    )
    row = conn.execute(text(sql)).one()
    return int(row.c)


def test_migration_creates_age_graph(age_postgres_engine: Engine) -> None:
    with age_postgres_engine.connect() as conn:
        installed = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'age'")).scalar()
    assert installed == 1, "AGE extension should be installed by migration 0042"

    with age_postgres_engine.connect() as conn:
        _age_session_setup(conn)
        graph_row = conn.execute(
            text("SELECT name FROM ag_catalog.ag_graph WHERE name = :g"),
            {"g": _GRAPH},
        ).first()
    assert graph_row is not None, "deployai_matrix graph should exist"


def test_node_inserts_mirror_to_age(age_postgres_engine: Engine) -> None:
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()

    with age_postgres_engine.begin() as conn:
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_id)
        _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Alpha")
        _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Beta")
        _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Gamma")

    with age_postgres_engine.connect() as conn:
        assert _count_graph_nodes(conn, engagement_id=engagement_id) == 3


def test_edge_inserts_mirror_one_hop_traversal(age_postgres_engine: Engine) -> None:
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()

    with age_postgres_engine.begin() as conn:
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_id)
        from_id = _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Source")
        to_id = _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Target")
        _insert_edge(
            conn,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            edge_type="affects",
            from_node_id=from_id,
            to_node_id=to_id,
        )

    with age_postgres_engine.connect() as conn:
        _age_session_setup(conn)
        sql = (
            f"SELECT count(*) AS c FROM cypher('{_GRAPH}', $$ "
            f"MATCH (a:matrix_node {{id: '{from_id}', engagement_id: '{engagement_id}'}})"
            f"-[r]->(b:matrix_node {{id: '{to_id}', engagement_id: '{engagement_id}'}}) "
            "RETURN r "
            "$$) AS (r agtype)"
        )
        row = conn.execute(text(sql)).one()
    assert int(row.c) == 1, "one-hop traversal should find the affects edge"


def test_cross_engagement_isolation_in_cypher(age_postgres_engine: Engine) -> None:
    tenant_id = uuid.uuid4()
    engagement_a = uuid.uuid4()
    engagement_b = uuid.uuid4()

    with age_postgres_engine.begin() as conn:
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_a)
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_b)
        _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_a, title="EngA")
        _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_b, title="EngB")

    with age_postgres_engine.connect() as conn:
        a_count = _count_graph_nodes(conn, engagement_id=engagement_a)
        b_count = _count_graph_nodes(conn, engagement_id=engagement_b)

    assert a_count == 1, "engagement A should see exactly one node"
    assert b_count == 1, "engagement B should see exactly one node"


def test_update_propagates_title_change_to_age(age_postgres_engine: Engine) -> None:
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()

    with age_postgres_engine.begin() as conn:
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_id)
        node_id = _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Before")
        conn.execute(
            text("UPDATE matrix_nodes SET title = :t WHERE id = :id"),
            {"t": "After", "id": node_id},
        )

    with age_postgres_engine.connect() as conn:
        _age_session_setup(conn)
        sql = (
            f"SELECT n FROM cypher('{_GRAPH}', $$ "
            f"MATCH (n:matrix_node {{id: '{node_id}', engagement_id: '{engagement_id}'}}) "
            "RETURN n.title "
            "$$) AS (n agtype)"
        )
        row = conn.execute(text(sql)).one()
    # AGE returns agtype which renders the string with surrounding quotes
    assert "After" in str(row.n)


def test_delete_removes_vertex_from_age(age_postgres_engine: Engine) -> None:
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()

    with age_postgres_engine.begin() as conn:
        _seed_tenant_and_engagement(conn, tenant_id=tenant_id, engagement_id=engagement_id)
        node_id = _insert_node(conn, tenant_id=tenant_id, engagement_id=engagement_id, title="Doomed")

    with age_postgres_engine.connect() as conn:
        assert _count_graph_nodes(conn, engagement_id=engagement_id) == 1

    with age_postgres_engine.begin() as conn:
        conn.execute(text("DELETE FROM matrix_nodes WHERE id = :id"), {"id": node_id})

    with age_postgres_engine.connect() as conn:
        assert _count_graph_nodes(conn, engagement_id=engagement_id) == 0


def test_downgrade_drops_graph_and_extension(age_postgres_engine: Engine) -> None:
    """Migration 0042 down/up roundtrip must drop and recreate cleanly.

    We exercise the roundtrip at the end of the module to avoid leaving
    the schema in a partially-downgraded state for other tests in this
    module — every other test passes before this one runs because of
    pytest's default file-order execution.
    """

    raw_url = age_postgres_engine.url.render_as_string(hide_password=False)
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_SERVICE_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", raw_url)

    command.downgrade(cfg, "20260613_0041")
    with age_postgres_engine.connect() as conn:
        ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'age'")).scalar()
    assert ext is None, "AGE extension should be dropped on downgrade"

    command.upgrade(cfg, "head")
    with age_postgres_engine.connect() as conn:
        ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'age'")).scalar()
    assert ext == 1, "AGE extension should reinstall on upgrade"
