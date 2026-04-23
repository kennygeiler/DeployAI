"""Fuzz-subtree fixtures.

Shares the `postgres_engine` container fixture from `tests/conftest.py`.
Adds the `deployai_app` LOGIN shim because the Story 1.9 migration
provisions the role NOLOGIN by design — ops enables LOGIN at deploy, and
the fuzz harness needs an app-role connection to hit RLS instead of being
stopped at role-level auth.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, text

_APP_USER = "deployai_app"
# Fuzz-run password. CI sets `FUZZ_APP_PASSWORD` directly via workflow env
# and the production-weight CLI test reads it; this fallback is for local
# `pytest -m fuzz` runs that don't bother exporting the env var.
_APP_PASSWORD = os.environ.get("FUZZ_APP_PASSWORD") or "deployai-fuzz-test"

_CANONICAL_TABLES: tuple[str, ...] = (
    "learning_lifecycle_states",
    "solidified_learnings",
    "identity_supersessions",
    "identity_attribute_history",
    "identity_nodes",
    "canonical_memory_events",
    "tombstones",
    "schema_proposals",
)


@pytest.fixture(scope="module", autouse=True)
def _configure_app_role_for_fuzz(postgres_engine: Engine) -> Generator[None]:
    """Enable LOGIN on `deployai_app` so the fuzz harness can authenticate as it."""
    with postgres_engine.begin() as conn:
        conn.execute(
            text(f"ALTER ROLE {_APP_USER} WITH LOGIN PASSWORD '{_APP_PASSWORD}'"),
        )
    yield


@pytest.fixture(autouse=True)
def _truncate_between_fuzz_tests(postgres_engine: Engine) -> Generator[None]:
    """TRUNCATE canonical-memory rows between fuzz tests.

    Without this, `run_fuzz` + `_seed` keeps piling rows onto a module-
    scoped container across tests, which (a) lets the weak
    `_fetch_row_ids` sanity check hide seed regressions from test 2
    onwards, and (b) can cause the production-weight test to collide
    with the fuzz-tenant-id pre-flight check if a prior test left rows
    behind. `session_replication_role='replica'` bypasses the
    append-only trigger on `canonical_memory_events` (the trigger is
    the system under test, not a harness obstacle).
    """
    yield

    with postgres_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in _CANONICAL_TABLES:
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))


@pytest.fixture()
def app_password() -> str:
    return _APP_PASSWORD


@pytest.fixture()
def app_user() -> str:
    return _APP_USER
