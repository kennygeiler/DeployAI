"""Persistence for ``EmailIngestEvent`` — Phase C inc 9.1."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.email_events import EmailIngestEvent
from control_plane.emails.paste_parser import ParsedEmail
from control_plane.ledger import emit_ledger_event


async def record_email_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source: str,
    raw: str,
    parsed: ParsedEmail,
    engagement_id: uuid.UUID | None = None,
) -> EmailIngestEvent:
    """Persist one parsed email + its raw payload as an ingest event row."""
    row = EmailIngestEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        source=source,
        external_message_id=parsed.message_id,
        raw_payload=raw,
        parsed_subject=parsed.subject,
        parsed_from=parsed.from_addr,
        parsed_to=list(parsed.to_addrs),
        parsed_date=parsed.date,
    )
    session.add(row)
    await session.flush()
    occurred_at = parsed.date or datetime.now(UTC)
    summary = (parsed.subject or f"email ingested from {source}")[:500]
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=occurred_at,
        actor_kind="system",
        actor_id=None,
        source_kind="email_ingest",
        source_ref=row.id,
        summary=summary,
        detail={
            "source": source,
            "external_message_id": parsed.message_id,
            "from": parsed.from_addr,
            "to": list(parsed.to_addrs),
        },
    )
    await session.commit()
    await session.refresh(row)
    return row
