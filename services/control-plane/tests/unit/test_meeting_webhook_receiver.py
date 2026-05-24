"""Unit tests for ``control_plane.meetings.webhook_receiver``."""

from __future__ import annotations

from datetime import UTC, datetime

from control_plane.meetings.webhook_receiver import (
    ALLOWED_SOURCES,
    ParsedMeetingEvent,
    parse_webhook_payload,
)


def test_allowed_sources_pinned() -> None:
    assert ALLOWED_SOURCES == frozenset({"zoom", "gmeet", "teams", "manual_paste"})


def test_parse_zoom_meeting_ended() -> None:
    payload = {
        "event": "meeting.ended",
        "payload": {
            "object": {
                "uuid": "abc-uuid-123",
                "id": 88001122,
                "topic": "Phase C kick-off",
                "start_time": "2026-05-24T15:00:00Z",
                "duration": 45,
                "participants": [
                    {"email": "fde@deploy.ai", "user_name": "FDE Bot"},
                    {"email": "dev@customer.example", "user_name": "Customer Dev"},
                ],
                "recording_url": "https://zoom.example/rec/abc",
            }
        },
    }
    out = parse_webhook_payload("zoom", payload)
    assert isinstance(out, ParsedMeetingEvent)
    assert out.source == "zoom"
    assert out.source_event_id == "abc-uuid-123"
    assert out.title == "Phase C kick-off"
    assert out.start_ts == datetime(2026, 5, 24, 15, 0, tzinfo=UTC)
    assert out.end_ts == datetime(2026, 5, 24, 15, 45, tzinfo=UTC)
    assert out.attendees == ("fde@deploy.ai", "dev@customer.example")
    assert out.transcript_url == "https://zoom.example/rec/abc"


def test_parse_zoom_missing_fields_does_not_raise() -> None:
    out = parse_webhook_payload("zoom", {})
    assert out.source == "zoom"
    assert out.source_event_id is None
    assert out.title is None
    assert out.start_ts is None
    assert out.end_ts is None
    assert out.attendees == ()
    assert out.transcript_url is None


def test_parse_manual_paste_canonical_shape() -> None:
    payload = {
        "source_event_id": "paste-1",
        "title": "Kick-off transcript",
        "start_ts": "2026-05-24T09:00:00+00:00",
        "end_ts": "2026-05-24T10:00:00+00:00",
        "attendees": ["alice@deploy.ai", "bob@customer.example"],
        "transcript_url": "https://uploads.deployai/transcripts/paste-1.txt",
    }
    out = parse_webhook_payload("manual_paste", payload)
    assert out.source == "manual_paste"
    assert out.source_event_id == "paste-1"
    assert out.title == "Kick-off transcript"
    assert out.start_ts == datetime(2026, 5, 24, 9, 0, tzinfo=UTC)
    assert out.end_ts == datetime(2026, 5, 24, 10, 0, tzinfo=UTC)
    assert out.attendees == ("alice@deploy.ai", "bob@customer.example")
    assert out.transcript_url == "https://uploads.deployai/transcripts/paste-1.txt"


def test_parse_manual_paste_accepts_comma_string_attendees() -> None:
    out = parse_webhook_payload(
        "manual_paste",
        {"title": "x", "attendees": "alice@x.com , bob@x.com"},
    )
    assert out.attendees == ("alice@x.com", "bob@x.com")


def test_parse_gmeet_extracts_gcal_shape() -> None:
    payload = {
        "id": "gmeet-7",
        "summary": "Discovery sync",
        "start": {"dateTime": "2026-05-24T13:30:00Z"},
        "end": {"dateTime": "2026-05-24T14:00:00Z"},
        "attendees": [
            {"email": "alice@deploy.ai"},
            {"email": "carol@customer.example"},
        ],
        "hangoutLink": "https://meet.google.com/aaa-bbb-ccc",
    }
    out = parse_webhook_payload("gmeet", payload)
    assert out.source == "gmeet"
    assert out.source_event_id == "gmeet-7"
    assert out.title == "Discovery sync"
    assert out.start_ts == datetime(2026, 5, 24, 13, 30, tzinfo=UTC)
    assert out.end_ts == datetime(2026, 5, 24, 14, 0, tzinfo=UTC)
    assert out.attendees == ("alice@deploy.ai", "carol@customer.example")
    assert out.transcript_url == "https://meet.google.com/aaa-bbb-ccc"


def test_parse_unknown_source_falls_back_to_manual_paste_shape() -> None:
    out = parse_webhook_payload(
        "exotic_vendor",
        {"title": "Whatever", "source_event_id": "x-1"},
    )
    assert out.source == "exotic_vendor"
    assert out.source_event_id == "x-1"
    assert out.title == "Whatever"


def test_parse_bad_timestamps_yield_none() -> None:
    out = parse_webhook_payload(
        "manual_paste",
        {"start_ts": "not-a-date", "end_ts": ""},
    )
    assert out.start_ts is None
    assert out.end_ts is None
