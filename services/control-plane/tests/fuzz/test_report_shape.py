"""Hermetic tests for the FuzzReport + Failure dataclasses (Story 1.10, AC5).

No DB, no harness run. Verifies the JSON shape and finalize() semantics are
stable — this is the contract the Epic-12 FOIA verifier parses.
"""

from __future__ import annotations

import json
from pathlib import Path

from control_plane.fuzz.report import Failure, FuzzReport, TableReport


def test_finalize_sets_totals_and_result_pass() -> None:
    report = FuzzReport(
        seed=1,
        started_at="2026-04-23T00:00:00+00:00",
        finished_at="2026-04-23T00:01:00+00:00",
        postgres_version="16.3",
        tenants=["t-a", "t-b"],
    )
    report.tables["canonical_memory_events"] = TableReport(
        seeded_rows_per_tenant=50,
        attempts_per_attack_class={"1": 80, "6": 100},
        failures=[],
        duration_ms=1234,
    )
    report.finalize()
    assert report.totals == {"attempts": 180, "failures": 0, "duration_ms": 1234}
    assert report.result == "pass"


def test_finalize_result_fail_when_any_failure() -> None:
    report = FuzzReport(
        seed=1,
        started_at="x",
        finished_at="y",
        postgres_version="16.3",
        tenants=[],
    )
    report.tables["identity_nodes"] = TableReport(
        seeded_rows_per_tenant=50,
        attempts_per_attack_class={"1": 1},
        failures=[
            Failure(
                attack_class=1,
                attack_name="baseline_rls_read",
                tenant_under_scope="a",
                leaked_tenant="b",
                table="identity_nodes",
                sql="SELECT ...",
                rows_returned=["(id, b)"],
            )
        ],
        duration_ms=50,
    )
    report.finalize()
    assert report.totals["failures"] == 1
    assert report.result == "fail"


def test_write_round_trips(tmp_path: Path) -> None:
    report = FuzzReport(
        seed=42,
        started_at="s",
        finished_at="f",
        postgres_version="16.3",
        tenants=["t-a"],
    )
    report.tables["canonical_memory_events"] = TableReport(
        seeded_rows_per_tenant=50,
        attempts_per_attack_class={"1": 10},
        failures=[],
        duration_ms=1,
    )
    report.finalize()
    out = tmp_path / "deep/nested/report.json"
    report.write(out)
    assert out.exists()
    parsed = json.loads(out.read_text())
    assert parsed["seed"] == 42
    assert parsed["result"] == "pass"
    assert parsed["totals"]["attempts"] == 10
