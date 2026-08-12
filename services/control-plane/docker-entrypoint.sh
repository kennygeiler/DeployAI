#!/bin/sh
# Control-plane container entrypoint.
#
# Railway (unlike Fly or compose) has no separate release-command or
# process-group mechanism, so one image serves every role:
#
#   SERVICE_ROLE=api       (default) run uvicorn
#   SERVICE_ROLE=embedder  run the embedding worker
#   RUN_MIGRATIONS=1       alembic upgrade head before starting (api role);
#                          alembic needs a sync driver, so +asyncpg is
#                          swapped for +psycopg for the migration run only.
#
# Compose and Fly keep their existing dedicated migrate mechanisms; with
# neither env var set this behaves exactly like the old CMD.
set -eu

ROLE="${SERVICE_ROLE:-api}"

# Platforms without file-mount secrets (Railway) pass the RS256 session
# signing key as base64 env; materialize it where the settings expect a path.
if [ -n "${DEPLOYAI_JWT_PRIVATE_KEY_B64:-}" ] && [ -z "${DEPLOYAI_JWT_PRIVATE_KEY_PATH:-}" ]; then
  umask 077
  printf '%s' "$DEPLOYAI_JWT_PRIVATE_KEY_B64" | base64 -d > /tmp/jwt-private.pem
  export DEPLOYAI_JWT_PRIVATE_KEY_PATH=/tmp/jwt-private.pem
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ] && [ "$ROLE" = "api" ]; then
  echo "entrypoint: running alembic upgrade head"
  DATABASE_URL="$(printf '%s' "${DATABASE_URL:-}" | sed 's/+asyncpg/+psycopg/')" alembic upgrade head
fi

case "$ROLE" in
  embedder)
    exec python -m control_plane.cli.embedder
    ;;
  api)
    exec uvicorn control_plane.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  *)
    echo "entrypoint: unknown SERVICE_ROLE '$ROLE'" >&2
    exit 1
    ;;
esac
