#!/usr/bin/env bash
# Pilot-refresh ticket H1 -- pg_dump the Fly-hosted Postgres to S3-compatible
# storage (Tigris or AWS S3).
#
# Fly sibling of scripts/backup.sh (which is compose-only: it shells into the
# local docker compose postgres service). This script instead runs pg_dump
# INSIDE the Fly machine via `fly ssh console -C`, so the local host needs no
# Postgres client tools and there is no client/server version-skew risk. The
# dump streams back over the SSH session, is gzipped locally, and uploaded to
# s3://${S3_BUCKET}/${S3_PREFIX}/${TIMESTAMP}/.
#
# The dump uses --format=plain (SQL text) rather than --format=custom because
# `fly ssh console` allocates a session that is only trustworthy for text
# output; a binary custom-format archive can be corrupted in transit. The
# script verifies the dump starts with the pg_dump header and refuses to
# upload anything that does not look like a real dump.
#
# Retention: scripts/backup-prune.sh is already bucket-based and prefix-
# parameterized -- run it with S3_PREFIX pointed at this script's prefix
# (see .github/workflows/fly-backup.yml).
#
# Required env:
#   S3_BUCKET                 -- target bucket (script refuses without it)
#   AWS_ACCESS_KEY_ID         -- S3 creds (for Tigris: `fly storage` credentials)
#   AWS_SECRET_ACCESS_KEY     -- S3 creds
#   FLY_API_TOKEN             -- Fly auth for non-interactive `fly ssh console`
#                                (a logged-in local `fly` session also works;
#                                the check only warns when neither is present)
#
# Optional env:
#   FLY_APP                   -- Fly Postgres app name (default "deployai-postgres")
#   FLY_CONTROL_PLANE_APP     -- Fly control-plane app for DEK metadata
#                                (default "deployai-control-plane")
#   SKIP_DEK_METADATA         -- "1" to skip the DEK-metadata capture
#   S3_PREFIX                 -- key prefix, default "deployai/backups/fly"
#   S3_ENDPOINT_URL           -- for Tigris: https://fly.storage.tigris.dev
#   AWS_REGION                -- default "auto" (Tigris); set us-east-1 etc. for AWS
#   POSTGRES_USER, POSTGRES_DB -- default "deployai" / "deployai"
#
# Flags:
#   --dry-run                 -- validate env + print the plan; no fly/aws calls
#
# Outputs (uploaded, never echoed):
#   <ts>/postgres.sql.gz      -- gzipped plain-format pg_dump
#   <ts>/dek_metadata.json    -- {tenants: [{id, name, dek_key_id}]} JSON
#
# Exit codes: 0 ok, 2 misconfig (missing required env), 1 any other failure.

set -euo pipefail

FLY_APP="${FLY_APP:-deployai-postgres}"
FLY_CONTROL_PLANE_APP="${FLY_CONTROL_PLANE_APP:-deployai-control-plane}"
S3_PREFIX="${S3_PREFIX:-deployai/backups/fly}"
AWS_REGION="${AWS_REGION:-auto}"
POSTGRES_USER="${POSTGRES_USER:-deployai}"
POSTGRES_DB="${POSTGRES_DB:-deployai}"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *)
      echo "fly-backup: unknown argument '$arg' (only --dry-run is supported)" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${S3_BUCKET:-}" ]]; then
  echo "fly-backup: S3_BUCKET is unset -- refusing to run (would mask prod misconfiguration)" >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "fly-backup: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required" >&2
  exit 2
fi

if [[ -z "${FLY_API_TOKEN:-}" ]]; then
  # A locally-authenticated `fly` session works too, so warn rather than die.
  echo "fly-backup: FLY_API_TOKEN is unset -- relying on an existing 'fly auth' login" >&2
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
S3_BASE="s3://${S3_BUCKET}/${S3_PREFIX%/}/${TIMESTAMP}"

# Dry-run validates configuration and prints the plan without requiring
# the fly/aws tooling to be installed locally.
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "fly-backup: DRY-RUN -- would perform:"
  echo "  1. fly ssh console -a ${FLY_APP} -C \"pg_dump --format=plain --clean --if-exists --no-owner --no-privileges --username=${POSTGRES_USER} ${POSTGRES_DB}\""
  echo "  2. fly ssh console -a ${FLY_CONTROL_PLANE_APP} -C \"python -m control_plane.cli.dek_metadata\"  (skip: SKIP_DEK_METADATA=${SKIP_DEK_METADATA:-0})"
  echo "  3. gzip + upload to ${S3_BASE}/ (endpoint: ${S3_ENDPOINT_URL:-default AWS})"
  exit 0
fi

for cmd in fly aws gzip; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "fly-backup: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

DUMP_PATH="${WORKDIR}/postgres.sql"
META_PATH="${WORKDIR}/dek_metadata.json"

echo "fly-backup: pg_dump ${POSTGRES_DB} inside Fly app ${FLY_APP} ..." >&2
# --clean --if-exists so the restore path can replay this dump over an
# existing schema (mirrors what scripts/restore.sh gets from pg_restore
# --clean; plain-format dumps must bake the drops in at dump time).
fly ssh console --app "$FLY_APP" --quiet \
  --command "pg_dump --format=plain --clean --if-exists --no-owner --no-privileges --username=${POSTGRES_USER} ${POSTGRES_DB}" \
  >"$DUMP_PATH"

# `fly ssh console` exiting 0 with empty/garbled output has been observed on
# flaky sessions; never upload something that is not visibly a pg_dump.
if ! head -c 4096 "$DUMP_PATH" | grep -q "PostgreSQL database dump"; then
  echo "fly-backup: output does not look like a pg_dump (missing header) -- aborting" >&2
  exit 1
fi

dump_bytes=$(wc -c <"$DUMP_PATH" | tr -d '[:space:]')
if [[ "$dump_bytes" -le 0 ]]; then
  echo "fly-backup: pg_dump produced 0 bytes -- aborting" >&2
  exit 1
fi

if [[ "${SKIP_DEK_METADATA:-0}" == "1" ]]; then
  echo "fly-backup: SKIP_DEK_METADATA=1 -- writing empty DEK manifest marker" >&2
  echo '{"tenants": [], "skipped": true}' >"$META_PATH"
else
  echo "fly-backup: collecting tenant-DEK metadata from ${FLY_CONTROL_PLANE_APP} ..." >&2
  fly ssh console --app "$FLY_CONTROL_PLANE_APP" --quiet \
    --command "python -m control_plane.cli.dek_metadata" \
    >"$META_PATH"
  if ! head -c 1 "$META_PATH" | grep -q "{"; then
    echo "fly-backup: DEK metadata output is not JSON -- aborting (set SKIP_DEK_METADATA=1 to bypass)" >&2
    exit 1
  fi
fi

echo "fly-backup: gzipping dump ..." >&2
gzip -9 "$DUMP_PATH"
GZ_PATH="${DUMP_PATH}.gz"

aws_args=(--region "$AWS_REGION")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi

echo "fly-backup: uploading to ${S3_BASE}/ ..." >&2
aws "${aws_args[@]}" s3 cp "$GZ_PATH" "${S3_BASE}/postgres.sql.gz" >/dev/null
aws "${aws_args[@]}" s3 cp "$META_PATH" "${S3_BASE}/dek_metadata.json" >/dev/null

gz_bytes=$(wc -c <"$GZ_PATH" | tr -d '[:space:]')
meta_bytes=$(wc -c <"$META_PATH" | tr -d '[:space:]')

echo "fly-backup: done"
echo "  destination       ${S3_BASE}/"
echo "  postgres.sql.gz   ${gz_bytes} bytes (uncompressed ${dump_bytes})"
echo "  dek_metadata      ${meta_bytes} bytes"
