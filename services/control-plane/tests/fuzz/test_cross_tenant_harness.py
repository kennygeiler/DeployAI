"""Meta-tests for the cross-tenant fuzz harness itself (Story 1.10, AC10).

Two layers of protection against a silent harness regression:

1. `test_baseline_run_passes` — run the full harness against a correctly
   isolated schema and assert `result == "pass"`. This is the smoke test
   CI relies on.
2. `test_harness_detects_dropped_policy` — drop the RLS policy on one table,
   re-run, and assert `result == "fail"` **and** the failure record fingers
   the right table. This is the anti-test that proves the fuzzer is still
   doing its job — if a future refactor accidentally stubs out the attack
   loop, this test catches it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine, text

from control_plane.fuzz.cross_tenant import (
    CANONICAL_TABLES,
    FuzzConfig,
    _derive_app_url,
    run_fuzz,
)

pytestmark = [pytest.mark.fuzz, pytest.mark.integration]


def _derive_sync_root_url(postgres_engine: Engine) -> str:
    """The container's superuser URL as an async psycopg string."""
    raw = postgres_engine.url.render_as_string(hide_password=False)
    remainder = raw.split("@", 1)[1]
    # The base URL uses +psycopg (sync). Keep the same driver name for async —
    # psycopg v3 dispatches sync vs async on the SQLAlchemy engine type.
    return f"postgresql+psycopg://deployai:deployai-test@{remainder}"


def _small_config(postgres_engine: Engine, *, app_user: str, app_password: str, tmp_path: Path) -> FuzzConfig:
    """Downsized config so the meta-tests finish in ~20 s, not 10 min."""
    root_url = _derive_sync_root_url(postgres_engine)
    app_url = _derive_app_url(root_url, user=app_user, password=app_password)
    return FuzzConfig(
        seed=1234,
        database_url=root_url,
        app_database_url=app_url,
        report_path=tmp_path / "report.json",
        tenants=3,
        rows_per_tenant=5,  # AC minimum is 50; for the meta-test 5 is enough
        attempts_per_table=18,  # 3 per attack class, 6 classes
    )


def test_baseline_run_passes(postgres_engine: Engine, app_user: str, app_password: str, tmp_path: Path) -> None:
    """AC10(a): a correctly-isolated schema yields result=pass."""
    config = _small_config(postgres_engine, app_user=app_user, app_password=app_password, tmp_path=tmp_path)
    report = asyncio.run(run_fuzz(config))
    assert report.result == "pass", (
        f"baseline should pass, got {report.result}; "
        f"first failure: {report.tables[next(iter(report.tables))].failures[:1]}"
    )
    assert report.totals.get("failures") == 0
    # Every canonical table was exercised.
    assert set(report.tables.keys()) == set(CANONICAL_TABLES)
    # Every attack class got at least one attempt per table.
    for table_report in report.tables.values():
        # Attack class 3 (GUC override) is intentionally omitted — see
        # control_plane/fuzz/cross_tenant._fuzz_table docstring.
        assert set(table_report.attempts_per_attack_class.keys()) == {
            "1",
            "2",
            "4",
            "5",
            "6",
            "7",
        }


def test_harness_detects_disabled_rls(
    postgres_engine: Engine, app_user: str, app_password: str, tmp_path: Path
) -> None:
    """AC10(b): DISABLE ROW LEVEL SECURITY on one table → harness reports result=fail.

    Just dropping the policy would make reads return zero rows (no policy +
    FORCE RLS ⇒ deny-all). The actual "broken isolation" shape we need to
    catch is RLS fully off on a table, which is what a bad migration or an
    overzealous ops-fix might do. Restores RLS at teardown so subsequent
    tests see a healthy schema.
    """
    with postgres_engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE public.canonical_memory_events DISABLE ROW LEVEL SECURITY"),
        )
    try:
        config = _small_config(
            postgres_engine,
            app_user=app_user,
            app_password=app_password,
            tmp_path=tmp_path,
        )
        report = asyncio.run(run_fuzz(config))
        assert report.result == "fail", "harness missed RLS-disabled canonical_memory_events"
        events_report = report.tables["canonical_memory_events"]
        assert events_report.failures, "expected at least one failure on events"
        failure = events_report.failures[0]
        assert failure.table == "canonical_memory_events"
    finally:
        with postgres_engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE public.canonical_memory_events ENABLE ROW LEVEL SECURITY"),
            )
            conn.execute(
                text("ALTER TABLE public.canonical_memory_events FORCE ROW LEVEL SECURITY"),
            )


def test_report_written_to_disk(postgres_engine: Engine, app_user: str, app_password: str, tmp_path: Path) -> None:
    """AC5: JSON report is written at the declared path and is parseable."""
    import json

    config = _small_config(postgres_engine, app_user=app_user, app_password=app_password, tmp_path=tmp_path)
    report = asyncio.run(run_fuzz(config))
    report.write(config.report_path)
    assert config.report_path.exists()
    parsed = cast(dict[str, object], json.loads(config.report_path.read_text()))
    assert parsed["seed"] == config.seed
    assert parsed["result"] in {"pass", "fail"}
    assert "tables" in parsed
    assert "totals" in parsed
