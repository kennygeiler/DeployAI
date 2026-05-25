"""Unit tests for the ``emit_ledger_event`` helper (Phase F1.b).

Validation, secret-scrubbing, and session.add/flush wiring are exercised
against an AsyncMock session — no DB needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.ledger import ALLOWED_SOURCE_KINDS, emit_ledger_event


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
        "actor_id": str(uuid.uuid4()),
        "source_kind": "matrix_node_created",
        "source_ref": uuid.uuid4(),
        "summary": "node created: Alice",
        "detail": {"node_type": "stakeholder"},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_writes_row_and_flushes() -> None:
    s = _session()
    await emit_ledger_event(s, **_kwargs())
    s.add.assert_called_once()
    s.flush.assert_awaited()


@pytest.mark.asyncio
async def test_rejects_unknown_source_kind() -> None:
    s = _session()
    with pytest.raises(ValueError, match="invalid source_kind"):
        await emit_ledger_event(s, **_kwargs(source_kind="not_a_real_kind"))
    s.add.assert_not_called()
    s.flush.assert_not_awaited()


@pytest.mark.parametrize("kind", sorted(ALLOWED_SOURCE_KINDS))
@pytest.mark.asyncio
async def test_accepts_every_enum_value(kind: str) -> None:
    s = _session()
    await emit_ledger_event(s, **_kwargs(source_kind=kind))
    s.add.assert_called_once()


@pytest.mark.asyncio
async def test_rejects_empty_summary() -> None:
    s = _session()
    with pytest.raises(ValueError, match="summary"):
        await emit_ledger_event(s, **_kwargs(summary=""))
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_oversized_summary() -> None:
    s = _session()
    with pytest.raises(ValueError, match="summary"):
        await emit_ledger_event(s, **_kwargs(summary="x" * 501))
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_non_dict_detail() -> None:
    s = _session()
    with pytest.raises(ValueError, match="detail"):
        await emit_ledger_event(s, **_kwargs(detail="not-a-dict"))  # type: ignore[arg-type]
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_empty_actor_kind() -> None:
    s = _session()
    with pytest.raises(ValueError, match="actor_kind"):
        await emit_ledger_event(s, **_kwargs(actor_kind=""))
    s.add.assert_not_called()


@pytest.mark.asyncio
async def test_strips_secret_keys_from_detail() -> None:
    s = _session()
    detail = {
        "api_key": "sk-leaked",
        "signing_secret": "shh",
        "webhook_url": "https://hooks.example",
        "client_secret": "x",
        "password": "p",
        "bearer_token": "b",
        "safe": "ok",
        "nested": {
            "refresh_token": "leak",
            "kept": "yes",
        },
        "items": [{"access_token": "leak", "label": "n1"}, {"label": "n2"}],
    }
    await emit_ledger_event(s, **_kwargs(detail=detail))
    s.add.assert_called_once()
    row = s.add.call_args_list[0].args[0]
    sanitised = row.detail
    for needle in ("api_key", "signing_secret", "webhook_url", "client_secret", "password", "bearer_token"):
        assert needle not in sanitised
    assert sanitised["safe"] == "ok"
    assert sanitised["nested"] == {"kept": "yes"}
    assert sanitised["items"] == [{"label": "n1"}, {"label": "n2"}]


@pytest.mark.asyncio
async def test_emits_cause_and_affect_edges() -> None:
    s = _session()
    parent = uuid.uuid4()
    node = uuid.uuid4()
    await emit_ledger_event(
        s,
        **_kwargs(),
        caused_by=[parent],
        affects=[("matrix_node", node)],
    )
    # main row + cause row + affect row
    assert s.add.call_count == 3


@pytest.mark.asyncio
async def test_rejects_unknown_affect_kind() -> None:
    s = _session()
    with pytest.raises(ValueError, match="affect entity_kind"):
        await emit_ledger_event(s, **_kwargs(), affects=[("garbage", uuid.uuid4())])


@pytest.mark.asyncio
async def test_does_not_commit_caller_owns_transaction() -> None:
    s = _session()
    await emit_ledger_event(s, **_kwargs())
    s.commit.assert_not_awaited()
