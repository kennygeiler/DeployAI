"""Backfill missing daily matrix snapshots for one engagement.

Usage:

    python -m control_plane.cli.snapshot_backfill \\
        --engagement <uuid> \\
        --days N \\
        [--tenant-id <uuid>] \\
        [--rebuild]

Exit 0 OK, 1 DB error, 2 misconfig. Prints the count of snapshot rows written.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane.snapshots.cron import backfill_snapshots


def _coerce_async_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgresql+psycopg2"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


async def _run(
    database_url: str,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    days: int,
    rebuild: bool,
) -> int:
    engine = create_async_engine(_coerce_async_url(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            written = await backfill_snapshots(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                days=days,
                rebuild=rebuild,
            )
            await session.commit()
            return written
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill daily matrix snapshots for one engagement")
    parser.add_argument("--engagement", required=True, help="Engagement UUID")
    parser.add_argument("--days", type=int, required=True, help="Number of UTC days back to fill")
    parser.add_argument("--tenant-id", help="Tenant UUID (defaults to $DEPLOYAI_TENANT_ID)")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL; defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing in-window rows for this engagement before re-inserting.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    tenant_raw = args.tenant_id or os.environ.get("DEPLOYAI_TENANT_ID")
    if not tenant_raw:
        print("error: --tenant-id or $DEPLOYAI_TENANT_ID is required", file=sys.stderr)
        return 2

    if args.days <= 0:
        print("error: --days must be > 0", file=sys.stderr)
        return 2

    try:
        tenant_id = uuid.UUID(tenant_raw)
        engagement_id = uuid.UUID(args.engagement)
    except ValueError as exc:
        print(f"error: invalid UUID: {exc}", file=sys.stderr)
        return 2

    try:
        written = asyncio.run(_run(args.database_url, tenant_id, engagement_id, args.days, args.rebuild))
    except SQLAlchemyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {written} snapshots")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
