"""Unit tests for the Phase 1 tool layer common types + registry."""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from control_plane.agents.tools import (
    TOOL_REGISTRY,
    Citation,
    ToolError,
    ToolResult,
    ToolSpec,
    _ensure_uuid,
    _require_scope,
    register_tool,
)


def test_citation_is_immutable_dataclass() -> None:
    cid = uuid.uuid4()
    c = Citation(kind="event", id=cid)
    assert c.kind == "event"
    assert c.id == cid
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.kind = "node"  # type: ignore[misc]


def test_tool_result_defaults() -> None:
    r = ToolResult(name="dummy", rows=[])
    assert r.name == "dummy"
    assert r.rows == []
    assert r.citations == []
    assert r.truncated is False
    assert r.next_cursor is None
    assert r.duration_ms == 0.0
    assert r.detail is None


def test_tool_result_populated() -> None:
    cid = uuid.uuid4()
    r = ToolResult(
        name="x",
        rows=[{"a": 1}],
        citations=[Citation(kind="node", id=cid)],
        truncated=True,
        next_cursor="abc",
        duration_ms=1.5,
        detail="ok",
    )
    assert r.truncated is True
    assert r.next_cursor == "abc"
    assert r.citations[0].id == cid


def test_tool_error_is_value_error() -> None:
    assert issubclass(ToolError, ValueError)


def test_registry_contains_all_twelve_tools() -> None:
    expected = {
        "query_ledger",
        "walk_chain",
        "get_matrix_node",
        "get_matrix_neighbors",
        "get_matrix_subgraph",
        "read_synthesis",
        "get_decision_history",
        "get_open_risks",
        "get_engagement_summary",
        "keyword_search",
        "vector_search",
        "propose_action",
    }
    assert expected.issubset(TOOL_REGISTRY.keys())
    assert len(expected) == 12


def test_each_tool_spec_has_json_schema_shape() -> None:
    for name, spec in TOOL_REGISTRY.items():
        assert spec.name == name
        assert spec.description
        assert isinstance(spec.input_schema, dict)
        assert spec.input_schema.get("type") == "object"
        assert "properties" in spec.input_schema


def test_register_tool_rejects_duplicate() -> None:
    spec = ToolSpec(
        name="query_ledger",
        description="dup",
        input_schema={"type": "object", "properties": {}},
    )
    with pytest.raises(ValueError):
        register_tool(spec)


def test_ensure_uuid_accepts_uuid_and_string() -> None:
    u = uuid.uuid4()
    assert _ensure_uuid(u, "x") == u
    assert _ensure_uuid(str(u), "x") == u


def test_ensure_uuid_rejects_garbage() -> None:
    with pytest.raises(ToolError):
        _ensure_uuid("not-a-uuid", "x")
    with pytest.raises(ToolError):
        _ensure_uuid(42, "x")


def test_require_scope_rejects_missing() -> None:
    with pytest.raises(ToolError, match="tenant_id"):
        _require_scope(tenant_id=None, engagement_id=uuid.uuid4())
    with pytest.raises(ToolError, match="engagement_id"):
        _require_scope(tenant_id=uuid.uuid4(), engagement_id=None)


def test_require_scope_returns_tuple_of_uuids() -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    out_tid, out_eid = _require_scope(tenant_id=str(tid), engagement_id=str(eid))
    assert out_tid == tid
    assert out_eid == eid


def test_audit_hash_is_deterministic() -> None:
    from control_plane.agents.tools.audit import hash_tool_input

    h1 = hash_tool_input({"a": 1, "b": [1, 2]})
    h2 = hash_tool_input({"b": [1, 2], "a": 1})
    assert h1 == h2
    assert len(h1) == 32
