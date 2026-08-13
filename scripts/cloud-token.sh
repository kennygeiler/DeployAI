#!/usr/bin/env bash
#
# Mint a short-lived (15 min) bootstrap session JWT from the hosted
# control plane. Operator-only access shim while OIDC is unwired — see
# docs/ops/cloud-deploy.md §7. The CP must have
# DEPLOYAI_ALLOW_TEST_SESSION_MINT=1 set (bootstrap only; unset post-OIDC).
#
# Hits POST {CP_URL}/internal/v1/test/session-tokens with the
# X-DeployAI-Internal-Key header and prints the access token plus the
# cookie recipe the web app expects.
#
# Required env:
#   DEPLOYAI_INTERNAL_API_KEY   the shared internal key (also read from
#                               INTERNAL_KEY in ~/.deployai-railway-state
#                               when unset)
# Optional env:
#   CP_URL       control-plane base URL
#                (default: the Railway CP public domain)
#   TENANT_ID    default 11111111-1111-1111-1111-111111111111 (dev tenant)
#   USER_ID      default 22222222-2222-2222-2222-222222222222
#   ROLES        comma-separated, default "platform_admin"
#   STATE_FILE   default ~/.deployai-railway-state
#
# Exit codes: 0 ok, 2 misconfig, 1 mint failure.

set -euo pipefail

CP_URL="${CP_URL:-https://control-plane-production-798e.up.railway.app}"
TENANT_ID="${TENANT_ID:-11111111-1111-1111-1111-111111111111}"
USER_ID="${USER_ID:-22222222-2222-2222-2222-222222222222}"
# "platform_admin" is a real role in the authz matrix; the old default
# ("admin") is not a role at all — the web middleware parses it to null and
# every strategist page 403s, which reads as a broken deploy.
ROLES="${ROLES:-platform_admin}"
STATE_FILE="${STATE_FILE:-$HOME/.deployai-railway-state}"

if [[ -z "${DEPLOYAI_INTERNAL_API_KEY:-}" && -f "$STATE_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$STATE_FILE"
  DEPLOYAI_INTERNAL_API_KEY="${INTERNAL_KEY:-}"
fi

if [[ -z "${DEPLOYAI_INTERNAL_API_KEY:-}" ]]; then
  echo "cloud-token: DEPLOYAI_INTERNAL_API_KEY is unset (and no INTERNAL_KEY in ${STATE_FILE})" >&2
  exit 2
fi

for cmd in curl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "cloud-token: required command '$cmd' not found on PATH" >&2
    exit 2
  fi
done

# Build the roles JSON array from the comma-separated ROLES.
roles_json="$(python3 -c 'import json,sys; print(json.dumps([r.strip() for r in sys.argv[1].split(",") if r.strip()]))' "$ROLES")"

body="$(printf '{"tenant_id": "%s", "user_id": "%s", "roles": %s}' \
  "$TENANT_ID" "$USER_ID" "$roles_json")"

echo "cloud-token: minting session for tenant ${TENANT_ID} at ${CP_URL} ..." >&2

response="$(curl -sS --fail-with-body \
  -X POST "${CP_URL%/}/internal/v1/test/session-tokens" \
  -H "Content-Type: application/json" \
  -H "X-DeployAI-Internal-Key: ${DEPLOYAI_INTERNAL_API_KEY}" \
  -d "$body")" || {
  echo "cloud-token: mint failed. Response body (if any):" >&2
  echo "$response" >&2
  echo "cloud-token: 404 usually means DEPLOYAI_ALLOW_TEST_SESSION_MINT is not set on the CP;" >&2
  echo "cloud-token: 401/403 means the internal key does not match." >&2
  exit 1
}

access_token="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
expires_in="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("expires_in", "?"))')"

echo >&2
echo "cloud-token: access token (expires in ${expires_in}s):" >&2
printf '%s\n' "$access_token"
echo >&2
echo "cloud-token: to use it, set this cookie on the web app's domain" >&2
echo "cloud-token: (browser devtools -> Application -> Cookies):" >&2
echo "cloud-token:   name:  deployai_access_token" >&2
echo "cloud-token:   value: <the token above>" >&2
echo "cloud-token: then load /engagements. Re-run this script when it expires." >&2
