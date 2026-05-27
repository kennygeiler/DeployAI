#!/usr/bin/env bash
# Fly.io-specific entrypoint shim.
#
# Fly mounts the persistent volume at /var/lib/postgresql/data with uid=0/gid=0
# and mode 0755, which is unwritable for the postgres user. The stock postgres
# image expects to chown $PGDATA itself, but when it boots non-root that fails
# with "Permission denied". This shim, which always runs as root, prepares the
# mount + PGDATA subdirectory and then delegates to the stock entrypoint.
#
# It is a no-op on docker-compose, where the volume is already postgres-owned.

set -e

if [ "$(id -u)" = "0" ]; then
  : "${PGDATA:=/var/lib/postgresql/data}"
  mkdir -p "$PGDATA"
  chown postgres:postgres "$PGDATA"
  chmod 0700 "$PGDATA"
fi

exec docker-entrypoint.sh "$@"
