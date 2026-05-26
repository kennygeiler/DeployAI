"""Unit tests for the full 5-kind citation regex (v2 Phase 3 / §7.1).

Phase 3 hardens ``CITATION_RE`` to require a strict UUID payload for
every DB-kind cite, including the new ``edge`` kind that landed with
Phase 1's :class:`Citation.kind` Literal expansion.
"""

from __future__ import annotations

from control_plane.agents.agent_kenny.types import (
    CITATION_RE,
    DB_CITATION_KINDS,
    EXTERNAL_CITATION_RE,
    parse_citations,
)

_UUID = "11111111-1111-4111-8111-111111111111"
_UUID_2 = "22222222-2222-4222-8222-222222222222"
_UUID_3 = "33333333-3333-4333-8333-333333333333"


def test_db_citation_kinds_cover_phase3_set() -> None:
    assert DB_CITATION_KINDS == frozenset({"event", "node", "insight", "turn", "edge"})


def test_regex_matches_all_five_db_kinds() -> None:
    text = f"[event:{_UUID}] then [node:{_UUID}] then [insight:{_UUID}] then [turn:{_UUID}] then [edge:{_UUID}]."
    kinds = [m.group(1) for m in CITATION_RE.finditer(text)]
    assert kinds == ["event", "node", "insight", "turn", "edge"]


def test_regex_rejects_non_uuid_identifier_for_db_kinds() -> None:
    # Loose identifiers are external-only; the DB regex must not catch them.
    text = "[event:not-a-uuid] and [node:foo-123]"
    assert list(CITATION_RE.finditer(text)) == []


def test_regex_rejects_uppercase_hex_so_canonical_uuids_stay_normalized() -> None:
    # The regex is lowercase-only by spec; uppercase hex must not match.
    text = "[event:AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA]"
    assert list(CITATION_RE.finditer(text)) == []


def test_external_regex_does_not_capture_db_kinds() -> None:
    text = f"[event:{_UUID}]"
    assert list(EXTERNAL_CITATION_RE.finditer(text)) == []


def test_external_regex_captures_loose_provider_ids() -> None:
    text = "[slack:msg-abc-123] [linear:LIN-42] [gdrive:1a-_.b] [notion:p_42] [github:owner_repo-42]"
    found = [(m.group(1), m.group(2)) for m in EXTERNAL_CITATION_RE.finditer(text)]
    assert {k for k, _ in found} == {"slack", "linear", "gdrive", "notion", "github"}


def test_parse_citations_dedupes_across_db_and_external() -> None:
    text = f"first [event:{_UUID}] again [event:{_UUID}] then [edge:{_UUID_2}] and external [slack:msg-1] [slack:msg-1]"
    parsed = parse_citations(text)
    assert len(parsed) == 3
    assert (parsed[0].kind, parsed[0].identifier) == ("event", _UUID)
    assert (parsed[1].kind, parsed[1].identifier) == ("edge", _UUID_2)
    assert (parsed[2].kind, parsed[2].identifier) == ("slack", "msg-1")


def test_parse_citations_preserves_text_order() -> None:
    text = f"[node:{_UUID}] before [event:{_UUID_2}] before [edge:{_UUID_3}]"
    parsed = parse_citations(text)
    assert [p.kind for p in parsed] == ["node", "event", "edge"]


def test_parse_citations_ignores_unknown_kinds() -> None:
    # ``email`` is not a Phase 3 cite kind. Don't pick it up.
    text = f"[email:{_UUID}] but [edge:{_UUID}]"
    parsed = parse_citations(text)
    assert [p.kind for p in parsed] == ["edge"]
