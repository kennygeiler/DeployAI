"""Shared fixtures for every test subtree under `services/control-plane/tests/`.

Lives at the `tests/` rootdir so both `tests/integration/` and `tests/fuzz/`
(Story 1.10) inherit the Postgres testcontainer fixture without having to
duplicate the container lifecycle or resort to non-top-level
`pytest_plugins` (deprecated since pytest 7).

Subtree-specific teardown (e.g. integration's autouse TRUNCATE between tests)
stays in the subtree conftest.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from alembic import command

try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    PostgresContainer = None  # type: ignore[assignment,misc]


_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = _SERVICE_ROOT / "alembic.ini"
_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


def _docker_available() -> bool:
    """Best-effort probe for a reachable Docker daemon."""
    try:  # pragma: no cover
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine]:
    """Module-scoped engine bound to a fresh Postgres 16 + pgvector container.

    Spun up once per test module, migrated to head, then yielded. Skips when
    Docker is unreachable so `pytest -m 'not integration and not fuzz'` stays
    clean on Docker-less dev boxes.
    """
    if PostgresContainer is None:
        pytest.skip("testcontainers[postgres] not installed")
    if not _docker_available():
        pytest.skip("Docker daemon unreachable; integration/fuzz tests require Docker")

    container = PostgresContainer(
        image=_PGVECTOR_IMAGE,
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

        _bootstrap_extensions(sync_url)
        _run_alembic_upgrade(sync_url)

        engine = create_engine(sync_url, future=True)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        container.stop()


def _bootstrap_extensions(sync_url: str) -> None:
    """Install pgcrypto + vector before migrations run.

    In production these extensions are installed by
    ``infra/compose/postgres/init/01-extensions.sql`` (Story 1.7) and the
    RDS parameter-group bootstrap; the testcontainer starts bare.
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
