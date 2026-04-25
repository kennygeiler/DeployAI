"""Cover ``python -m cartographer.benchmark`` CLI (argparse + print branches)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_CARTOGRAPHER_ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cartographer.benchmark", "--help"],
        cwd=_CARTOGRAPHER_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    out = f"{r.stdout}{r.stderr}"
    assert "--chars" in out
    assert "stub" in out.lower() or "llm" in out.lower()


def test_benchmark_stub_mode_tiny_cli() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cartographer.benchmark", "--chars", "200", "--mode", "stub"],
        cwd=_CARTOGRAPHER_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "wall_seconds=" in f"{r.stdout}{r.stderr}"


def test_benchmark_llm_mode_tiny_cli() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cartographer.benchmark", "--chars", "150", "--mode", "llm"],
        cwd=_CARTOGRAPHER_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    out = f"{r.stdout}{r.stderr}"
    assert "wall_seconds=" in out
    assert "llm" in out.lower() or "mock" in out.lower()


def test_main_runs_in_process_for_coverage(capsys: pytest.CaptureFixture[str]) -> None:
    from cartographer.benchmark import main

    with patch.object(sys, "argv", ["cartographer.benchmark", "--chars", "120", "--mode", "stub"]):
        main()
    one = capsys.readouterr().out
    assert "wall_seconds=" in one
    assert "stub" in one.lower() or "char_target=120" in one

    with patch.object(sys, "argv", ["cartographer.benchmark", "--chars", "80", "--mode", "llm"]):
        main()
    two = capsys.readouterr().out
    assert "wall_seconds=" in two
