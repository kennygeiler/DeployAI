#!/usr/bin/env bash
#
# Wrapper for the 5 `fly deploy` calls in correct order.
# Read docs/ops/cloud-deploy.md first — this assumes Fly apps + secrets
# already exist. Idempotent: safe to re-run after a failed deploy.
#
# Usage:
#   bin/cloud-deploy.sh              # deploy all services in order
#   bin/cloud-deploy.sh control-plane # deploy just one
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

deploy_one() {
  local name="$1"
  echo
  echo "================================================================"
  echo "  Deploying $name"
  echo "================================================================"
  fly deploy --config "infra/fly/$name/fly.toml" --remote-only
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
echo "All deploys complete. Smoke check:"
echo "  curl https://api.<your-domain>/health"
echo "  curl https://mcp.<your-domain>/health"
echo "  open https://app.<your-domain>"
