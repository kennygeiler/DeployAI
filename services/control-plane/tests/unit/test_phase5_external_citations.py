"""Unit tests for Phase 5 Wave 1C external citation prefixes (§9.3).

The citation verifier learns five external (MCP-provider) prefixes —
slack / linear / gdrive / notion / github. They are recorded but never
DB-checked; the audit ledger captures the upstream call. Unknown
prefixes (e.g. ``[twitter:abc]``) MUST still surface as
``citation_unverified`` so we never silently trust an unfamiliar source.

This file covers the parser + verifier seams; the SSE-frame end-to-end
ordering is exercised by ``tests/integration/test_phase5_external_citations_stream.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from control_plane.agents.agent_kenny.nodes.citations import verify_citations
from control_plane.agents.agent_kenny.types import (
    EXTERNAL_CITATION_KINDS,
    AgentState,
    CitationExternalChunk,
    CitationUnverifiedChunk,
    CitationVerifiedChunk,
    parse_citations,
)

_TENANT = uuid.UUID("00000000-0000-7000-8000-000000000a01")
_ENG = uuid.UUID("00000000-0000-7000-8000-000000000a02")
_ACTOR = uuid.UUID("00000000-0000-7000-8000-000000000a03")
_INTERNAL_UUID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _state(text: str) -> AgentState:
    s = AgentState(
        tenant_id=_TENANT,
        engagement_id=_ENG,
        actor_user_id=_ACTOR,
        user_message="hi",
        started_at=datetime(2026, 5, 26, tzinfo=UTC),
    )
    s.accumulated_text = text
    return s


class _StubResult:
    def __init__(self, value: Any) -> None:
        self._v = value

    def scalar_one_or_none(self) -> Any:
        return self._v


class _StubSession:
    """Async session stub — every DB lookup misses."""

    def __init__(self) -> None:
        self.execute_calls = 0

    async def execute(self, _stmt: Any) -> _StubResult:
        self.execute_calls += 1
        return _StubResult(None)


# ---------------------------------------------------------------------------
# Parser coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_kind", "expected_id"),
    [
        ("see [slack:msg-id]", "slack", "msg-id"),
        ("see [slack:C0123/1700000000.123456]", "slack", "C0123/1700000000.123456"),
        ("see [linear:LIN-42]", "linear", "LIN-42"),
        ("see [gdrive:1AbCdEfGhIjKlMn-_.xyz]", "gdrive", "1AbCdEfGhIjKlMn-_.xyz"),
        ("see [notion:8f3e2d1c-2e2e-4f00-8a8a-000000000001]", "notion", "8f3e2d1c-2e2e-4f00-8a8a-000000000001"),
        ("see [github:deployai/control-plane#182]", "github", "deployai/control-plane#182"),
        ("see [github:deployai/control-plane@abc123def456]", "github", "deployai/control-plane@abc123def456"),
    ],
)
def test_each_external_prefix_parses(text: str, expected_kind: str, expected_id: str) -> None:
    parsed = parse_citations(text)
    assert len(parsed) == 1, parsed
    assert parsed[0].kind == expected_kind
    assert parsed[0].identifier == expected_id
    assert parsed[0].kind in EXTERNAL_CITATION_KINDS


def test_mixed_reply_buckets_internal_and_external_correctly() -> None:
    text = (
        f"DB hit [event:{_INTERNAL_UUID}], "
        "slack note [slack:msg-abc], "
        "linear issue [linear:LIN-7], "
        "gdrive [gdrive:fileid_42], "
        "notion [notion:page_42], "
        "github [github:owner/repo#9], "
        "and unknown [twitter:tw-1]."
    )
    parsed = parse_citations(text)
    kinds = [p.kind for p in parsed]
    # Internal first (text order), then five external, then unknown.
    assert kinds == ["event", "slack", "linear", "gdrive", "notion", "github", "twitter"]


# ---------------------------------------------------------------------------
# Verifier + chunk routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_citation_emits_citation_external_chunk_not_verified_or_unverified() -> None:
    emitted: list[Any] = []

    async def _emit(chunk: Any) -> None:
        emitted.append(chunk)

    session = _StubSession()
    state = _state("Notes: [slack:msg-abc] and [linear:LIN-42] and [github:owner/repo#7].")
    await verify_citations(session, state, emit=_emit)

    # All three external citations must produce CitationExternalChunk.
    external_chunks = [c for c in emitted if isinstance(c, CitationExternalChunk)]
    assert len(external_chunks) == 3
    assert {c.kind for c in external_chunks} == {"slack", "linear", "github"}

    # Critically: NO verified / unverified frames for external prefixes.
    verified_chunks = [c for c in emitted if isinstance(c, CitationVerifiedChunk)]
    unverified_chunks = [c for c in emitted if isinstance(c, CitationUnverifiedChunk)]
    assert verified_chunks == []
    assert unverified_chunks == []

    # And the verifier MUST NOT hit the DB for external citations.
    assert session.execute_calls == 0

    # Report bucket: all three land in ``external`` with ``external_trust``.
    assert state.citation_report is not None
    assert len(state.citation_report.external) == 3
    assert {c.outcome for c in state.citation_report.external} == {"external_trust"}


@pytest.mark.asyncio
async def test_unknown_prefix_emits_citation_unverified_not_external() -> None:
    emitted: list[Any] = []

    async def _emit(chunk: Any) -> None:
        emitted.append(chunk)

    session = _StubSession()
    state = _state("Saw it on [twitter:abc-123] earlier today.")
    await verify_citations(session, state, emit=_emit)

    # Unknown prefix must NOT be promoted to external_trust silently.
    external_chunks = [c for c in emitted if isinstance(c, CitationExternalChunk)]
    assert external_chunks == []

    unverified_chunks = [c for c in emitted if isinstance(c, CitationUnverifiedChunk)]
    assert len(unverified_chunks) == 1
    assert unverified_chunks[0].kind == "twitter"
    assert unverified_chunks[0].identifier == "abc-123"
    assert unverified_chunks[0].outcome == "not_found"

    assert state.citation_report is not None
    assert len(state.citation_report.not_found) == 1
    assert len(state.citation_report.external) == 0


@pytest.mark.asyncio
async def test_external_citation_skips_db_lookup_entirely() -> None:
    """Phase 5 §9.3: external citations are trusted upstream — no DB hit."""
    session = _StubSession()
    state = _state("Refs: [slack:msg-1] [linear:LIN-1] [gdrive:f-1] [notion:p-1] [github:o/r#1].")
    await verify_citations(session, state)
    # Five external citations, zero DB lookups.
    assert session.execute_calls == 0
    assert state.citation_report is not None
    assert len(state.citation_report.external) == 5
