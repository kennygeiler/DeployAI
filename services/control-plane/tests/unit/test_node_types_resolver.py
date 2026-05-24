"""Unit tests for ``control_plane.domain.canonical_memory.node_types``."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.canonical_memory.matrix import MATRIX_NODE_TYPES, TenantNodeType
from control_plane.domain.canonical_memory.node_types import (
    BUILTIN_NODE_TYPES,
    list_tenant_node_types,
    resolve_allowed_node_types,
)


def _fake_session_returning(rows: list[TenantNodeType]) -> AsyncMock:
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    session = AsyncMock()
    session.execute.return_value = result
    return session


def test_builtin_node_types_matches_matrix_constant() -> None:
    assert BUILTIN_NODE_TYPES == MATRIX_NODE_TYPES


@pytest.mark.asyncio
async def test_list_returns_session_rows() -> None:
    tid = uuid.uuid4()
    row = TenantNodeType(tenant_id=tid, name="patient_journey", label="Patient journey")
    session = _fake_session_returning([row])
    out = await list_tenant_node_types(session, tid)
    assert out == [row]


@pytest.mark.asyncio
async def test_resolve_with_no_custom_returns_builtins_only() -> None:
    session = _fake_session_returning([])
    out = await resolve_allowed_node_types(session, uuid.uuid4())
    assert out == set(BUILTIN_NODE_TYPES)


@pytest.mark.asyncio
async def test_resolve_unions_builtins_and_custom() -> None:
    tid = uuid.uuid4()
    rows = [
        TenantNodeType(tenant_id=tid, name="patient_journey", label="Patient journey"),
        TenantNodeType(tenant_id=tid, name="feature_flag", label="Feature flag"),
    ]
    session = _fake_session_returning(rows)
    out = await resolve_allowed_node_types(session, tid)
    assert out == set(BUILTIN_NODE_TYPES) | {"patient_journey", "feature_flag"}
