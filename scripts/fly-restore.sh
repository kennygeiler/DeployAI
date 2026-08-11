#!/usr/bin/env bash
# Pilot-refresh ticket H1 -- restore a fly-backup.sh dump into the Fly Postgres.
#
# Fly sibling of scripts/restore.sh (which targets the local compose stack).
# Pulls postgres.sql.gz + dek_metadata.json from a timestamped S3 prefix
# written by scripts/fly-backup.sh and replays the SQL against the Fly-hosted
# database THROUGH `fly proxy` with a local psql client. psql is required
# locally because `fly ssh console` cannot reliably stream a multi-hundred-MB
# dump into a remote stdin; the proxy path is bidirectional and binary-safe.
#
# THIS OVERWRITES THE LIVE FLY DATABASE. Same double-confirmation guardrails
# as scripts/restore.sh:
#
#   DEPLOYAI_RESTORE_CONFIRM=YES           -- always required
#   DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES   -- additionally required when the
#                                             target DB already has tenant rows
#
# Required:
#   $1 (or $BACKUP)               -- s3://bucket/prefix/<TIMESTAMP>/ to restore
#   AWS_ACCESS_KEY_ID             -- S3 creds (Tigris or AWS)
#   AWS_SECRET_ACCESS_KEY         -- S3 creds
#   PGPASSWORD                    -- the Fly POSTGRES_PASSWORD secret value
#                                    (psql auths through the proxy with it)
#
# Optional env:
#   FLY_APP                       -- Fly Postgres app (default "deployai-postgres")
#   FLY_API_TOKEN                 -- Fly auth for non-interactive `fly proxy`
#   FLY_PROXY_PORT                -- local proxy port (default 15432)
#   S3_ENDPOINT_URL               -- for Tigris: https://fly.storage.tigris.dev
#   AWS_REGION                    -- default "auto" (Tigris)
#   POSTGRES_USER, POSTGRES_DB    -- default "deployai" / "deployai"
#
# Exit codes: 0 ok, 2 misconfig / safety guard, 1 any other failure.

set -euo pipefail

FLY_APP="${FLY_APP:-deployai-postgres}"
FLY_PROXY_PORT="${FLY_PROXY_PORT:-15432}"
AWS_REGION="${AWS_REGION:-auto}"
POSTGRES_USER="${POSTGRES_USER:-deployai}"
POSTGRES_DB="${POSTGRES_DB:-deployai}"

BACKUP_URI="${1:-${BACKUP:-}}"

if [[ -z "$BACKUP_URI" ]]; then
  echo "fly-restore: BACKUP is unset -- pass as \$1 or BACKUP=s3://bucket/prefix/<TIMESTAMP>/" >&2
  exit 2
fi

if [[ "$BACKUP_URI" != s3://* ]]; then
  echo "fly-restore: BACKUP must be an s3:// URI, got '${BACKUP_URI}'" >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "fly-restore: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required" >&2
  exit 2
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "fly-restore: PGPASSWORD is required (the Fly POSTGRES_PASSWORD secret value)" >&2
  exit 2
fi

if [[ "${DEPLOYAI_RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "fly-restore: DEPLOYAI_RESTORE_CONFIRM=YES not set -- refusing." >&2
  echo "fly-restore: this overwrites the live Fly database (${FLY_APP}). Set" >&2
  echo "fly-restore: DEPLOYAI_RESTORE_CONFIRM=YES ONLY after verifying the target app" >&2
  echo "fly-restore: and the source BACKUP prefix are correct." >&2
  exit 2
fi

for cmd in fly aws gunzip psql; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "fly-restore: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

WORKDIR="$(mktemp -d)"
PROXY_PID=""
cleanup() {
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" 2>/dev/null; then
    kill "$PROXY_PID" 2>/dev/null || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

GZ_PATH="${WORKDIR}/postgres.sql.gz"
SQL_PATH="${WORKDIR}/postgres.sql"
META_PATH="${WORKDIR}/dek_metadata.json"

BACKUP_BASE="${BACKUP_URI%/}"

aws_args=(--region "$AWS_REGION")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi

echo "fly-restore: pulling ${BACKUP_BASE}/postgres.sql.gz ..." >&2
aws "${aws_args[@]}" s3 cp "${BACKUP_BASE}/postgres.sql.gz" "$GZ_PATH" >/dev/null

echo "fly-restore: pulling ${BACKUP_BASE}/dek_metadata.json ..." >&2
aws "${aws_args[@]}" s3 cp "${BACKUP_BASE}/dek_metadata.json" "$META_PATH" >/dev/null

echo "fly-restore: verifying gzip integrity ..." >&2
gunzip -t "$GZ_PATH"
gunzip -k "$GZ_PATH"

sql_bytes=$(wc -c <"$SQL_PATH" | tr -d '[:space:]')
if [[ "$sql_bytes" -le 0 ]]; then
  echo "fly-restore: dump is empty (0 bytes) -- refusing" >&2
  exit 1
fi

echo "fly-restore: DEK manifest (verify tenant set BEFORE the destructive step):" >&2
echo "--- BEGIN dek_metadata.json ---" >&2
cat "$META_PATH" >&2
echo "" >&2
echo "--- END dek_metadata.json ---" >&2

echo "fly-restore: opening fly proxy ${FLY_PROXY_PORT}:5432 to ${FLY_APP} ..." >&2
fly proxy "${FLY_PROXY_PORT}:5432" --app "$FLY_APP" &
PROXY_PID=$!

# Wait for the proxy to accept connections (up to 30s).
proxy_up=0
for _ in $(seq 1 30); do
  if (exec 3<>"/dev/tcp/127.0.0.1/${FLY_PROXY_PORT}") 2>/dev/null; then
    exec 3>&- || true
    proxy_up=1
    break
  fi
  sleep 1
done
if [[ "$proxy_up" -ne 1 ]]; then
  echo "fly-restore: fly proxy did not come up on 127.0.0.1:${FLY_PROXY_PORT} within 30s" >&2
  exit 1
fi

psql_conn=(psql --host 127.0.0.1 --port "$FLY_PROXY_PORT" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-psqlrc)

# Probe the target DB for existing user data (same second gate as restore.sh):
# a populated app_tenants table means the operator is about to clobber real
# state and must opt in a SECOND time.
echo "fly-restore: probing target DB for existing rows ..." >&2
table_exists=$("${psql_conn[@]}" -tAc "SELECT to_regclass('public.app_tenants') IS NOT NULL" | tr -d '[:space:]')
if [[ "$table_exists" == "t" ]]; then
  existing_rows=$("${psql_conn[@]}" -tAc "SELECT COUNT(*) FROM app_tenants" | tr -d '[:space:]')
else
  existing_rows=0
fi
if [[ -z "$existing_rows" ]]; then
  existing_rows=0
fi

if [[ "$existing_rows" -gt 0 && "${DEPLOYAI_RESTORE_FORCE_OVERWRITE:-}" != "YES" ]]; then
  echo "fly-restore: target DB is non-empty (${existing_rows} tenant rows present)." >&2
  echo "fly-restore: refusing to overwrite. Set DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES to proceed." >&2
  exit 2
fi

echo "fly-restore: replaying dump into ${FLY_APP}/${POSTGRES_DB} (single transaction; rolls back on failure) ..." >&2
"${psql_conn[@]}" --single-transaction -v ON_ERROR_STOP=1 -f "$SQL_PATH" >/dev/null

echo "fly-restore: done" >&2
echo "  source          ${BACKUP_BASE}/" >&2
echo "  postgres.sql    ${sql_bytes} bytes" >&2
echo "fly-restore: next steps -- run alembic against the restored DB if the app" >&2
echo "fly-restore: version has advanced, then smoke the deployment before traffic." >&2
