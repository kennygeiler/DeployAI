#!/usr/bin/env bash
# Local full monorepo verify (Node + Go + uv on PATH) — same sequence as GitHub `smoke` + turbo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for c in node pnpm uv go; do
  if ! command -v "$c" &>/dev/null; then
    echo "run-turbo-all: missing '$c' on PATH. See docs/dev-environment.md or use infra/docker/Dockerfile.turbo-all" >&2
    exit 1
  fi
done

pnpm install --frozen-lockfile
bash scripts/ci-uv-sync-all.sh
pnpm turbo run test lint typecheck build
echo "run-turbo-all: done."
