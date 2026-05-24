"""Meeting webhook receiver — Phase C inc 9.2.

Twin of the D1 email-paste landing path: shape the data flow now so the
deferred OAuth swap-in (Zoom / Google Meet / Teams webhooks) is mechanical.

The parser normalises payloads from heterogeneous sources (a Zoom-style
``meeting.ended`` event, a manual transcript paste, etc.) into a single
``ParsedMeetingEvent`` shape. Downstream increments will fold these into
canonical_memory_events + matrix proposals; this slice only lands the raw
row + the parsed view.

# TODO(phase-c-9.x): OAuth-delivered transcript fetch
# -----------------------------------------------------------------------
# Once Zoom / Google Meet / Microsoft Teams OAuth lands (deferred per
# ORCHESTRATOR D1), the connector polls the provider for transcript URLs
# and POSTs to the same ``record_webhook_event`` path with a real source
# slug (``"zoom"``, ``"gmeet"``, ``"teams"``). The parser shape here is
# the contract those connectors target — keep ``ParsedMeetingEvent``
# additive-only so the OAuth path stays a thin adapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.meeting_events import MeetingWebhookEvent

ALLOWED_SOURCES: frozenset[str] = frozenset({"zoom", "gmeet", "teams", "manual_paste"})


@dataclass(frozen=True)
class ParsedMeetingEvent:
    """Source-agnostic meeting view; mirrors the eventual OAuth payload shape."""

    source: str
    source_event_id: str | None
    title: str | None
    start_ts: datetime | None
    end_ts: datetime | None
    attendees: tuple[str, ...] = ()
    transcript_url: str | None = None


def parse_webhook_payload(source: str, payload: dict[str, Any]) -> ParsedMeetingEvent:
    """Normalise raw payload to ``ParsedMeetingEvent``; unknown sources fall through to manual-paste."""
    if source == "zoom":
        return _parse_zoom(payload)
    if source == "gmeet":
        return _parse_gmeet(payload)
    if source == "teams":
        return _parse_teams(payload)
    return _parse_manual_paste(source, payload)


def _parse_zoom(payload: dict[str, Any]) -> ParsedMeetingEvent:
    obj = _as_dict(payload.get("payload", {}).get("object")) if isinstance(payload.get("payload"), dict) else {}
    if not obj:
        obj = _as_dict(payload.get("object"))
    title = _as_str(obj.get("topic"))
    start_ts = _parse_ts(obj.get("start_time"))
    end_ts = _compute_end(start_ts, obj.get("duration"))
    attendees = _zoom_attendees(obj)
    transcript_url = _as_str(obj.get("recording_url") or obj.get("transcript_url"))
    source_event_id = _as_str(obj.get("uuid") or obj.get("id"))
    return ParsedMeetingEvent(
        source="zoom",
        source_event_id=source_event_id,
        title=title,
        start_ts=start_ts,
        end_ts=end_ts,
        attendees=attendees,
        transcript_url=transcript_url,
    )


def _parse_gmeet(payload: dict[str, Any]) -> ParsedMeetingEvent:
    title = _as_str(payload.get("summary") or payload.get("title"))
    start_ts = _parse_ts(_dig(payload, "start", "dateTime") or payload.get("start_time"))
    end_ts = _parse_ts(_dig(payload, "end", "dateTime") or payload.get("end_time"))
    attendees = _gcal_attendees(payload.get("attendees"))
    transcript_url = _as_str(payload.get("transcript_url") or payload.get("hangoutLink"))
    source_event_id = _as_str(payload.get("id") or payload.get("iCalUID"))
    return ParsedMeetingEvent(
        source="gmeet",
        source_event_id=source_event_id,
        title=title,
        start_ts=start_ts,
        end_ts=end_ts,
        attendees=attendees,
        transcript_url=transcript_url,
    )


def _parse_teams(payload: dict[str, Any]) -> ParsedMeetingEvent:
    title = _as_str(payload.get("subject") or payload.get("title"))
    start_ts = _parse_ts(_dig(payload, "start", "dateTime") or payload.get("startDateTime"))
    end_ts = _parse_ts(_dig(payload, "end", "dateTime") or payload.get("endDateTime"))
    attendees = _gcal_attendees(payload.get("attendees"))
    transcript_url = _as_str(payload.get("recording_url") or payload.get("transcript_url"))
    source_event_id = _as_str(payload.get("id") or payload.get("iCalUId"))
    return ParsedMeetingEvent(
        source="teams",
        source_event_id=source_event_id,
        title=title,
        start_ts=start_ts,
        end_ts=end_ts,
        attendees=attendees,
        transcript_url=transcript_url,
    )


def _parse_manual_paste(source: str, payload: dict[str, Any]) -> ParsedMeetingEvent:
    title = _as_str(payload.get("title") or payload.get("subject"))
    start_ts = _parse_ts(payload.get("start_ts") or payload.get("start_time"))
    end_ts = _parse_ts(payload.get("end_ts") or payload.get("end_time"))
    raw_attendees = payload.get("attendees")
    if isinstance(raw_attendees, list):
        attendees = tuple(str(a).strip() for a in raw_attendees if str(a).strip())
    elif isinstance(raw_attendees, str):
        attendees = tuple(a.strip() for a in raw_attendees.split(",") if a.strip())
    else:
        attendees = ()
    transcript_url = _as_str(payload.get("transcript_url"))
    source_event_id = _as_str(payload.get("source_event_id") or payload.get("external_event_id"))
    return ParsedMeetingEvent(
        source=source,
        source_event_id=source_event_id,
        title=title,
        start_ts=start_ts,
        end_ts=end_ts,
        attendees=attendees,
        transcript_url=transcript_url,
    )


async def record_webhook_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source: str,
    payload: dict[str, Any],
    engagement_id: uuid.UUID | None = None,
    parsed: ParsedMeetingEvent | None = None,
) -> MeetingWebhookEvent:
    """Persist the raw webhook payload + the parsed external id."""
    if parsed is None:
        parsed = parse_webhook_payload(source, payload)
    row = MeetingWebhookEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        source=source,
        external_event_id=parsed.source_event_id,
        payload=payload,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _as_dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _as_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s or None


def _dig(d: dict[str, Any], *path: str) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _compute_end(start: datetime | None, duration: Any) -> datetime | None:
    if start is None or not isinstance(duration, int | float) or isinstance(duration, bool) or duration <= 0:
        return None
    return start + timedelta(minutes=float(duration))


def _zoom_attendees(obj: dict[str, Any]) -> tuple[str, ...]:
    raw = obj.get("participants")
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            email = entry.get("email") or entry.get("user_email") or entry.get("user_name")
            if isinstance(email, str) and email.strip():
                out.append(email.strip())
        elif isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return tuple(out)


def _gcal_attendees(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            email = entry.get("email")
            if not isinstance(email, str) or not email.strip():
                addr_obj = entry.get("emailAddress")
                if isinstance(addr_obj, dict):
                    email = addr_obj.get("address")
            if isinstance(email, str) and email.strip():
                out.append(email.strip())
        elif isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return tuple(out)
