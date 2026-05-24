"""Email paste parser — Phase C inc 9.1.

Pure functions over stdlib ``email`` + ``mailbox``. Normalises pasted
RFC 5322 messages (one message at a time) and pasted mbox content (zero
or more messages) into a single ``ParsedEmail`` shape.

# TODO(phase-c-9.x): OAuth-delivered email fetch
# -----------------------------------------------------------------------
# Once Gmail / M365 OAuth lands (deferred per ORCHESTRATOR D1), the
# connector polls the provider for new messages and POSTs the Gmail API
# ``message.raw`` (a base64url-encoded RFC 5322 message) — or its M365
# equivalent — to the same ingest endpoint with source slug ``"gmail"`` /
# ``"m365"``. The parser shape here is the contract those connectors
# target: ``ParsedEmail`` mirrors what surfaces from a Gmail API message
# resource (Message-ID, Subject, From, To, Date, body text). Keep
# ``ParsedEmail`` additive-only so the OAuth path stays a thin adapter.
"""

from __future__ import annotations

import io
import mailbox
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_string
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

ALLOWED_SOURCES: frozenset[str] = frozenset({"imap_paste", "mbox_paste", "manual_paste"})


@dataclass(frozen=True)
class ParsedEmail:
    """Source-agnostic email view; mirrors the eventual OAuth-Gmail payload shape."""

    message_id: str | None
    subject: str | None
    from_addr: str | None
    to_addrs: tuple[str, ...] = ()
    date: datetime | None = None
    body_text: str | None = None
    raw: str = field(default="", repr=False)


def parse_email_paste(source: str, raw: str) -> ParsedEmail | list[ParsedEmail]:
    """Parse a pasted email or mbox blob.

    ``mbox_paste`` returns a list (zero or more). Other sources return a
    single ``ParsedEmail`` derived from one RFC 5322 message.
    """
    if source == "mbox_paste":
        return _parse_mbox(raw)
    return _parse_single(raw)


def _parse_single(raw: str) -> ParsedEmail:
    msg = message_from_string(raw)
    return _parsed_from_message(msg, raw)


def _parse_mbox(raw: str) -> list[ParsedEmail]:
    if not raw.strip():
        return []
    # ``mailbox.mbox`` reads from a file path. Use a temporary file so we
    # do not assume the caller has one (the paste arrives as a string).
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "paste.mbox"
        path.write_text(raw, encoding="utf-8")
        box = mailbox.mbox(str(path))
        try:
            out: list[ParsedEmail] = []
            for key in box.keys():
                msg = box.get_message(key)
                # ``mbox.get_message`` returns ``mboxMessage`` — a Message
                # subclass; re-serialise so ``raw`` mirrors what the row
                # stores for that single message.
                raw_msg = msg.as_string()
                out.append(_parsed_from_message(msg, raw_msg))
            return out
        finally:
            box.close()


def _parsed_from_message(msg: Message, raw: str) -> ParsedEmail:
    return ParsedEmail(
        message_id=_clean(msg.get("Message-ID") or msg.get("Message-Id")),
        subject=_clean(msg.get("Subject")),
        from_addr=_first_addr(msg.get_all("From")),
        to_addrs=_all_addrs(msg.get_all("To")),
        date=_parse_date(msg.get("Date")),
        body_text=_body_text(msg),
        raw=raw,
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s or None


def _first_addr(headers: list[str] | None) -> str | None:
    if not headers:
        return None
    pairs = getaddresses(headers)
    for _name, addr in pairs:
        a = addr.strip()
        if a:
            return a
    return None


def _all_addrs(headers: list[str] | None) -> tuple[str, ...]:
    if not headers:
        return ()
    out: list[str] = []
    for _name, addr in getaddresses(headers):
        a = addr.strip()
        if a:
            out.append(a)
    return tuple(out)


def _parse_date(raw: str | None) -> datetime | None:
    if not raw or not raw.strip():
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _body_text(msg: Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = _decode_part(part)
                if payload is not None:
                    return payload
        return None
    if msg.get_content_type() != "text/plain":
        return None
    return _decode_part(msg)


def _decode_part(part: Message) -> str | None:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes | bytearray):
        text = part.get_payload()
        if isinstance(text, str):
            return text or None
        return None
    charset = part.get_content_charset() or "utf-8"
    try:
        return io.BytesIO(payload).read().decode(charset, errors="replace") or None
    except LookupError:
        return payload.decode("utf-8", errors="replace") or None
