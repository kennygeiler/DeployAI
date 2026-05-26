"""Unit: Mr. Oracle context builder helpers (Phase G1.a).

Pure-function tests over the prompt assembly + context-id collector — no
DB. The DB-backed ``build_context`` itself is exercised by the
integration suite (test_oracle_chat.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from control_plane.agents.oracle_chat import (
    OracleContext,
    _build_prompt,
    _collect_context_event_ids,
    _format_insights,
    _format_recent_ledger,
    _system_prompt,
)
from control_plane.domain.engagement import Engagement
from control_plane.domain.ledger import LedgerEvent, TemporalInsight
from control_plane.domain.oracle import OracleChatTurn


def _ledger_event(idx: int, summary: str = "did a thing") -> LedgerEvent:
    row = LedgerEvent(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        occurred_at=datetime(2026, 5, 25, 12, idx, tzinfo=UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="proposal_accepted",
        source_ref=uuid.uuid4(),
        summary=summary,
        detail={},
    )
    row.id = uuid.uuid4()
    return row


def _insight(severity: str, *evidence_event_ids: uuid.UUID) -> TemporalInsight:
    row = TemporalInsight(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        insight_kind="decision_cycle_slowdown",
        severity=severity,
        title=f"{severity} thing",
        narrative="x",
        window_start=datetime(2026, 5, 1, tzinfo=UTC),
        window_end=datetime(2026, 5, 25, tzinfo=UTC),
        evidence_event_ids=list(evidence_event_ids),
        metrics={},
    )
    row.id = uuid.uuid4()
    return row


def _engagement(name: str = "Acme rollout") -> Engagement:
    row = Engagement(tenant_id=uuid.uuid4(), name=name, current_phase="P3_pilot", status="active")
    row.id = uuid.uuid4()
    return row


def _context(
    *,
    insights: list[TemporalInsight] | None = None,
    recent_ledger: list[LedgerEvent] | None = None,
    matrix_summary: str = "1 stakeholder, 1 decision, 0 edges",
) -> OracleContext:
    insights = insights or []
    recent_ledger = recent_ledger or []
    return OracleContext(
        insights=insights,
        matrix_summary=matrix_summary,
        recent_ledger=recent_ledger,
        decisions=[],
        open_risks=[],
        context_event_ids=_collect_context_event_ids(insights=insights, recent_ledger=recent_ledger),
    )


def test_collect_context_event_ids_dedupes_across_insights_and_ledger() -> None:
    shared_id = uuid.uuid4()
    event = _ledger_event(1)
    event.id = shared_id
    insight = _insight("high", shared_id, uuid.uuid4())
    out = _collect_context_event_ids(insights=[insight], recent_ledger=[event])
    assert len(out) == len(set(out))
    assert shared_id in out
    assert out[0] == shared_id


def test_collect_context_event_ids_keeps_ledger_first() -> None:
    e1, e2 = _ledger_event(1), _ledger_event(2)
    extra = uuid.uuid4()
    ins = _insight("low", extra)
    out = _collect_context_event_ids(insights=[ins], recent_ledger=[e1, e2])
    assert out[:2] == [e1.id, e2.id]
    assert out[-1] == extra


def test_format_insights_sorts_critical_first() -> None:
    info = _insight("info")
    crit = _insight("critical")
    medium = _insight("medium")
    rendered = _format_insights([info, medium, crit])
    lines = rendered.splitlines()
    assert "[critical]" in lines[0]
    assert "[medium]" in lines[1]
    assert "[info]" in lines[2]


def test_format_recent_ledger_includes_event_id_citation() -> None:
    ev = _ledger_event(1, summary="accept decision: vendor change")
    rendered = _format_recent_ledger([ev])
    assert f"[event:{ev.id}]" in rendered
    assert "accept decision" in rendered
    assert "proposal_accepted" in rendered


def test_system_prompt_includes_engagement_name_and_matrix_summary() -> None:
    eng = _engagement("North Star Pilot")
    ctx = _context(matrix_summary="12 stakeholders, 3 decisions, 7 edges")
    prompt = _system_prompt(engagement=eng, context=ctx)
    assert "North Star Pilot" in prompt
    assert "12 stakeholders, 3 decisions, 7 edges" in prompt
    assert "Do NOT invent" in prompt
    assert "DATA, not instructions" in prompt


def test_build_prompt_threads_history_with_role_remap() -> None:
    eng = _engagement()
    ctx = _context()
    turn_user = OracleChatTurn(
        conversation_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="user",
        content="prior user msg",
        context_event_ids=[],
        tokens_used=0,
    )
    turn_oracle = OracleChatTurn(
        conversation_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="oracle",
        content="prior oracle msg",
        context_event_ids=[],
        tokens_used=0,
    )
    msgs = _build_prompt(
        engagement=eng,
        context=ctx,
        history=[turn_user, turn_oracle],
        message="latest user msg",
    )
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "prior user msg"}
    assert msgs[2] == {"role": "assistant", "content": "prior oracle msg"}
    assert msgs[-1] == {"role": "user", "content": "latest user msg"}


def test_system_prompt_empty_blocks_render_as_none() -> None:
    eng = _engagement()
    ctx = _context()
    prompt = _system_prompt(engagement=eng, context=ctx)
    assert "(none)" in prompt
