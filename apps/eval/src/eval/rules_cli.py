"""CLI: `uv run python -m eval.rules_cli` — writes `artifacts/replay-parity/rules-report.json` (smoke, Story 4-5)."""

from __future__ import annotations

from pathlib import Path

from eval.rules.evaluator import RuleEvalReport, write_report


def _repo_root() -> Path:
    # .../apps/eval/src/eval/rules_cli.py → parents[4] = monorepo root
    return Path(__file__).resolve().parents[4]


def main() -> None:
    out = _repo_root() / "artifacts" / "replay-parity" / "rules-report.json"
    # Smoke: empty reports list is invalid UX — emit one passing smoke row until wired to the agent.
    write_report(
        [RuleEvalReport(query_id="ci-smoke-placeholder", pass_=True, missing=[], extra=[], wrong_rank=[])],
        out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
