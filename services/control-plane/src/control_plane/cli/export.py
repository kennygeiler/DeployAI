"""Export an engagement packet (Markdown + PDF + JSON) for a tenant.

Mirrors the operator-CLI shape of :mod:`control_plane.cli.dek_metadata` —
exit 0 OK, 1 DB error, 2 misconfig. Writes files only; stdout gets one
summary line. The packet never includes secret material (LLM api_keys,
webhook signing secrets, DEKs).

Usage:

    python -m control_plane.cli.export \\
        --engagement <uuid> \\
        --tenant-id <uuid> \\
        --out-dir ./packet/<id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane.exceptions import NotFoundError
from control_plane.export.aggregator import gather_engagement
from control_plane.export.renderer import render_markdown, render_pdf


def _coerce_async_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgresql+psycopg2"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


async def _run(database_url: str, tenant_id: uuid.UUID, engagement_id: uuid.UUID, out_dir: Path) -> dict[str, object]:
    engine = create_async_engine(_coerce_async_url(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            return await gather_engagement(session, tenant_id, engagement_id)
    finally:
        await engine.dispose()


def _write_packet(out_dir: Path, data: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(data)
    (out_dir / "markdown.md").write_text(markdown, encoding="utf-8")
    (out_dir / "packet.pdf").write_bytes(render_pdf(markdown))
    (out_dir / "data.json").write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an engagement packet (Markdown + PDF + JSON)")
    parser.add_argument("--engagement", required=True, help="Engagement UUID")
    parser.add_argument("--tenant-id", help="Tenant UUID (defaults to $DEPLOYAI_TENANT_ID)")
    parser.add_argument("--out-dir", help="Output directory (defaults to ./packet/<engagement>)")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL; defaults to $DATABASE_URL",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    tenant_raw = args.tenant_id or os.environ.get("DEPLOYAI_TENANT_ID")
    if not tenant_raw:
        print("error: --tenant-id or $DEPLOYAI_TENANT_ID is required", file=sys.stderr)
        return 2

    try:
        tenant_id = uuid.UUID(tenant_raw)
        engagement_id = uuid.UUID(args.engagement)
    except ValueError as exc:
        print(f"error: invalid UUID: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else Path("packet") / str(engagement_id)

    try:
        data = asyncio.run(_run(args.database_url, tenant_id, engagement_id, out_dir))
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _write_packet(out_dir, data)
    print(f"wrote packet to {out_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
