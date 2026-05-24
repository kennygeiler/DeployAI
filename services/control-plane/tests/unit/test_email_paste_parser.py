"""Unit tests for ``control_plane.emails.paste_parser``."""

from __future__ import annotations

from datetime import UTC, datetime

from control_plane.emails.paste_parser import (
    ALLOWED_SOURCES,
    ParsedEmail,
    parse_email_paste,
)


def test_allowed_sources_pinned() -> None:
    assert ALLOWED_SOURCES == frozenset({"imap_paste", "mbox_paste", "manual_paste"})


_RFC5322 = (
    "Message-ID: <abc-1@deploy.ai>\r\n"
    "From: FDE <fde@deploy.ai>\r\n"
    "To: Customer Dev <dev@customer.example>, ops@customer.example\r\n"
    "Subject: Kick-off thread\r\n"
    "Date: Sun, 24 May 2026 15:00:00 +0000\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "Hello — picking up where we left off.\r\n"
)


def test_parse_single_imap_paste() -> None:
    out = parse_email_paste("imap_paste", _RFC5322)
    assert isinstance(out, ParsedEmail)
    assert out.message_id == "<abc-1@deploy.ai>"
    assert out.subject == "Kick-off thread"
    assert out.from_addr == "fde@deploy.ai"
    assert out.to_addrs == ("dev@customer.example", "ops@customer.example")
    assert out.date == datetime(2026, 5, 24, 15, 0, tzinfo=UTC)
    assert out.body_text is not None
    assert "picking up where we left off" in out.body_text
    assert out.raw == _RFC5322


def test_parse_manual_paste_single_message() -> None:
    out = parse_email_paste("manual_paste", _RFC5322)
    assert isinstance(out, ParsedEmail)
    assert out.subject == "Kick-off thread"


def test_parse_message_with_missing_headers_does_not_raise() -> None:
    raw = "Subject: orphan\r\n\r\nbody only\r\n"
    out = parse_email_paste("imap_paste", raw)
    assert isinstance(out, ParsedEmail)
    assert out.message_id is None
    assert out.from_addr is None
    assert out.to_addrs == ()
    assert out.date is None


def test_parse_bad_date_yields_none_date() -> None:
    raw = "From: a@x.com\r\nTo: b@x.com\r\nSubject: nope\r\nDate: not-a-real-date\r\n\r\nbody\r\n"
    out = parse_email_paste("imap_paste", raw)
    assert isinstance(out, ParsedEmail)
    assert out.date is None


def test_parse_multipart_picks_text_plain() -> None:
    raw = (
        "From: a@x.com\r\n"
        "To: b@x.com\r\n"
        "Subject: multi\r\n"
        'Content-Type: multipart/alternative; boundary="BOUND"\r\n'
        "\r\n"
        "--BOUND\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Plain body wins.\r\n"
        "--BOUND\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        "<p>HTML body loses.</p>\r\n"
        "--BOUND--\r\n"
    )
    out = parse_email_paste("imap_paste", raw)
    assert isinstance(out, ParsedEmail)
    assert out.body_text is not None
    assert "Plain body wins" in out.body_text


_MBOX = (
    "From fde@deploy.ai Sun May 24 15:00:00 2026\r\n"
    "Message-ID: <one@deploy.ai>\r\n"
    "From: fde@deploy.ai\r\n"
    "To: a@x.com\r\n"
    "Subject: first\r\n"
    "Date: Sun, 24 May 2026 15:00:00 +0000\r\n"
    "\r\n"
    "first body\r\n"
    "\r\n"
    "From fde@deploy.ai Sun May 24 16:00:00 2026\r\n"
    "Message-ID: <two@deploy.ai>\r\n"
    "From: fde@deploy.ai\r\n"
    "To: b@x.com\r\n"
    "Subject: second\r\n"
    "Date: Sun, 24 May 2026 16:00:00 +0000\r\n"
    "\r\n"
    "second body\r\n"
)


def test_parse_mbox_returns_list_of_messages() -> None:
    out = parse_email_paste("mbox_paste", _MBOX)
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0].subject == "first"
    assert out[0].message_id == "<one@deploy.ai>"
    assert out[0].to_addrs == ("a@x.com",)
    assert out[1].subject == "second"
    assert out[1].message_id == "<two@deploy.ai>"
    assert out[1].to_addrs == ("b@x.com",)


def test_parse_empty_mbox_returns_empty_list() -> None:
    out = parse_email_paste("mbox_paste", "")
    assert out == []
