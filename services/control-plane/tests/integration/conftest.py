"""Integration-test fixtures: a real Postgres 16 + pgvector container.

Matches the production `infra/compose/postgres/Dockerfile` image base so
the schema runs against the same Postgres build the dev stack uses. The
container is module-scoped: each test module spins up one container and
tears it down on exit, cutting docker-pull overhead compared to a
function-scoped fixture.

Skips the whole module when Docker is not reachable — e.g. when a
developer runs ``pytest -m integration`` without Docker Desktop running.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from alembic import command

try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — pytest collector handles the skip below
    PostgresContainer = None  # type: ignore[assignment,misc]


_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _SERVICE_ROOT / "alembic.ini"
_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


def _docker_available() -> bool:
    """Best-effort probe for a reachable Docker daemon.

    Uses the ``docker`` Python SDK that testcontainers already pulls in.
    """

    try:  # pragma: no cover — guard for environments without docker
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine]:
    """Module-scoped engine bound to a fresh Postgres container."""

    if PostgresContainer is None:
        pytest.skip("testcontainers[postgres] not installed")
    if not _docker_available():
        pytest.skip("Docker daemon unreachable; integration tests require Docker")

    container = PostgresContainer(
        image=_PGVECTOR_IMAGE,
        username="deployai",
        password="deployai-test",
        dbname="deployai",
    )
    container.start()
    try:
        # testcontainers returns a psycopg2 URL by default on 4.x; normalize
        # to the modern psycopg (v3) driver name so SQLAlchemy 2.x picks the
        # driver we pin in pyproject.toml dev deps.
        raw_url = container.get_connection_url()
        sync_url = raw_url.replace("postgresql+psycopg2", "postgresql+psycopg")
        if "+psycopg" not in sync_url:
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1)

        _bootstrap_pgcrypto(sync_url)
        _run_alembic_upgrade(sync_url)

        engine = create_engine(sync_url, future=True)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        container.stop()


def _bootstrap_pgcrypto(sync_url: str) -> None:
    """Install pgcrypto so ``deployai_uuid_v7`` can call ``gen_random_bytes``.

    In production, this extension is installed by
    ``infra/compose/postgres/init/01-extensions.sql`` (Story 1.7) and by
    the RDS parameter-group bootstrap. The testcontainer starts from a
    bare pgvector image without that init script, so we run the
    equivalent ``CREATE EXTENSION`` here.
    """

    engine = create_engine(sync_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        engine.dispose()


def _run_alembic_upgrade(sync_url: str) -> None:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_SERVICE_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_tenant_rows(postgres_engine: Engine) -> Generator[None]:
    """Wipe canonical-memory rows between tests so each test owns a clean slate.

    Uses session_replication_role='replica' to temporarily bypass the
    ``canonical_memory_events_append_only`` trigger so DELETE is allowed
    during test teardown — the trigger is the system under test, not a
    test-harness obstacle.
    """

    yield

    with postgres_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in _TEARDOWN_ORDER:
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))


_TEARDOWN_ORDER: tuple[str, ...] = (
    "learning_lifecycle_states",
    "solidified_learnings",
    "identity_supersessions",
    "identity_attribute_history",
    "identity_nodes",
    "canonical_memory_events",
    "tombstones",
    "schema_proposals",
)


@pytest.fixture()
def tenant_id() -> Any:
    """A stable tenant id per test (UUID v7-looking sentinel)."""

    import uuid

    return uuid.UUID("00000000-0000-7000-8000-000000000001")
