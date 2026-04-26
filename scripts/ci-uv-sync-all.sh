#!/usr/bin/env bash
# Sync every directory that has `uv.lock` so `uv run` in turbo tasks is warm.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv &>/dev/null; then
  echo "ci-uv-sync-all: uv is not on PATH. Install from https://docs.astral.sh/uv/ " >&2
  exit 1
fi

while IFS= read -r lock; do
  [[ -z "$lock" ]] && continue
  dir=$(dirname "$lock")
  echo "ci-uv-sync-all: (cd $dir && uv sync)"
  (cd "$dir" && uv sync)
done < <(find . -name uv.lock -not -path "*/node_modules/*" | LC_ALL=C sort)

echo "ci-uv-sync-all: done."
