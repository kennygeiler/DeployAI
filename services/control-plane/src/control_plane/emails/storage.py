"""Persistence for ``EmailIngestEvent`` — Phase C inc 9.1."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.email_events import EmailIngestEvent
from control_plane.emails.paste_parser import ParsedEmail


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
    await session.commit()
    await session.refresh(row)
    return row
