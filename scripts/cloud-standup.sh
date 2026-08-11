#!/usr/bin/env bash
# One-shot (idempotent) stand-up of the DeployAI production stack on Fly.io.
#
# Prereqs:
#   - `fly auth login` done, and the account has a payment method
#     (app creation fails with a billing error otherwise).
#   - ANTHROPIC_API_KEY present in infra/compose/.env (reused for the CP).
#   - An RSA keypair for session JWTs:
#       openssl genrsa -out "$KEY_DIR/jwt-private.pem" 2048
#       openssl rsa -in "$KEY_DIR/jwt-private.pem" -pubout -out "$KEY_DIR/jwt-public.pem"
#     Pass KEY_DIR=... (never commit keys).
#
# What it does, in order:
#   apps create x5 -> pg volume -> secrets -> deploy postgres -> deploy
#   control-plane (release runs migrations) -> deploy web/mcp/embedder ->
#   seed BlueState -> mint a bootstrap session token.
#
# State: generated secrets are cached in $STATE_FILE so re-runs reuse them.
# Auth note: this configures the CP-minted-JWT bootstrap path
# (DEPLOYAI_ALLOW_TEST_SESSION_MINT=1). Replace with real OIDC before a
# customer pilot and unset that flag. See docs/ops/cloud-deploy.md §6.
set -euo pipefail

ORG="${FLY_ORG:-personal}"
REGION="${FLY_REGION:-iad}"
KEY_DIR="${KEY_DIR:?set KEY_DIR to the directory holding jwt-private.pem/jwt-public.pem}"
STATE_FILE="${STATE_FILE:-$HOME/.deployai-fly-state}"
ENV_FILE="infra/compose/.env"
PG_VOLUME_GB="${PG_VOLUME_GB:-3}"

say() { printf '\n== %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$KEY_DIR/jwt-private.pem" ] || die "missing $KEY_DIR/jwt-private.pem"
[ -f "$ENV_FILE" ] || die "missing $ENV_FILE"
ANTHROPIC_API_KEY="$(grep -E '^ANTHROPIC_API_KEY=' "$ENV_FILE" | cut -d= -f2-)"
[ -n "$ANTHROPIC_API_KEY" ] || die "no ANTHROPIC_API_KEY in $ENV_FILE"
VOYAGE_API_KEY="$(grep -E '^VOYAGE_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"

# --- durable generated secrets -------------------------------------------
if [ -f "$STATE_FILE" ]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi
PG_PASS="${PG_PASS:-$(openssl rand -hex 24)}"
INTERNAL_KEY="${INTERNAL_KEY:-$(openssl rand -hex 32)}"
umask 077
cat > "$STATE_FILE" <<EOF
PG_PASS=$PG_PASS
INTERNAL_KEY=$INTERNAL_KEY
EOF

# --- apps -----------------------------------------------------------------
say "creating apps (no-op if they exist)"
for app in deployai-postgres deployai-control-plane deployai-web deployai-mcp-server deployai-embedder; do
  fly apps create "$app" --org "$ORG" 2>/dev/null || echo "  $app exists"
done

say "postgres volume"
fly volumes list --app deployai-postgres | grep -q deployai_pg_data || \
  fly volumes create deployai_pg_data --app deployai-postgres --region "$REGION" --size "$PG_VOLUME_GB" --yes

say "redis (Upstash via fly)"
REDIS_URL="${REDIS_URL:-}"
if [ -z "$REDIS_URL" ]; then
  if fly redis list 2>/dev/null | grep -q deployai-redis; then
    REDIS_URL="$(fly redis status deployai-redis 2>/dev/null | grep -Eo 'redis://[^ ]+' | head -1 || true)"
  else
    fly redis create --name deployai-redis --org "$ORG" --region "$REGION" --no-replicas --disable-eviction || true
    REDIS_URL="$(fly redis status deployai-redis 2>/dev/null | grep -Eo 'redis://[^ ]+' | head -1 || true)"
  fi
fi
[ -n "$REDIS_URL" ] || echo "WARN: could not auto-detect REDIS_URL — set it and re-run (fly redis status deployai-redis)"

DB_URL="postgresql+asyncpg://deployai:${PG_PASS}@deployai-postgres.internal:5432/deployai"

# --- secrets --------------------------------------------------------------
say "secrets: postgres"
fly secrets set POSTGRES_PASSWORD="$PG_PASS" POSTGRES_USER=deployai POSTGRES_DB=deployai \
  --app deployai-postgres --stage

say "secrets: control-plane"
fly secrets set \
  DATABASE_URL="$DB_URL" \
  ${REDIS_URL:+REDIS_URL="$REDIS_URL"} \
  DEPLOYAI_INTERNAL_API_KEY="$INTERNAL_KEY" \
  ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  ${VOYAGE_API_KEY:+VOYAGE_API_KEY="$VOYAGE_API_KEY"} \
  DEPLOYAI_JWT_PRIVATE_KEY_B64="$(base64 < "$KEY_DIR/jwt-private.pem" | tr -d '\n')" \
  DEPLOYAI_ALLOW_TEST_SESSION_MINT=1 \
  --app deployai-control-plane --stage

say "secrets: web"
fly secrets set \
  DEPLOYAI_INTERNAL_API_KEY="$INTERNAL_KEY" \
  DEPLOYAI_CONTROL_PLANE_URL="http://deployai-control-plane.internal:8000" \
  NEXT_PUBLIC_CONTROL_PLANE_URL="https://deployai-control-plane.fly.dev" \
  DEPLOYAI_WEB_TRUST_JWT=1 \
  DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM="$(cat "$KEY_DIR/jwt-public.pem")" \
  DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1 \
  --app deployai-web --stage

say "secrets: mcp-server + embedder"
fly secrets set DATABASE_URL="$DB_URL" DEPLOYAI_INTERNAL_API_KEY="$INTERNAL_KEY" \
  --app deployai-mcp-server --stage
fly secrets set DATABASE_URL="$DB_URL" ${VOYAGE_API_KEY:+VOYAGE_API_KEY="$VOYAGE_API_KEY"} \
  --app deployai-embedder --stage

# --- deploys (order matters) ---------------------------------------------
say "deploy postgres"
fly deploy --config infra/fly/postgres/fly.toml --remote-only --yes

say "deploy control-plane (release runs alembic upgrade head)"
fly deploy --config infra/fly/control-plane/fly.toml --remote-only --yes

say "deploy web / mcp-server / embedder"
fly deploy --config infra/fly/web/fly.toml --remote-only --yes
fly deploy --config infra/fly/mcp-server/fly.toml --remote-only --yes
fly deploy --config infra/fly/embedder/fly.toml --remote-only --yes

# --- seed + smoke ---------------------------------------------------------
CP=https://deployai-control-plane.fly.dev
say "health"
curl -fsS "$CP/health" >/dev/null && echo "  control-plane healthy"
curl -fsS -o /dev/null -w '  web -> %{http_code}\n' https://deployai-web.fly.dev/api/health

say "seed BlueState (idempotent; 409 = already seeded)"
curl -s -X POST "$CP/internal/v1/admin/seed-scenarios/bluestate?tenant_id=11111111-1111-1111-1111-111111111111" \
  -H "X-DeployAI-Internal-Key: $INTERNAL_KEY" -H "Content-Type: application/json" -d '{}' \
  -o /dev/null -w '  seed -> %{http_code}\n' || true

say "bootstrap token (15-min expiry; re-mint with scripts/cloud-token.sh)"
bash scripts/cloud-token.sh || true

say "done — https://deployai-web.fly.dev"
