"""Shared fixtures: testcontainer Postgres + Alembic migrations.

Mirrors the CP integration conftest so the MCP server can exercise resources +
tools against a real database with the production schema applied. The MCP
service has no migrations of its own — it depends on CP's Alembic tree.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    PostgresContainer = None  # type: ignore[assignment,misc]


_CP_ROOT = Path(__file__).resolve().parents[2] / "control-plane"
_ALEMBIC_INI = _CP_ROOT / "alembic.ini"
_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


def _docker_available() -> bool:
    try:  # pragma: no cover
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine]:
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
    engine = create_engine(sync_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        engine.dispose()


def _run_alembic_upgrade(sync_url: str) -> None:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_CP_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_tenant_rows(postgres_engine: Engine) -> Generator[None]:
    yield
    with postgres_engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename NOT LIKE 'alembic_%' "
                "AND tablename NOT LIKE 'ag_%'"
            )
        )
        tables = [r[0] for r in result.all()]
        if tables:
            conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
            for t in tables:
                conn.execute(text(f'TRUNCATE TABLE "{t}" RESTART IDENTITY CASCADE'))


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def async_session(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncSession]:
    """One async session against the testcontainer DB for direct CRUD."""
    url = _async_url(postgres_engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mcp-test-key")
    from mcp_server.db import clear_engine_cache, get_session_factory

    clear_engine_cache()
    factory = get_session_factory()
    async with factory() as session:
        yield session
    clear_engine_cache()


def seed_tenant_with_engagement(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'mcp-tests')"),
            {"t": str(tid)},
        )
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase) VALUES (:e, :t, 'mcp-eng', 'P2_active')"
            ),
            {"e": str(eid), "t": str(tid)},
        )
    return tid, eid


def insert_api_key(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    name: str,
) -> tuple[uuid.UUID, str]:
    """Insert one tenant_api_keys row + return ``(id, raw_key)``."""
    from control_plane.domain.app_identity.api_keys import generate_raw_key, hash_raw_key

    raw = generate_raw_key()
    hashed = hash_raw_key(raw)
    key_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_api_keys (id, tenant_id, engagement_id, name, hashed_secret, scopes) "
                "VALUES (:i, :t, :e, :n, :h, ARRAY['read']::text[])"
            ),
            {
                "i": str(key_id),
                "t": str(tenant_id),
                "e": str(engagement_id) if engagement_id else None,
                "n": name,
                "h": hashed,
            },
        )
    return key_id, raw


__all__ = ["insert_api_key", "seed_tenant_with_engagement"]
