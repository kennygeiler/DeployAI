#!/usr/bin/env bash
# Mint a short-lived (15 min) bootstrap session token for the Fly deployment
# and print ready-to-paste browser instructions. Interim access path until a
# real OIDC issuer is configured (docs/ops/cloud-deploy.md §6) — requires
# DEPLOYAI_ALLOW_TEST_SESSION_MINT=1 on the control-plane app.
set -euo pipefail

STATE_FILE="${STATE_FILE:-$HOME/.deployai-fly-state}"
CP="${CP_URL:-https://deployai-control-plane.fly.dev}"
TENANT="${TENANT_ID:-11111111-1111-1111-1111-111111111111}"
USER_ID="${USER_ID:-aaaaaaa1-1111-4111-8111-111111111111}"
ROLE="${ROLE:-deployment_strategist}"

# shellcheck disable=SC1090
source "$STATE_FILE" 2>/dev/null || { echo "no $STATE_FILE — run scripts/cloud-standup.sh first" >&2; exit 1; }

TOKEN=$(curl -fsS -X POST "$CP/internal/v1/test/session-tokens" \
  -H "X-DeployAI-Internal-Key: $INTERNAL_KEY" -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"$TENANT\",\"user_id\":\"$USER_ID\",\"roles\":[\"$ROLE\"]}" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

cat <<EOF

Token minted (expires in 15 min). To log in, open https://deployai-web.fly.dev
then paste this in the browser devtools console and reload:

  document.cookie = "deployai_access_token=$TOKEN; path=/; secure";

Or for API calls:  Authorization: Bearer $TOKEN
EOF
