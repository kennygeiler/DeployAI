"""Production-weight fuzz CLI smoke (Story 1.10, AC6/AC7).

This is the gate the CI workflow actually cares about. The meta-tests in
`test_cross_tenant_harness.py` validate the harness shape at reduced scale;
this test runs the CLI at AC-minimum scale against the same testcontainer,
writes the report to the canonical `artifacts/fuzz/cross-tenant-report.json`
path (so the workflow's `upload-artifact` step finds it), and asserts
`result == "pass"`.

Gated behind `FUZZ_GATE_MODE=production` so the default local `pytest -m
fuzz` loop (developer ergonomics) doesn't pay the 3-5 min cost. CI sets
the env var explicitly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine

from control_plane.fuzz.cross_tenant import main as fuzz_main

pytestmark = [pytest.mark.fuzz, pytest.mark.integration]


def _derive_async_root_url(postgres_engine: Engine) -> str:
    raw = postgres_engine.url.render_as_string(hide_password=False)
    return cast(str, raw).replace("postgresql+psycopg2", "postgresql+psycopg")


@pytest.mark.skipif(
    os.environ.get("FUZZ_GATE_MODE") != "production",
    reason="Production-weight CLI run; enable via FUZZ_GATE_MODE=production (CI sets this)",
)
def test_cli_production_run_against_testcontainer(
    postgres_engine: Engine,
    app_user: str,
    app_password: str,
) -> None:
    """Run the CLI at AC-minimum scale (3 tenants x 50 rows x 500 attempts/table x 8 tables).

    Writes to `services/control-plane/artifacts/fuzz/cross-tenant-report.json`
    so the workflow's `cross-tenant-report` artifact upload picks it up.
    """
    root_url = _derive_async_root_url(postgres_engine)

    report_dir = Path("artifacts") / "fuzz"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "cross-tenant-report.json"

    argv = [
        "--seed",
        os.environ.get("FUZZ_SEED", "20260423"),
        "--database-url",
        root_url,
        "--app-user",
        app_user,
        "--app-password",
        app_password,
        "--report",
        str(report_path),
    ]
    exit_code = fuzz_main(argv)
    assert report_path.exists(), f"CLI should have written report to {report_path}"
    assert exit_code == 0, (
        f"production-weight fuzz CLI returned exit={exit_code}; "
        f"see {report_path} for the failure record(s). stderr was captured by pytest."
    )
    parsed = cast(dict[str, object], json.loads(report_path.read_text()))
    assert parsed["result"] == "pass"
    totals = cast(dict[str, int], parsed["totals"])
    assert totals["attempts"] >= 4_000, f"AC3 requires >=500 attempts/table x 8 tables = 4000; got {totals['attempts']}"
    assert totals["failures"] == 0
