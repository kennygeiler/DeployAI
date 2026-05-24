#!/usr/bin/env bash
# Phase C inc 12.2 -- restore pg_dump from S3 (or MinIO) into Postgres.
#
# Companion to scripts/backup.sh: pulls postgres.dump + dek_metadata.json
# from a timestamped S3 prefix written by `make backup` and replays the
# dump against the control-plane Postgres.
#
# Required:
#   $1 (or $BACKUP)               -- s3://bucket/prefix/<TIMESTAMP>/ to restore
#   AWS_ACCESS_KEY_ID             -- AWS creds; for MinIO use MINIO_ROOT_USER
#   AWS_SECRET_ACCESS_KEY         -- AWS creds; for MinIO use MINIO_ROOT_PASSWORD
#   DEPLOYAI_RESTORE_CONFIRM=YES  -- mandatory operator-acknowledged kill-switch;
#                                    restore is destructive (overwrites the live DB)
#
# Conditionally required:
#   DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES
#                                 -- required when the target DB is non-empty;
#                                    refuses otherwise so naive operators hit a
#                                    hard wall before clobbering populated prod.
#
# Optional env:
#   S3_ENDPOINT_URL               -- non-empty for MinIO (e.g. http://localhost:9000)
#   AWS_REGION                    -- default "us-east-1"
#   COMPOSE_FILE                  -- compose file (default infra/compose/docker-compose.yml)
#   COMPOSE_ENV_FILE              -- compose --env-file (default infra/compose/.env)
#   POSTGRES_USER, POSTGRES_DB    -- defaults match infra/compose/.env.example
#
# Exit codes: 0 ok, 2 misconfig / safety guard, 1 any other failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/infra/compose/docker-compose.yml}"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-${REPO_ROOT}/infra/compose/.env}"

AWS_REGION="${AWS_REGION:-us-east-1}"
POSTGRES_USER="${POSTGRES_USER:-deployai}"
POSTGRES_DB="${POSTGRES_DB:-deployai}"

BACKUP_URI="${1:-${BACKUP:-}}"

if [[ -z "$BACKUP_URI" ]]; then
  echo "restore: BACKUP is unset -- pass as \$1 or BACKUP=s3://bucket/prefix/<TIMESTAMP>/" >&2
  exit 2
fi

if [[ "$BACKUP_URI" != s3://* ]]; then
  echo "restore: BACKUP must be an s3:// URI, got '${BACKUP_URI}'" >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "restore: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required" >&2
  exit 2
fi

if [[ "${DEPLOYAI_RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "restore: DEPLOYAI_RESTORE_CONFIRM=YES not set -- refusing." >&2
  echo "restore: this overwrites the live database. Set DEPLOYAI_RESTORE_CONFIRM=YES" >&2
  echo "restore: in the environment ONLY after you have verified the target DB and" >&2
  echo "restore: the source BACKUP prefix are correct." >&2
  exit 2
fi

for cmd in docker aws; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "restore: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

DUMP_PATH="${WORKDIR}/postgres.dump"
META_PATH="${WORKDIR}/dek_metadata.json"

# Normalise trailing slash for predictable joins.
BACKUP_BASE="${BACKUP_URI%/}"

aws_args=(--region "$AWS_REGION")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi

compose_args=(--file "$COMPOSE_FILE")
if [[ -f "$COMPOSE_ENV_FILE" ]]; then
  compose_args+=(--env-file "$COMPOSE_ENV_FILE")
fi

echo "restore: pulling ${BACKUP_BASE}/postgres.dump ..." >&2
aws "${aws_args[@]}" s3 cp "${BACKUP_BASE}/postgres.dump" "$DUMP_PATH" >/dev/null

echo "restore: pulling ${BACKUP_BASE}/dek_metadata.json ..." >&2
aws "${aws_args[@]}" s3 cp "${BACKUP_BASE}/dek_metadata.json" "$META_PATH" >/dev/null

dump_bytes=$(wc -c <"$DUMP_PATH" | tr -d '[:space:]')
if [[ "$dump_bytes" -le 0 ]]; then
  echo "restore: pg_dump file is empty (0 bytes) -- refusing to truncate the target DB" >&2
  exit 1
fi

echo "restore: DEK manifest (verify tenant set BEFORE the destructive step):" >&2
echo "--- BEGIN dek_metadata.json ---" >&2
cat "$META_PATH" >&2
echo "" >&2
echo "--- END dek_metadata.json ---" >&2

# Probe the target DB for existing user data. The control-plane schema
# carries `app_tenants` from migration zero, so we count rows there. A
# non-zero count means the operator is about to clobber populated state
# and must opt in a SECOND time via DEPLOYAI_RESTORE_FORCE_OVERWRITE.
echo "restore: probing target DB for existing rows ..." >&2
existing_rows=$(docker compose "${compose_args[@]}" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT COALESCE((SELECT COUNT(*) FROM app_tenants), 0)" 2>/dev/null \
  | tr -d '[:space:]' || echo "0")

if [[ -z "$existing_rows" ]]; then
  existing_rows=0
fi

if [[ "$existing_rows" -gt 0 && "${DEPLOYAI_RESTORE_FORCE_OVERWRITE:-}" != "YES" ]]; then
  echo "restore: target DB is non-empty (${existing_rows} tenant rows present)." >&2
  echo "restore: refusing to overwrite. Set DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES to proceed." >&2
  exit 2
fi

echo "restore: replaying pg_dump into ${POSTGRES_DB} (single-transaction; rolls back on failure) ..." >&2
docker compose "${compose_args[@]}" exec -T postgres \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  --single-transaction --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" \
  <"$DUMP_PATH"

echo "restore: done" >&2
echo "  source           ${BACKUP_BASE}/" >&2
echo "  postgres.dump    ${dump_bytes} bytes" >&2
