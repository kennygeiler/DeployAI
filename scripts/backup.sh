#!/usr/bin/env bash
# Phase C inc 12.1 -- pg_dump + tenant-DEK metadata to S3 (or MinIO).
#
# Per ORCHESTRATOR.md S4 D3: writes pg_dump of the control-plane Postgres
# plus a JSON document of (tenant_id, name, dek_key_id) tuples to
# s3://${S3_BUCKET}/${S3_PREFIX}/${TIMESTAMP}/.
#
# Required env:
#   S3_BUCKET                 -- target bucket (script refuses without it)
#
# Optional env:
#   S3_PREFIX                 -- key prefix, default "deployai/backups"
#   S3_ENDPOINT_URL           -- non-empty for MinIO (e.g. http://localhost:9000)
#   AWS_REGION                -- default "us-east-1"
#   AWS_ACCESS_KEY_ID         -- AWS creds; for MinIO use MINIO_ROOT_USER value
#   AWS_SECRET_ACCESS_KEY     -- AWS creds; for MinIO use MINIO_ROOT_PASSWORD value
#   COMPOSE_FILE              -- path to docker-compose.yml (default repo's infra/compose)
#   COMPOSE_ENV_FILE          -- compose --env-file (default repo's infra/compose/.env)
#   POSTGRES_USER, POSTGRES_DB -- defaults match infra/compose/.env.example
#
# Outputs (uploaded, never echoed):
#   <ts>/postgres.dump        -- pg_dump custom format
#   <ts>/dek_metadata.json    -- {tenants: [{id, name, dek_key_id}]} JSON
#
# Exit codes: 0 ok, 2 misconfig (no $S3_BUCKET), 1 any other failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/infra/compose/docker-compose.yml}"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-${REPO_ROOT}/infra/compose/.env}"

S3_PREFIX="${S3_PREFIX:-deployai/backups}"
AWS_REGION="${AWS_REGION:-us-east-1}"
POSTGRES_USER="${POSTGRES_USER:-deployai}"
POSTGRES_DB="${POSTGRES_DB:-deployai}"

if [[ -z "${S3_BUCKET:-}" ]]; then
  echo "backup: S3_BUCKET is unset -- refusing to run (would mask prod misconfiguration)" >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "backup: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required" >&2
  exit 2
fi

for cmd in docker aws; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "backup: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

DUMP_PATH="${WORKDIR}/postgres.dump"
META_PATH="${WORKDIR}/dek_metadata.json"

compose_args=(--file "$COMPOSE_FILE")
if [[ -f "$COMPOSE_ENV_FILE" ]]; then
  compose_args+=(--env-file "$COMPOSE_ENV_FILE")
fi

echo "backup: pg_dump ${POSTGRES_DB} from postgres service ..."
docker compose "${compose_args[@]}" exec -T postgres \
  pg_dump --format=custom --no-owner --no-privileges \
  --username="$POSTGRES_USER" "$POSTGRES_DB" >"$DUMP_PATH"

echo "backup: collecting tenant-DEK metadata via control-plane CLI ..."
docker compose "${compose_args[@]}" exec -T control-plane \
  python -m control_plane.cli.dek_metadata >"$META_PATH"

aws_args=(--region "$AWS_REGION")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi

S3_BASE="s3://${S3_BUCKET}/${S3_PREFIX}/${TIMESTAMP}"

echo "backup: uploading to ${S3_BASE}/ ..."
aws "${aws_args[@]}" s3 cp "$DUMP_PATH" "${S3_BASE}/postgres.dump" >/dev/null
aws "${aws_args[@]}" s3 cp "$META_PATH" "${S3_BASE}/dek_metadata.json" >/dev/null

dump_bytes=$(wc -c <"$DUMP_PATH" | tr -d '[:space:]')
meta_bytes=$(wc -c <"$META_PATH" | tr -d '[:space:]')

echo "backup: done"
echo "  destination     ${S3_BASE}/"
echo "  postgres.dump   ${dump_bytes} bytes"
echo "  dek_metadata    ${meta_bytes} bytes"
