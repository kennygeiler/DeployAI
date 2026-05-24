#!/usr/bin/env bash
# Phase C inc 12.3 -- delete S3 backup objects older than the retention window.
#
# Companion to scripts/backup.sh (writes the timestamped folders) and
# scripts/restore.sh (reads them). Enumerates `s3://${S3_BUCKET}/${S3_PREFIX}/`,
# parses each immediate sub-prefix as an ISO-8601 timestamp (UTC, format
# `YYYYMMDDTHHMMSSZ` -- matches backup.sh) and `aws s3 rm --recursive` any
# folder older than ${BACKUP_RETENTION_DAYS} (default 30).
#
# Required env:
#   S3_BUCKET                    -- target bucket (script refuses without it)
#   AWS_ACCESS_KEY_ID            -- AWS creds; for MinIO use MINIO_ROOT_USER
#   AWS_SECRET_ACCESS_KEY        -- AWS creds; for MinIO use MINIO_ROOT_PASSWORD
#   DEPLOYAI_PRUNE_CONFIRM=YES   -- mandatory operator-acknowledged kill-switch;
#                                   without it the script runs DRY (lists the
#                                   would-delete set, exits 0, changes nothing)
#
# Optional env:
#   BACKUP_RETENTION_DAYS        -- default 30; must be a positive integer
#   S3_PREFIX                    -- default "deployai/backups"
#   S3_ENDPOINT_URL              -- non-empty for MinIO (e.g. http://localhost:9000)
#   AWS_REGION                   -- default "us-east-1"
#
# Exit codes: 0 ok (including dry-run), 2 misconfig / safety guard, 1 other.

set -euo pipefail

S3_PREFIX="${S3_PREFIX:-deployai/backups}"
AWS_REGION="${AWS_REGION:-us-east-1}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

if [[ -z "${S3_BUCKET:-}" ]]; then
  echo "backup-prune: S3_BUCKET is unset -- refusing to run (would mask prod misconfiguration)" >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "backup-prune: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required" >&2
  exit 2
fi

if ! [[ "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]] || [[ "$BACKUP_RETENTION_DAYS" -lt 1 ]]; then
  echo "backup-prune: BACKUP_RETENTION_DAYS must be a positive integer (got '${BACKUP_RETENTION_DAYS}')" >&2
  exit 2
fi

for cmd in aws date; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "backup-prune: required command '$cmd' not found on PATH" >&2
    exit 1
  fi
done

DRY_RUN=1
if [[ "${DEPLOYAI_PRUNE_CONFIRM:-}" == "YES" ]]; then
  DRY_RUN=0
else
  echo "backup-prune: DEPLOYAI_PRUNE_CONFIRM=YES not set -- running DRY (no deletions)." >&2
fi

# Cutoff epoch: anything strictly older is eligible to prune. We compare epoch
# seconds, not date strings, so DST / month-boundary edges are not an issue.
NOW_EPOCH=$(date -u +%s)
CUTOFF_EPOCH=$(( NOW_EPOCH - BACKUP_RETENTION_DAYS * 86400 ))

aws_args=(--region "$AWS_REGION")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi

# Normalise prefix so the join below produces "deployai/backups/" not
# "deployai/backups//"; backup.sh writes folders right under S3_PREFIX/.
PREFIX_TRIMMED="${S3_PREFIX%/}"

# Enumerate immediate sub-prefixes (Delimiter=/) so we see each backup folder
# exactly once rather than every uploaded object. CommonPrefixes returns the
# full key prefix including the parent; the leaf timestamp is the parsed unit.
echo "backup-prune: listing s3://${S3_BUCKET}/${PREFIX_TRIMMED}/ ..." >&2
list_output=$(aws "${aws_args[@]}" s3api list-objects-v2 \
  --bucket "$S3_BUCKET" \
  --prefix "${PREFIX_TRIMMED}/" \
  --delimiter "/" \
  --query 'CommonPrefixes[].Prefix' \
  --output text 2>/dev/null || true)

if [[ -z "$list_output" || "$list_output" == "None" ]]; then
  echo "backup-prune: no backup folders found under s3://${S3_BUCKET}/${PREFIX_TRIMMED}/" >&2
  echo "backup-prune: done (kept=0 deleted=0)"
  exit 0
fi

kept=0
deleted=0
skipped=0

# `list-objects-v2 --output text` returns prefixes tab-separated on one line.
for raw in $list_output; do
  # CommonPrefixes always end with '/'; strip both the parent and the trailing
  # slash to get the bare timestamp folder name.
  leaf="${raw#"${PREFIX_TRIMMED}"/}"
  leaf="${leaf%/}"

  # Backup.sh writes `date -u +%Y%m%dT%H%M%SZ`. Reject anything that doesn't
  # match -- never delete a folder we don't understand the name of.
  if ! [[ "$leaf" =~ ^([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z$ ]]; then
    echo "backup-prune: unrecognized prefix '${leaf}', skipping" >&2
    skipped=$((skipped + 1))
    continue
  fi

  yyyy="${BASH_REMATCH[1]}"
  mm="${BASH_REMATCH[2]}"
  dd="${BASH_REMATCH[3]}"
  hh="${BASH_REMATCH[4]}"
  mi="${BASH_REMATCH[5]}"
  ss="${BASH_REMATCH[6]}"

  # GNU date and BSD date disagree on -d / -j; try GNU first, fall back to BSD.
  iso="${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}Z"
  folder_epoch=$(date -u -d "$iso" +%s 2>/dev/null \
    || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null \
    || echo "")

  if [[ -z "$folder_epoch" ]]; then
    echo "backup-prune: could not parse timestamp '${leaf}', skipping" >&2
    skipped=$((skipped + 1))
    continue
  fi

  if [[ "$folder_epoch" -ge "$CUTOFF_EPOCH" ]]; then
    kept=$((kept + 1))
    continue
  fi

  target="s3://${S3_BUCKET}/${PREFIX_TRIMMED}/${leaf}/"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "backup-prune: WOULD delete ${target}" >&2
  else
    echo "backup-prune: deleting ${target} ..." >&2
    aws "${aws_args[@]}" s3 rm "$target" --recursive >/dev/null
  fi
  deleted=$((deleted + 1))
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "backup-prune: DRY-RUN summary (kept=${kept} would_delete=${deleted} skipped=${skipped})"
  echo "backup-prune: set DEPLOYAI_PRUNE_CONFIRM=YES to actually delete." >&2
else
  echo "backup-prune: done (kept=${kept} deleted=${deleted} skipped=${skipped})"
fi
