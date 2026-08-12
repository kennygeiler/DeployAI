#!/usr/bin/env bash
#
# Deploy the five DeployAI services to Railway in dependency order.
# Read docs/ops/cloud-deploy.md first — this assumes the project, services,
# volume, and variables already exist (scripts/cloud-standup.sh creates
# them). Idempotent: safe to re-run after a failed deploy.
#
# `railway up` tarballs the working tree from the repo root (honoring
# .gitignore) and builds each service with its RAILWAY_DOCKERFILE_PATH.
# Order matters only for first boots: control-plane runs
# `alembic upgrade head` on start (RUN_MIGRATIONS=1), so Postgres must be
# up first; web/mcp-server/embedder depend on the schema.
#
# Usage:
#   scripts/cloud-deploy.sh                 # deploy all services in order
#   scripts/cloud-deploy.sh control-plane   # deploy just one
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v railway >/dev/null 2>&1; then
  echo "cloud-deploy: railway CLI not found (brew install railway)" >&2
  exit 2
fi

deploy_one() {
  local name="$1"
  echo
  echo "================================================================"
  echo "  Deploying $name"
  echo "================================================================"
  railway up --service "$name" --detach
}

services=(postgres control-plane embedder mcp-server web)

if [ "$#" -gt 0 ]; then
  deploy_one "$1"
  exit 0
fi

for svc in "${services[@]}"; do
  deploy_one "$svc"
done

echo
echo "All deploys triggered (--detach: builds continue on Railway)."
echo "Watch:   railway logs --service control-plane"
echo "Smoke:   curl https://control-plane-production-798e.up.railway.app/health"
echo "         curl https://mcp-server-production-d7af.up.railway.app/health"
echo "         open https://web-production-e4059.up.railway.app"
