#!/usr/bin/env python3
"""Validate ``services/config/llm-capability-matrix.yaml`` against a Python stub provider."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "services" / "config" / "llm-capability-matrix.yaml"


def main() -> int:
    from llm_provider_py.stub import create_stub_provider

    doc = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    agents = doc.get("agents") or {}
    p = create_stub_provider()
    caps = p.capabilities()
    failed = False
    for name, spec in agents.items():
        for k in spec.get("require") or []:
            if not caps.get(k):
                print(
                    f'llm matrix: agent "{name}" needs "{k}" but stub reports {caps.get(k)!r}',
                    file=sys.stderr,
                )
                failed = True
    if failed:
        return 1
    print("llm-capability-matrix (Python): stub provider meets all agent requirements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
