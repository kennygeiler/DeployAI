"""Backfill ``ledger_events`` from existing source tables for one tenant.

Reads ``email_ingest_events``, ``meeting_webhook_events``, ``matrix_proposals``
(create + accept/reject), ``matrix_nodes``, ``matrix_edges``, and
``matrix_insights`` for the named tenant, then writes one ledger row per
source row + the appropriate cause/affect edges. Idempotent via
``(source_kind, source_ref)`` — re-running is a no-op for rows that already
exist. See ``docs/design/timeline-ledger.md`` §4.3-§4.4 for the source-kind
mapping.

Usage:

    python -m control_plane.cli.ledger_backfill --tenant-id <uuid> [--dry-run]

When ``--database-url`` is omitted the value of ``DATABASE_URL`` is used.
``--dry-run`` reports the row-count plan per source_kind without writing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, Row, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class _PendingEvent:
    """One ledger row to insert + the cause/affect edges that go with it."""

    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    occurred_at: Any
    actor_kind: str
    actor_id: str | None
    source_kind: str
    source_ref: uuid.UUID
    summary: str
    detail: dict[str, Any]
    caused_by_source_ref: uuid.UUID | None = None
    affects: tuple[tuple[str, uuid.UUID], ...] = ()


def _coerce_sync_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername == "postgresql+asyncpg":
        parsed = parsed.set(drivername="postgresql+psycopg")
    elif parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def _truncate(value: str | None, limit: int = 500) -> str:
    if not value:
        return "(no summary)"
    cleaned = value.strip().replace("\n", " ")
    return cleaned[: limit - 1] + "…" if len(cleaned) >= limit else cleaned


def _collect_email_ingest(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text(
            "SELECT id, engagement_id, COALESCE(parsed_date, received_at) AS occurred_at, "
            "       source, parsed_subject, parsed_from "
            "FROM email_ingest_events WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    ).all()
    return [
        _PendingEvent(
            tenant_id=tenant_id,
            engagement_id=row.engagement_id,
            occurred_at=row.occurred_at,
            actor_kind="system",
            actor_id=row.source,
            source_kind="email_ingest",
            source_ref=row.id,
            summary=_truncate(f"email: {row.parsed_subject or '(no subject)'}"),
            detail={"source": row.source, "from": row.parsed_from},
        )
        for row in rows
    ]


def _collect_meeting_webhook(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text(
            "SELECT id, engagement_id, received_at, source, external_event_id "
            "FROM meeting_webhook_events WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    ).all()
    return [
        _PendingEvent(
            tenant_id=tenant_id,
            engagement_id=row.engagement_id,
            occurred_at=row.received_at,
            actor_kind="system",
            actor_id=row.source,
            source_kind="meeting_webhook",
            source_ref=row.id,
            summary=_truncate(f"meeting webhook from {row.source}"),
            detail={"source": row.source, "external_event_id": row.external_event_id},
        )
        for row in rows
    ]


def _collect_proposals(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text(
            "SELECT id, engagement_id, created_at, decided_at, decided_by, status, "
            "       proposal_kind, result_node_id, result_edge_id "
            "FROM matrix_proposals WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    ).all()
    pending: list[_PendingEvent] = []
    for row in rows:
        pending.append(
            _PendingEvent(
                tenant_id=tenant_id,
                engagement_id=row.engagement_id,
                occurred_at=row.created_at,
                actor_kind="agent:matrix_extractor",
                actor_id=None,
                source_kind="llm_proposal_created",
                source_ref=row.id,
                summary=_truncate(f"proposal ({row.proposal_kind}) created"),
                detail={"proposal_kind": row.proposal_kind, "status": row.status},
            )
        )
        if row.status not in ("accepted", "rejected") or row.decided_at is None:
            continue
        affects: tuple[tuple[str, uuid.UUID], ...] = ()
        if row.status == "accepted":
            if row.result_node_id is not None:
                affects = (("matrix_node", row.result_node_id),)
            elif row.result_edge_id is not None:
                affects = (("matrix_edge", row.result_edge_id),)
        pending.append(
            _PendingEvent(
                tenant_id=tenant_id,
                engagement_id=row.engagement_id,
                occurred_at=row.decided_at,
                actor_kind="user" if row.decided_by else "system",
                actor_id=row.decided_by,
                source_kind=f"proposal_{row.status}",
                source_ref=row.id,
                summary=_truncate(f"proposal {row.status}"),
                detail={"proposal_kind": row.proposal_kind},
                caused_by_source_ref=row.id,
                affects=affects,
            )
        )
    return pending


def _collect_matrix_nodes(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text("SELECT id, engagement_id, created_at, node_type, title FROM matrix_nodes WHERE tenant_id = :t"),
        {"t": str(tenant_id)},
    ).all()
    return [
        _PendingEvent(
            tenant_id=tenant_id,
            engagement_id=row.engagement_id,
            occurred_at=row.created_at,
            actor_kind="system",
            actor_id=None,
            source_kind="matrix_node_created",
            source_ref=row.id,
            summary=_truncate(f"{row.node_type}: {row.title}"),
            detail={"node_type": row.node_type},
            affects=(("matrix_node", row.id),),
        )
        for row in rows
    ]


def _collect_matrix_edges(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text(
            "SELECT id, engagement_id, created_at, edge_type, from_node_id, to_node_id "
            "FROM matrix_edges WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    ).all()
    return [
        _PendingEvent(
            tenant_id=tenant_id,
            engagement_id=row.engagement_id,
            occurred_at=row.created_at,
            actor_kind="system",
            actor_id=None,
            source_kind="matrix_edge_created",
            source_ref=row.id,
            summary=_truncate(f"edge {row.edge_type}"),
            detail={"edge_type": row.edge_type},
            affects=(("matrix_edge", row.id),),
        )
        for row in rows
    ]


def _collect_matrix_insights(conn: Any, tenant_id: uuid.UUID) -> list[_PendingEvent]:
    rows = conn.execute(
        text(
            "SELECT id, engagement_id, created_at, decided_at, status, agent, "
            "       insight_type, title "
            "FROM matrix_insights WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    ).all()
    pending: list[_PendingEvent] = []
    for row in rows:
        pending.append(
            _PendingEvent(
                tenant_id=tenant_id,
                engagement_id=row.engagement_id,
                occurred_at=row.created_at,
                actor_kind=f"agent:{row.agent}",
                actor_id=None,
                source_kind="insight_opened",
                source_ref=row.id,
                summary=_truncate(f"{row.insight_type}: {row.title}"),
                detail={"agent": row.agent, "insight_type": row.insight_type},
                affects=(("insight", row.id),),
            )
        )
        if row.status in ("dismissed", "resolved") and row.decided_at is not None:
            pending.append(
                _PendingEvent(
                    tenant_id=tenant_id,
                    engagement_id=row.engagement_id,
                    occurred_at=row.decided_at,
                    actor_kind=f"agent:{row.agent}",
                    actor_id=None,
                    source_kind="insight_closed",
                    source_ref=row.id,
                    summary=_truncate(f"insight {row.status}"),
                    detail={"final_status": row.status},
                    caused_by_source_ref=row.id,
                    affects=(("insight", row.id),),
                )
            )
    return pending


_COLLECTORS = (
    _collect_email_ingest,
    _collect_meeting_webhook,
    _collect_proposals,
    _collect_matrix_nodes,
    _collect_matrix_edges,
    _collect_matrix_insights,
)


def _existing_keys(conn: Any, tenant_id: uuid.UUID) -> set[tuple[str, uuid.UUID]]:
    rows: Iterable[Row[Any]] = conn.execute(
        text("SELECT source_kind, source_ref FROM ledger_events WHERE tenant_id = :t AND source_ref IS NOT NULL"),
        {"t": str(tenant_id)},
    ).all()
    return {(row.source_kind, row.source_ref) for row in rows}


def _index_by_source_ref(conn: Any, tenant_id: uuid.UUID) -> dict[tuple[str, uuid.UUID], uuid.UUID]:
    rows = conn.execute(
        text("SELECT id, source_kind, source_ref FROM ledger_events WHERE tenant_id = :t AND source_ref IS NOT NULL"),
        {"t": str(tenant_id)},
    ).all()
    return {(row.source_kind, row.source_ref): row.id for row in rows}


def _insert_event(conn: Any, ev: _PendingEvent) -> uuid.UUID:
    row = conn.execute(
        text(
            "INSERT INTO ledger_events "
            "(tenant_id, engagement_id, occurred_at, actor_kind, actor_id, "
            " source_kind, source_ref, summary, detail) "
            "VALUES (:t, :e, :o, :ak, :ai, :sk, :sr, :s, CAST(:d AS jsonb)) "
            "RETURNING id"
        ),
        {
            "t": str(ev.tenant_id),
            "e": str(ev.engagement_id) if ev.engagement_id else None,
            "o": ev.occurred_at,
            "ak": ev.actor_kind,
            "ai": ev.actor_id,
            "sk": ev.source_kind,
            "sr": str(ev.source_ref),
            "s": ev.summary,
            "d": json.dumps(ev.detail),
        },
    ).one()
    new_id: uuid.UUID = row.id
    return new_id


def _link_cause(conn: Any, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    if event_id == caused_by_id:
        return
    conn.execute(
        text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :c) ON CONFLICT DO NOTHING"),
        {"e": str(event_id), "c": str(caused_by_id)},
    )


def _link_affect(conn: Any, event_id: uuid.UUID, kind: str, entity_id: uuid.UUID) -> None:
    conn.execute(
        text(
            "INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) "
            "VALUES (:e, :k, :i) ON CONFLICT DO NOTHING"
        ),
        {"e": str(event_id), "k": kind, "i": str(entity_id)},
    )


def _plan(
    events: list[_PendingEvent], existing: set[tuple[str, uuid.UUID]]
) -> tuple[list[_PendingEvent], dict[str, int]]:
    todo: list[_PendingEvent] = []
    counts: dict[str, int] = {}
    for ev in events:
        if (ev.source_kind, ev.source_ref) in existing:
            continue
        todo.append(ev)
        counts[ev.source_kind] = counts.get(ev.source_kind, 0) + 1
    return todo, counts


# source_kinds that represent the "create" half of a paired source_ref; the
# accept/reject/close halves point back at the create row via caused_by.
_CREATE_KINDS: frozenset[str] = frozenset({"llm_proposal_created", "insight_opened"})


def run(
    database_url: str,
    tenant_id: uuid.UUID,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    engine: Engine = create_engine(_coerce_sync_url(database_url), future=True)
    try:
        with engine.connect() as conn:
            collected: list[_PendingEvent] = []
            for collector in _COLLECTORS:
                collected.extend(collector(conn, tenant_id))
            existing = _existing_keys(conn, tenant_id)
            todo, counts = _plan(collected, existing)

        if dry_run:
            return {
                "tenant_id": str(tenant_id),
                "dry_run": True,
                "planned_counts": counts,
                "total_planned": len(todo),
                "already_present": len(existing),
            }

        # Two-pass insert so paired CREATE→CLOSE source_refs always link.
        # We can't rely on occurred_at order alone: matrix_proposals.created_at
        # is a DB-side `now()` while decided_at can be a Python-side value
        # supplied before the row is INSERTed, so created_at > decided_at on
        # backfilled accept/reject rows. Sort-tiebreaker by `is_create` would
        # only help when occurred_at is exactly equal.
        # Pass 1: every event whose source_kind is in _CREATE_KINDS, sorted
        # by occurred_at. Pass 2: everything else, sorted by occurred_at —
        # cause-edge lookup always finds its parent.
        creates = sorted(
            (e for e in todo if e.source_kind in _CREATE_KINDS),
            key=lambda e: e.occurred_at,
        )
        non_creates = sorted(
            (e for e in todo if e.source_kind not in _CREATE_KINDS),
            key=lambda e: e.occurred_at,
        )
        ordered = [*creates, *non_creates]
        written: dict[str, int] = {}
        with engine.begin() as conn:
            existing_index = _index_by_source_ref(conn, tenant_id)
            for ev in ordered:
                new_id = _insert_event(conn, ev)
                if ev.source_kind in _CREATE_KINDS:
                    existing_index[(ev.source_kind, ev.source_ref)] = new_id
                if ev.caused_by_source_ref is not None:
                    for parent_kind in _CREATE_KINDS:
                        parent_id = existing_index.get((parent_kind, ev.caused_by_source_ref))
                        if parent_id is not None:
                            _link_cause(conn, new_id, parent_id)
                for kind, entity_id in ev.affects:
                    _link_affect(conn, new_id, kind, entity_id)
                written[ev.source_kind] = written.get(ev.source_kind, 0) + 1

        return {
            "tenant_id": str(tenant_id),
            "dry_run": False,
            "written_counts": written,
            "total_written": sum(written.values()),
            "already_present": len(existing),
        }
    finally:
        engine.dispose()


def _render(result: Mapping[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill ledger_events for one tenant from existing source tables",
    )
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID to backfill")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL; defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned row counts per source_kind without writing",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    try:
        tenant_id = uuid.UUID(args.tenant_id)
    except ValueError:
        print(f"error: --tenant-id must be a UUID (got {args.tenant_id!r})", file=sys.stderr)
        return 2

    try:
        result = run(args.database_url, tenant_id, dry_run=args.dry_run)
    except SQLAlchemyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(_render(result))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
