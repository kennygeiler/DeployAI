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
# Mirror the CI `smoke` job step-for-step. `turbo run lint` already calls
# `ruff format --check` per Python workspace via each `package.json#lint`
# script — but prettier (--check) lives outside turbo, so call it
# explicitly here. Without this, contributors can get a green local run
# and still red-CI on a prettier-only diff.
pnpm turbo run test lint typecheck build
pnpm run format:check
echo "run-turbo-all: done."
