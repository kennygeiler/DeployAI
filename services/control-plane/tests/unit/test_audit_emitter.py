"""Unit tests for the ``emit_audit_event`` helper.

Validation and session.add/flush wiring are exercised against an
AsyncMock session — no DB needed. Phase F1.b dual-emit semantics
(audit row + ledger row in one transaction) live in
``tests/integration/test_ledger_dual_emit.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.audit import emit_audit_event
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.strategist_personal import StrategistActivityEvent


def _session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


@pytest.mark.asyncio
async def test_writes_row_to_session() -> None:
    s = _session()
    tid, aid = uuid.uuid4(), uuid.uuid4()
    row = await emit_audit_event(
        s,
        tenant_id=tid,
        actor_id=aid,
        category="break_glass.requested",
        summary="bg requested",
        detail={"session_id": "abc"},
    )
    assert isinstance(row, StrategistActivityEvent)
    assert row.tenant_id == tid
    assert row.actor_id == aid
    assert row.category == "break_glass.requested"
    assert row.summary == "bg requested"
    assert row.detail == {"session_id": "abc"}
    assert row.ref_id is None
    added = [c.args[0] for c in s.add.call_args_list]
    assert any(isinstance(a, StrategistActivityEvent) for a in added)
    assert any(isinstance(a, LedgerEvent) for a in added)
    s.flush.assert_awaited()


@pytest.mark.asyncio
async def test_accepts_ref_id() -> None:
    s = _session()
    ref = uuid.uuid4()
    row = await emit_audit_event(
        s,
        tenant_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        category="override_added",
        summary="ok",
        detail={},
        ref_id=ref,
    )
    assert row.ref_id == ref


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "Bad.Caps",
        "break glass.requested",
        "1starts_with_digit",
        ".starts_with_dot",
        "a" * 81,
        "has-dash",
    ],
)
@pytest.mark.asyncio
async def test_rejects_invalid_category(bad: str) -> None:
    s = _session()
    with pytest.raises(ValueError, match="category"):
        await emit_audit_event(
            s,
            tenant_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            category=bad,
            summary="x",
            detail={},
        )
    s.add.assert_not_called()
    s.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_empty_summary() -> None:
    s = _session()
    with pytest.raises(ValueError, match="summary"):
        await emit_audit_event(
            s,
            tenant_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            category="ok",
            summary="",
            detail={},
        )
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_oversized_summary() -> None:
    s = _session()
    with pytest.raises(ValueError, match="summary"):
        await emit_audit_event(
            s,
            tenant_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            category="ok",
            summary="x" * 501,
            detail={},
        )
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_non_dict_detail() -> None:
    s = _session()
    with pytest.raises(ValueError, match="detail"):
        await emit_audit_event(
            s,
            tenant_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            category="ok",
            summary="x",
            detail="not a dict",  # type: ignore[arg-type]
        )
    s.add.assert_not_called()
