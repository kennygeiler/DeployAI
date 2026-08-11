#!/usr/bin/env bash
#
# One-shot (idempotent) standup of the DeployAI Railway project.
# Mirrors docs/ops/cloud-deploy.md §§1-5 — read that first.
#
# What it does, in order:
#   1. Verifies the railway CLI is installed + logged in.
#   2. Generates (or reuses) secrets: PG_PASS + INTERNAL_KEY in the state
#      file, an RS256 session-JWT keypair in KEY_DIR.
#   3. Creates the project / Redis / the five services if missing.
#   4. Adds the Postgres volume, sets per-service variables.
#   5. Deploys in dependency order via scripts/cloud-deploy.sh.
#
# Safe to re-run: existing project resources are left alone (create steps
# tolerate "already exists"), variables are re-asserted to the same values,
# and secrets are only generated when absent from the state file / KEY_DIR.
#
# State (chmod 600/700, never committed):
#   ~/.deployai-railway-state   PG_PASS + INTERNAL_KEY (sourceable KEY=VALUE)
#   ~/.deployai-keys/           jwt-private.pem / jwt-public.pem
#
# Required env:
#   ANTHROPIC_API_KEY           Claude key for the control plane
# Optional env:
#   VOYAGE_API_KEY              embeddings (embedder writes zero-vectors without)
#   DEPLOYAI_ADMIN_EMAILS       comma-separated admin emails
#   RAILWAY_PROJECT_NAME        default "deployai"
#   STATE_FILE                  default ~/.deployai-railway-state
#   KEY_DIR                     default ~/.deployai-keys
#   SKIP_DEPLOY=1               stand up config only; no `railway up`
#
# Exit codes: 0 ok, 2 misconfig, 1 any other failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PROJECT_NAME="${RAILWAY_PROJECT_NAME:-deployai}"
STATE_FILE="${STATE_FILE:-$HOME/.deployai-railway-state}"
KEY_DIR="${KEY_DIR:-$HOME/.deployai-keys}"

log() { printf 'cloud-standup: %s\n' "$*" >&2; }

# ---------------------------------------------------------------- prereqs
for cmd in railway openssl base64; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "required command '$cmd' not found on PATH"
    exit 2
  fi
done

if ! railway whoami >/dev/null 2>&1; then
  log "not logged in -- run 'railway login' first"
  exit 2
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  log "ANTHROPIC_API_KEY is required (control-plane LLM calls)"
  exit 2
fi
if [[ -z "${VOYAGE_API_KEY:-}" ]]; then
  log "WARN: VOYAGE_API_KEY unset -- embedder will write zero-vectors"
fi

# ---------------------------------------------------- secrets: state file
if [[ -f "$STATE_FILE" ]]; then
  log "reusing secrets from $STATE_FILE"
  # shellcheck source=/dev/null
  source "$STATE_FILE"
fi
if [[ -z "${PG_PASS:-}" || -z "${INTERNAL_KEY:-}" ]]; then
  log "generating PG_PASS + INTERNAL_KEY -> $STATE_FILE"
  PG_PASS="${PG_PASS:-$(openssl rand -hex 24)}"
  INTERNAL_KEY="${INTERNAL_KEY:-$(openssl rand -hex 32)}"
  umask 077
  {
    echo "PG_PASS=${PG_PASS}"
    echo "INTERNAL_KEY=${INTERNAL_KEY}"
  } >"$STATE_FILE"
fi

# ------------------------------------------------- secrets: JWT keypair
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"
if [[ ! -f "$KEY_DIR/jwt-private.pem" ]]; then
  log "generating RS256 session-JWT keypair in $KEY_DIR"
  umask 077
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$KEY_DIR/jwt-private.pem" 2>/dev/null
  openssl pkey -in "$KEY_DIR/jwt-private.pem" -pubout \
    -out "$KEY_DIR/jwt-public.pem" 2>/dev/null
fi
JWT_PRIVATE_B64="$(base64 <"$KEY_DIR/jwt-private.pem" | tr -d '\n')"
JWT_PUBLIC_PEM="$(cat "$KEY_DIR/jwt-public.pem")"

# -------------------------------------------------- project + services
# `railway status` succeeds only when the cwd is linked to a project.
if railway status >/dev/null 2>&1; then
  log "directory already linked to a Railway project -- reusing it"
else
  log "creating project '$PROJECT_NAME' (railway init)"
  railway init --name "$PROJECT_NAME"
fi

# Create-if-missing; Railway errors on duplicates, which we tolerate.
ensure_service() {
  local name="$1"
  if railway add --service "$name" >/dev/null 2>&1; then
    log "created service $name"
  else
    log "service $name already exists (ok)"
  fi
}

if railway add --database redis >/dev/null 2>&1; then
  log "created managed Redis"
else
  log "managed Redis already exists (ok)"
fi

for svc in postgres control-plane web mcp-server embedder; do
  ensure_service "$svc"
done

if railway volume add --service postgres \
  --mount-path /var/lib/postgresql/data >/dev/null 2>&1; then
  log "created postgres volume at /var/lib/postgresql/data"
else
  log "postgres volume already exists (ok)"
fi

# ------------------------------------------------------------ variables
# Idempotent by construction: re-setting a var to the same value is a no-op
# apart from a possible redeploy trigger.
set_vars() {
  local service="$1"
  shift
  log "variables -> $service"
  railway variables --service "$service" --skip-deploys "$@"
}

DB_URL="postgresql+asyncpg://deployai:${PG_PASS}@postgres.railway.internal:5432/deployai"
# Literal Railway reference syntax — resolved by Railway, not the shell.
# shellcheck disable=SC2016
REDIS_REF='redis://default:${{Redis.REDISPASSWORD}}@redis.railway.internal:6379/0'

set_vars postgres \
  --set "RAILWAY_DOCKERFILE_PATH=infra/compose/postgres/Dockerfile" \
  --set "POSTGRES_USER=deployai" \
  --set "POSTGRES_PASSWORD=${PG_PASS}" \
  --set "POSTGRES_DB=deployai" \
  --set "PGDATA=/var/lib/postgresql/data/pgdata"
# PGDATA subdirectory: Railway volume roots are not empty (metadata dirs),
# and initdb refuses a non-empty data directory — same class of problem the
# Fly volume's lost+found caused. A subdir sidesteps it.

set_vars control-plane \
  --set "RAILWAY_DOCKERFILE_PATH=services/control-plane/Dockerfile" \
  --set "RUN_MIGRATIONS=1" \
  --set "DATABASE_URL=${DB_URL}" \
  --set "REDIS_URL=${REDIS_REF}" \
  --set "DEPLOYAI_REDIS_URL=${REDIS_REF}" \
  --set "DEPLOYAI_INTERNAL_API_KEY=${INTERNAL_KEY}" \
  --set "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" \
  --set "VOYAGE_API_KEY=${VOYAGE_API_KEY:-}" \
  --set "DEPLOYAI_ADMIN_EMAILS=${DEPLOYAI_ADMIN_EMAILS:-}" \
  --set "DEPLOYAI_JWT_PRIVATE_KEY_B64=${JWT_PRIVATE_B64}" \
  --set "DEPLOYAI_ALLOW_TEST_SESSION_MINT=1"

# NEXT_PUBLIC_CONTROL_PLANE_URL needs the CP's public domain, which exists
# only after one is generated (dashboard or `railway domain`). Assert it
# when known; warn otherwise.
CP_PUBLIC_URL="${CP_PUBLIC_URL:-https://control-plane-production-798e.up.railway.app}"

set_vars web \
  --set "RAILWAY_DOCKERFILE_PATH=apps/web/Dockerfile" \
  --set "DEPLOYAI_INTERNAL_API_KEY=${INTERNAL_KEY}" \
  --set "DEPLOYAI_CONTROL_PLANE_URL=http://control-plane.railway.internal:8000" \
  --set "NEXT_PUBLIC_CONTROL_PLANE_URL=${CP_PUBLIC_URL}" \
  --set "DEPLOYAI_WEB_TRUST_JWT=1" \
  --set "DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM=${JWT_PUBLIC_PEM}"

set_vars mcp-server \
  --set "RAILWAY_DOCKERFILE_PATH=services/mcp-server/Dockerfile" \
  --set "DATABASE_URL=${DB_URL}" \
  --set "DEPLOYAI_INTERNAL_API_KEY=${INTERNAL_KEY}"

set_vars embedder \
  --set "RAILWAY_DOCKERFILE_PATH=services/control-plane/Dockerfile" \
  --set "SERVICE_ROLE=embedder" \
  --set "DATABASE_URL=${DB_URL}" \
  --set "VOYAGE_API_KEY=${VOYAGE_API_KEY:-}"

# --------------------------------------------------------------- deploy
if [[ "${SKIP_DEPLOY:-0}" == "1" ]]; then
  log "SKIP_DEPLOY=1 -- configuration asserted, skipping deploys"
else
  "$REPO_ROOT/scripts/cloud-deploy.sh"
fi

log "done. Next steps (docs/ops/cloud-deploy.md):"
log "  - generate public domains for web / control-plane / mcp-server"
log "    (dashboard -> Settings -> Networking, or 'railway domain --service <name>')"
log "  - re-run with CP_PUBLIC_URL=<cp domain> if it differed from the default"
log "  - seed a tenant (runbook §6), mint a bootstrap token (scripts/cloud-token.sh)"
log "  - schedule volume backups in the dashboard (docs/ops/backup.md)"
log "  - wire OIDC and unset DEPLOYAI_ALLOW_TEST_SESSION_MINT before any pilot user"
