"""CLI: `uv run python -m eval.judge_cli` — writes `artifacts/replay-parity/judge-report.json` (Story 4-6)."""

from __future__ import annotations

from pathlib import Path

from eval.judge.reporter import build_report_for_ci, write_judge_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main() -> None:
    out = _repo_root() / "artifacts" / "replay-parity" / "judge-report.json"
    rep = build_report_for_ci()
    write_judge_report(rep, out)
    print(f"Wrote {out} (mode={rep.mode})")


if __name__ == "__main__":
    main()
