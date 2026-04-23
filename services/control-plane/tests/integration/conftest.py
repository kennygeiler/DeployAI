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


@pytest.fixture(autouse=True)
def _clean_tenant_rows(postgres_engine: Engine) -> Generator[None]:
    """Wipe canonical-memory rows between tests so each test owns a clean slate.

    Uses `session_replication_role='replica'` to temporarily bypass the
    `canonical_memory_events_append_only` trigger so DELETE is allowed
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
