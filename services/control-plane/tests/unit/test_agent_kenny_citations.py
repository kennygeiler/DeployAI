"""Unit tests for citation verification logic (v2 Phase 2 / §7.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from control_plane.agents.agent_kenny.nodes.citations import (
    extract_citations,
    verify_citations,
)
from control_plane.agents.agent_kenny.types import AgentState

_TENANT = uuid.UUID("00000000-0000-7000-8000-000000000001")
_ENG = uuid.UUID("00000000-0000-7000-8000-000000000002")
_OTHER_ENG = uuid.UUID("00000000-0000-7000-8000-000000000099")
_ACTOR = uuid.UUID("00000000-0000-7000-8000-000000000003")
_EVENT_ID_GOOD = uuid.UUID("11111111-1111-4111-8111-111111111111")
_EVENT_ID_LEAK = uuid.UUID("22222222-2222-4222-8222-222222222222")
_EVENT_ID_MISSING = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _state(text: str) -> AgentState:
    s = AgentState(
        tenant_id=_TENANT,
        engagement_id=_ENG,
        actor_user_id=_ACTOR,
        user_message="hi",
        started_at=datetime(2026, 5, 23, tzinfo=UTC),
    )
    s.accumulated_text = text
    return s


class _StubResult:
    def __init__(self, value: Any) -> None:
        self._v = value

    def scalar_one_or_none(self) -> Any:
        return self._v


class _StubSession:
    """Tiny async-session stub that routes select() statements through a hook."""

    def __init__(self, lookup: dict[tuple[str, uuid.UUID, bool], Any]) -> None:
        # key: (table_name, id, scoped) -> ORM-like obj or None
        self._lookup = lookup

    async def execute(self, stmt: Any) -> _StubResult:
        # The verifier issues two flavors of select(model).where(...) per kind:
        # (a) tenant + engagement scoped — first call per citation
        # (b) bare id lookup (cross-engagement leak check) — second call
        # Heuristic: peek at the compiled where-clause column refs.
        table = _table_for_stmt(stmt)
        whereclause_text = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Determine which UUID is being looked up. The SQLAlchemy literal
        # binder strips hyphens from UUID values, so we compare against
        # ``hex`` not the canonical str form.
        target_id: uuid.UUID | None = None
        for known_id in (_EVENT_ID_GOOD, _EVENT_ID_LEAK, _EVENT_ID_MISSING):
            if known_id.hex in whereclause_text or str(known_id) in whereclause_text:
                target_id = known_id
                break
        if target_id is None:
            return _StubResult(None)
        where_only = whereclause_text.split("WHERE", 1)[-1] if "WHERE" in whereclause_text else ""
        scoped = "engagement_id" in where_only
        return _StubResult(self._lookup.get((table, target_id, scoped)))


def _table_for_stmt(stmt: Any) -> str:
    # The compiled FROM clause carries the table name.
    text = str(stmt)
    if "ledger_events" in text:
        return "ledger_events"
    if "matrix_nodes" in text:
        return "matrix_nodes"
    if "matrix_insights" in text:
        return "matrix_insights"
    if "oracle_chat_turns" in text:
        return "oracle_chat_turns"
    return "unknown"


class _DummyRow:
    def __init__(self) -> None:
        self.id = uuid.uuid4()


@pytest.mark.asyncio
async def test_extract_citations_is_pure_parse() -> None:
    s = _state("Hi [event:11111111-1111-4111-8111-111111111111] there.")
    out = await extract_citations(s)
    assert out is s
    assert s.messages[-1]["_meta_citations"] == [("event", "11111111-1111-4111-8111-111111111111")]


@pytest.mark.asyncio
async def test_verify_citations_marks_verified_when_in_scope() -> None:
    lookup = {("ledger_events", _EVENT_ID_GOOD, True): _DummyRow()}
    session = _StubSession(lookup)
    s = _state(f"Look at [event:{_EVENT_ID_GOOD}].")
    await verify_citations(session, s)
    report = s.citation_report
    assert report is not None
    assert len(report.verified) == 1
    assert report.verified[0].outcome == "verified"


@pytest.mark.asyncio
async def test_verify_citations_marks_cross_engagement_leak() -> None:
    lookup = {
        ("ledger_events", _EVENT_ID_LEAK, True): None,
        ("ledger_events", _EVENT_ID_LEAK, False): _DummyRow(),
    }
    session = _StubSession(lookup)
    s = _state(f"BAD [event:{_EVENT_ID_LEAK}].")
    await verify_citations(session, s)
    report = s.citation_report
    assert report is not None
    assert len(report.cross_engagement) == 1
    assert report.cross_engagement[0].outcome == "cross_engagement_leak"


@pytest.mark.asyncio
async def test_verify_citations_marks_not_found_when_absent_everywhere() -> None:
    session = _StubSession({})
    s = _state(f"hallucinated [event:{_EVENT_ID_MISSING}].")
    await verify_citations(session, s)
    report = s.citation_report
    assert report is not None
    assert len(report.not_found) == 1
    assert report.not_found[0].outcome == "not_found"


@pytest.mark.asyncio
async def test_verify_citations_marks_external_without_db_lookup() -> None:
    session = _StubSession({})
    s = _state("In Slack we said [slack:msg-abc-123] and [linear:LIN-42].")
    await verify_citations(session, s)
    report = s.citation_report
    assert report is not None
    assert len(report.external) == 2
    assert {c.kind for c in report.external} == {"slack", "linear"}


@pytest.mark.asyncio
async def test_verify_citations_rejects_malformed_uuid() -> None:
    session = _StubSession({})
    s = _state("Bad [event:not-a-uuid] format.")
    await verify_citations(session, s)
    report = s.citation_report
    assert report is not None
    assert len(report.not_found) == 1
