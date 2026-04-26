#!/usr/bin/env bash
# Full monorepo gate: pnpm + uv (Python) + Go already on PATH, then turbo.
# Example (Docker):
#   docker run --rm -v "$PWD":/repo -w /repo deployai-turbo-ci:local bash scripts/ci-turbo-full.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

corepack enable
corepack prepare pnpm@10.33.0 --activate
pnpm install --frozen-lockfile
bash scripts/ci-uv-sync-all.sh
pnpm turbo run build lint typecheck test
pnpm run format:check
pnpm turbo run contract:check
