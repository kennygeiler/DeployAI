#!/bin/bash
# Root-owned-volume entrypoint shim (named for its Fly.io origin — the
# behavior applies to Railway today, historical Fly before it; kept under
# the original name so the live Railway image build is byte-identical).
#
# Cloud platforms mount the persistent volume at /var/lib/postgresql/data
# root-owned (uid=0/gid=0, mode 0755), which the postgres image's own
# entrypoint can't chown when it drops to the postgres user. We run as
# root first, ensure $PGDATA is a postgres-owned subdir, and then delegate.
#
# Verbose by design — platform log shippers drop some early stdout, the
# `echo` lines give us a paper trail in the deploy logs either way.

set -x

PGDATA="${PGDATA:-/var/lib/postgresql/data/pgdata}"
export PGDATA

echo "fly-entrypoint: starting as $(id)"
echo "fly-entrypoint: PGDATA=$PGDATA"
ls -la /var/lib/postgresql/data || true

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$PGDATA" || true
  chown postgres:postgres "$PGDATA" || true
  chmod 0700 "$PGDATA" || true
fi

ls -la "$PGDATA" || true
echo "fly-entrypoint: delegating to docker-entrypoint.sh $*"

exec docker-entrypoint.sh "$@"
