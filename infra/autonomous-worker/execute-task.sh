#!/usr/bin/env bash
# Run aider headlessly against a markdown architecture plan (repo mounted at /workspace).
set -euo pipefail

PLAN="${1:-}"
if [[ -z "${PLAN}" || ! -f "${PLAN}" ]]; then
  echo "usage: execute-task.sh <path-to-plan.md>" >&2
  exit 1
fi

exec aider \
  --model gemini/gemini-1.5-pro \
  --dangerously-skip-permissions \
  --commit \
  --msg "automated agent refactor" \
  --apply "${PLAN}"
