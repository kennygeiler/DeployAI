"""Structured JSON report for cross-tenant isolation fuzz runs (Story 1.10, AC5).

The report shape is deliberately boring: flat dataclasses, `dataclasses.asdict`,
`json.dumps`. No pydantic, no attrs — keeping this dep-free means the Epic-12
FOIA CLI can re-parse it with stdlib only, and the shape is stable enough to be
a long-lived contract.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Failure:
    """One offending cross-tenant observation.

    `rows_returned` is capped at a small preview (first 3 rows, each row's
    values stringified) — the full rowset is never persisted to avoid leaking
    real tenant data into an audit artifact. The triage flow in
    `docs/security/cross-tenant-fuzz.md` walks operators through how to
    reproduce locally if they need the full rowset.
    """

    attack_class: int
    attack_name: str
    tenant_under_scope: str
    leaked_tenant: str
    table: str
    sql: str
    rows_returned: list[str]


@dataclass
class TableReport:
    seeded_rows_per_tenant: int
    attempts_per_attack_class: dict[str, int] = field(default_factory=dict)
    failures: list[Failure] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class FuzzReport:
    seed: int
    started_at: str
    finished_at: str
    postgres_version: str
    tenants: list[str]
    tables: dict[str, TableReport] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    result: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(self.to_dict(), fp, indent=2, sort_keys=False)
            fp.write("\n")

    def finalize(self) -> None:
        total_attempts = sum(sum(tr.attempts_per_attack_class.values()) for tr in self.tables.values())
        total_failures = sum(len(tr.failures) for tr in self.tables.values())
        total_duration = sum(tr.duration_ms for tr in self.tables.values())
        self.totals = {
            "attempts": total_attempts,
            "failures": total_failures,
            "duration_ms": total_duration,
        }
        self.result = "pass" if total_failures == 0 else "fail"
