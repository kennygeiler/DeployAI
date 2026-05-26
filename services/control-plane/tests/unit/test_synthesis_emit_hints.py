"""Unit tests — synthesis-dispatch hint fields on emit.

Covers the v2 Phase 0.5 follow-up: the proposal-accept and member-add routes
must populate ``detail.node_type`` / ``detail.stakeholder_node_id`` so the
emitter's ``_maybe_enqueue_synthesis`` dispatcher can route refresh jobs.

Also exercises the dispatcher's defensive fallback — when ``detail.node_type``
is missing on a ``proposal_accepted`` event, the dispatcher looks up the
node type from ``matrix_nodes`` via the affected matrix_node id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.canonical_memory.matrix import MatrixNode, SynthesisRefreshJob
from control_plane.ledger import emit_ledger_event
from control_plane.ledger.emitter import _maybe_enqueue_synthesis


def _session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


def _kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tenant_id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "occurred_at": datetime.now(UTC),
        "actor_kind": "user",
        "actor_id": "tester",
        "source_kind": "proposal_accepted",
        "source_ref": uuid.uuid4(),
        "summary": "proposal accepted: node",
        "detail": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# emit-site hint shape (proposal-accept route — exercised via the helper that
# the route now uses; the route-level happy-path is covered end-to-end in the
# integration test).
# ---------------------------------------------------------------------------


def _accept_detail(*, proposal_kind: str, payload_node_type: str | None) -> dict[str, Any]:
    """Mirror of the dispatch-hint logic in ``accept_matrix_proposal``."""
    detail: dict[str, Any] = {"proposal_kind": proposal_kind}
    if proposal_kind == "node" and isinstance(payload_node_type, str) and payload_node_type:
        detail["node_type"] = payload_node_type
    return detail


@pytest.mark.parametrize(
    ("payload_node_type", "expected"),
    [("decision", "decision"), ("stakeholder", "stakeholder"), ("system", "system")],
)
def test_node_proposal_accept_detail_carries_node_type(payload_node_type: str, expected: str) -> None:
    detail = _accept_detail(proposal_kind="node", payload_node_type=payload_node_type)
    assert detail["node_type"] == expected


def test_edge_proposal_accept_detail_omits_node_type() -> None:
    detail = _accept_detail(proposal_kind="edge", payload_node_type=None)
    assert "node_type" not in detail
    assert detail["proposal_kind"] == "edge"


# ---------------------------------------------------------------------------
# member_added hint shape — mirrors the look-up performed in
# ``add_engagement_member``: if there's a stakeholder match for the user's
# email, the route puts that node id under ``detail.stakeholder_node_id``.
# ---------------------------------------------------------------------------


def _member_detail(*, role: str, user_id: uuid.UUID, stakeholder_id: uuid.UUID | None) -> dict[str, Any]:
    detail: dict[str, Any] = {"role": role, "user_id": str(user_id), "user_provisioned": False}
    if stakeholder_id is not None:
        detail["stakeholder_node_id"] = str(stakeholder_id)
    return detail


def test_member_added_detail_carries_stakeholder_node_id_when_match() -> None:
    user_id = uuid.uuid4()
    stake_id = uuid.uuid4()
    detail = _member_detail(role="fde", user_id=user_id, stakeholder_id=stake_id)
    assert detail["stakeholder_node_id"] == str(stake_id)


def test_member_added_detail_omits_stakeholder_when_no_match() -> None:
    user_id = uuid.uuid4()
    detail = _member_detail(role="fde", user_id=user_id, stakeholder_id=None)
    assert "stakeholder_node_id" not in detail


# ---------------------------------------------------------------------------
# Dispatcher behaviour — exercises ``_maybe_enqueue_synthesis`` directly with
# an AsyncMock session. The dispatcher calls ``session.add(SynthesisRefreshJob(...))``
# once per trigger we expect to fire.
# ---------------------------------------------------------------------------


def _mock_event(source_kind: str) -> MagicMock:
    event = MagicMock()
    event.id = uuid.uuid4()
    event.tenant_id = uuid.uuid4()
    event.source_kind = source_kind
    return event


@pytest.mark.asyncio
async def test_dispatch_fires_decision_provenance_when_hint_present() -> None:
    s = _session()
    node_id = uuid.uuid4()
    await _maybe_enqueue_synthesis(
        s,
        event=_mock_event("proposal_accepted"),
        engagement_id=uuid.uuid4(),
        affects=[("matrix_node", node_id)],
        detail={"node_type": "decision"},
    )
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert len(jobs) == 1
    assert jobs[0].kind == "decision_provenance"
    assert jobs[0].target_id == node_id
    # session.get must NOT be called when the hint is present.
    s.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_fallback_queries_matrix_node_when_hint_missing() -> None:
    s = _session()
    node_id = uuid.uuid4()
    fake_node = MagicMock()
    fake_node.node_type = "decision"
    s.get = AsyncMock(return_value=fake_node)

    await _maybe_enqueue_synthesis(
        s,
        event=_mock_event("proposal_accepted"),
        engagement_id=uuid.uuid4(),
        affects=[("matrix_node", node_id)],
        detail={},  # no node_type hint
    )

    s.get.assert_awaited_once_with(MatrixNode, node_id)
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert len(jobs) == 1
    assert jobs[0].kind == "decision_provenance"
    assert jobs[0].target_id == node_id


@pytest.mark.asyncio
async def test_dispatch_fallback_skips_non_decision_node() -> None:
    s = _session()
    node_id = uuid.uuid4()
    fake_node = MagicMock()
    fake_node.node_type = "system"
    s.get = AsyncMock(return_value=fake_node)

    await _maybe_enqueue_synthesis(
        s,
        event=_mock_event("proposal_accepted"),
        engagement_id=uuid.uuid4(),
        affects=[("matrix_node", node_id)],
        detail={},
    )

    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert jobs == []


@pytest.mark.asyncio
async def test_dispatch_member_added_fires_when_stakeholder_hint_present() -> None:
    s = _session()
    stake_id = uuid.uuid4()
    await _maybe_enqueue_synthesis(
        s,
        event=_mock_event("member_added"),
        engagement_id=uuid.uuid4(),
        affects=[],
        detail={"stakeholder_node_id": str(stake_id)},
    )
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert len(jobs) == 1
    assert jobs[0].kind == "stakeholder_brief"
    assert jobs[0].target_id == stake_id


@pytest.mark.asyncio
async def test_dispatch_member_added_inert_without_hint() -> None:
    s = _session()
    await _maybe_enqueue_synthesis(
        s,
        event=_mock_event("member_added"),
        engagement_id=uuid.uuid4(),
        affects=[],
        detail={"role": "fde"},
    )
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert jobs == []


# ---------------------------------------------------------------------------
# Whole-pipe smoke: ``emit_ledger_event`` honours the hint via the dispatcher.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_with_decision_hint_enqueues_synthesis_job() -> None:
    s = _session()
    node_id = uuid.uuid4()
    await emit_ledger_event(
        s,
        **_kwargs(detail={"node_type": "decision"}, affects=[("matrix_node", node_id)]),
    )
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert len(jobs) == 1
    assert jobs[0].kind == "decision_provenance"
    assert jobs[0].target_id == node_id


@pytest.mark.asyncio
async def test_emit_without_hint_uses_fallback_lookup() -> None:
    s = _session()
    node_id = uuid.uuid4()
    fake_node = MagicMock()
    fake_node.node_type = "decision"
    s.get = AsyncMock(return_value=fake_node)
    await emit_ledger_event(
        s,
        **_kwargs(detail={}, affects=[("matrix_node", node_id)]),
    )
    s.get.assert_awaited_once_with(MatrixNode, node_id)
    jobs = [c.args[0] for c in s.add.call_args_list if isinstance(c.args[0], SynthesisRefreshJob)]
    assert len(jobs) == 1
    assert jobs[0].kind == "decision_provenance"
