"""Emit tenant -> DEK key-id metadata as JSON for backup envelopes.

Read-only: prints `id`, `name`, and `tenant_dek_key_id` per tenant. The
secret material (`tenant_dek_ciphertext`) is never read or printed --
the script never touches that column.

Usage:

    python -m control_plane.cli.dek_metadata \\
        --database-url postgresql+psycopg://deployai:...@postgres:5432/deployai

When `--database-url` is omitted the value of `DATABASE_URL` is used. The
process exits 2 if neither source supplies a URL, 0 otherwise. Output
goes to stdout; any DB error message goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


def _coerce_sync_url(url: str) -> str:
    """Force a synchronous driver; asyncpg URLs can't run in a sync engine."""
    parsed = make_url(url)
    if parsed.drivername == "postgresql+asyncpg":
        parsed = parsed.set(drivername="postgresql+psycopg")
    elif parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def collect(database_url: str) -> dict[str, Any]:
    engine = create_engine(_coerce_sync_url(database_url), future=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name, tenant_dek_key_id FROM app_tenants ORDER BY created_at")).all()
    finally:
        engine.dispose()

    tenants: list[dict[str, Any]] = [{"id": str(row[0]), "name": row[1], "dek_key_id": row[2]} for row in rows]
    payload: dict[str, Any] = {"tenants": tenants}
    if not any(t["dek_key_id"] for t in tenants):
        payload["note"] = "dek_management_pending"
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tenant -> DEK key-id metadata as JSON")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL; defaults to $DATABASE_URL",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    try:
        payload = collect(args.database_url)
    except SQLAlchemyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    json.dump(payload, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
