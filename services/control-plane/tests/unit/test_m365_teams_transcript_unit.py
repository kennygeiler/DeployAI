"""Unit tests for Teams transcript chunking helpers."""

from __future__ import annotations

from control_plane.services.m365_teams_transcript_sync import _chunk_vtt_cues, _vtt_speaker_names


def test_vtt_speaker_names() -> None:
    vtt = "WEBVTT\n\n00:00:01.0 --> 00:00:02.0\n<v Jane Doe>Hello</v>\n"
    assert "Jane Doe" in _vtt_speaker_names(vtt)


def test_chunk_under_60_min_single() -> None:
    vtt = "WEBVTT\n\n" + "x\n\n" * 5
    parts = _chunk_vtt_cues(vtt, 30.0)
    assert len(parts) == 1


def test_chunk_90_min_multi() -> None:
    vtt = "WEBVTT\n\n" + "\n\n".join(f"00:0{i}.0 --> 00:0{i}.1\n<v S{i}>L{i}</v>" for i in range(1, 10))
    parts = _chunk_vtt_cues(vtt, 90.0)
    assert len(parts) >= 2
