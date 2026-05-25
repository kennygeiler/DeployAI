"""Integration-subtree fixtures.

The Postgres testcontainer lifecycle lives in `tests/conftest.py` so the
fuzz subtree can share it (Story 1.10). This file keeps the autouse
TRUNCATE that the schema + isolation tests depend on between function-
scoped runs.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from control_plane.auth.sso_tenant import SSO_PENDING_TENANT_ID


@pytest.fixture(autouse=True)
def _ensure_sso_pending_tenant(postgres_engine: Engine) -> Generator[None]:
    """TRUNCATE removes the migration-seeded system tenant; restore before each test."""
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_tenants (id, name, scim_bearer_token_hash) "
                "VALUES (:id, 'SSO pending (system)', NULL) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(SSO_PENDING_TENANT_ID)},
        )
    yield


@pytest.fixture(autouse=True)
def _clean_tenant_rows(postgres_engine: Engine) -> Generator[None]:
    """Wipe every user-data row between tests so each test owns a clean slate.

    Discovers tables via `pg_tables` rather than a hand-rolled list so newly
    added migrations don't silently leak rows across tests. Uses
    `session_replication_role='replica'` to bypass the
    `canonical_memory_events_append_only` trigger (the trigger is the system
    under test, not a test-harness obstacle).
    """
    yield

    with postgres_engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename NOT LIKE 'alembic_%' "
                "AND tablename NOT LIKE 'pg_%'"
            )
        )
        tables = [row[0] for row in result]
        if not tables:
            return
        joined = ", ".join(tables)
        conn.execute(text("SET session_replication_role = 'replica'"))
        conn.execute(text(f"TRUNCATE TABLE {joined} CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))


@pytest.fixture()
def tenant_id() -> Any:
    """A stable tenant id per test (UUID v7-looking sentinel)."""
    import uuid

    return uuid.UUID("00000000-0000-7000-8000-000000000001")
