"""Unit tests for ``vector_search`` (Phase 5.5 Wave C, scope-v2 §10.3).

These tests intentionally don't touch Postgres — every database hit is
served by an in-memory stub session that records what SQL the tool
emitted. The goal is to lock in three properties that must hold
regardless of which backend runs underneath:

1. The query vector is bound as a parameter, never spliced into SQL.
2. ``kind=None`` merges all four source-table queries and ranks by
   similarity (highest first), tie-broken by id.
3. Audit emission carries the right metadata + tenant + engagement
   scoping is respected even when the caller omits engagement_id.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import pytest

from control_plane.agents.tools import ToolError
from control_plane.agents.tools.search import (
    VectorKind,
    VectorSearchHit,
    vector_search,
)

# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _StubEmbedder:
    """Records the query string + returns a deterministic vector."""

    def __init__(self, *, vec: list[float] | None = None) -> None:
        self._vec = vec if vec is not None else [0.1] * 1024
        self.calls: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [list(self._vec) for _ in texts]


class _RaisingEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("voyage down")


class _RowMapping(dict):  # type: ignore[type-arg]
    """A row that quacks like a SQLAlchemy ``RowMapping``."""

    def __getitem__(self, key: str) -> Any:  # type: ignore[override]
        return super().__getitem__(key)


class _StubResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [_RowMapping(r) for r in rows]

    def mappings(self) -> _StubResult:
        return self

    def all(self) -> list[_RowMapping]:
        return list(self._rows)


class _StubSession:
    """In-memory ``AsyncSession`` that intercepts every ``execute()`` call."""

    def __init__(
        self,
        per_kind_rows: Mapping[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        # Keyed by a fragment of the SQL text so each per-kind query
        # gets matched to its synthetic result set.
        self._per_kind_rows = per_kind_rows or {}
        self.executions: list[tuple[str, dict[str, Any]]] = []
        self.committed = False
        self.rolled_back = False
        # Capture ledger emits without hitting Postgres.
        self.ledger_emits: list[dict[str, Any]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _StubResult:
        sql = str(stmt)
        self.executions.append((sql, dict(params or {})))
        for fragment, rows in self._per_kind_rows.items():
            if fragment in sql:
                return _StubResult(rows)
        # Default: pretend the table has zero hits (e.g. unembedded).
        return _StubResult([])

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace ``emit_tool_invocation`` with a list-recorder.

    The real helper opens a transaction + writes a ledger row, which
    would require a live DB. We intercept it at the import site
    (``control_plane.agents.tools.search``) so the tool's audit
    behaviour is asserted without DB.
    """
    captured: list[dict[str, Any]] = []

    async def _record(session: Any, **kwargs: Any) -> uuid.UUID:
        # session passes through unused; record kwargs.
        del session
        captured.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(
        "control_plane.agents.tools.search.emit_tool_invocation",
        _record,
    )
    return captured


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_missing_tenant() -> None:
    with pytest.raises(ToolError, match="tenant_id"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=None,  # type: ignore[arg-type]
            engagement_id=None,
            query="hello",
            embedder=_StubEmbedder(),
        )


@pytest.mark.asyncio
async def test_rejects_blank_query() -> None:
    with pytest.raises(ToolError, match="non-empty"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            engagement_id=None,
            query="   ",
            embedder=_StubEmbedder(),
        )


@pytest.mark.asyncio
async def test_rejects_unknown_kind() -> None:
    with pytest.raises(ToolError, match="kind"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            engagement_id=None,
            query="hello",
            kind="bogus",  # type: ignore[arg-type]
            embedder=_StubEmbedder(),
        )


@pytest.mark.asyncio
async def test_rejects_bad_limit() -> None:
    with pytest.raises(ToolError, match="limit"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            engagement_id=None,
            query="hello",
            limit=0,
            embedder=_StubEmbedder(),
        )


@pytest.mark.asyncio
async def test_embedder_failure_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="embedder failed"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            engagement_id=None,
            query="hello",
            embedder=_RaisingEmbedder(),
        )


@pytest.mark.asyncio
async def test_missing_embedder_is_rejected() -> None:
    with pytest.raises(ToolError, match="embedder"):
        await vector_search(
            _StubSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            engagement_id=None,
            query="hello",
            embedder=None,  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------
# Parameterized SQL contract — the vector goes in as a *parameter*, never
# interpolated. This is the scope-v2 §10.3 vector-injection mitigation.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_vector_is_bound_not_interpolated() -> None:
    session = _StubSession()
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=tid,
        engagement_id=eid,
        query="kerberos delegation",
        kind="ledger",
        embedder=_StubEmbedder(vec=[0.42] * 1024),
    )
    # One execute call (kind="ledger") + zero ledger inserts because
    # the audit helper is stubbed.
    assert len(session.executions) == 1
    sql, params = session.executions[0]
    # The vector literal must NOT appear inside the SQL string. If a
    # future refactor accidentally f-strings the vector in, this fails.
    assert "0.42" not in sql, "query vector leaked into SQL — must be bound"
    assert "[" not in sql.split("FROM")[0], "vector literal in SELECT clause"
    # The placeholder is present and the param dict carries the literal.
    assert ":qvec" in sql
    assert params["qvec"].startswith("[")
    assert "0.42" in params["qvec"]
    # Tenant + engagement scoping bound, not interpolated.
    assert params["tenant_id"] == tid
    assert params["engagement_id"] == eid


@pytest.mark.asyncio
async def test_engagement_scope_dropped_when_caller_omits_it() -> None:
    session = _StubSession()
    tid = uuid.uuid4()
    await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=tid,
        engagement_id=None,
        query="ad migration",
        kind="conversation",
        embedder=_StubEmbedder(),
    )
    sql, params = session.executions[0]
    # The cheap-plan no-engagement variant has no JOIN.
    assert "JOIN oracle_conversations" not in sql
    assert "engagement_id" not in params


@pytest.mark.asyncio
async def test_conversation_scope_joins_through_oracle_conversations() -> None:
    session = _StubSession()
    await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        query="ad migration",
        kind="conversation",
        embedder=_StubEmbedder(),
    )
    sql, _ = session.executions[0]
    assert "JOIN oracle_conversations" in sql
    assert "c.engagement_id = :engagement_id" in sql


# --------------------------------------------------------------------------
# Result shape + score ordering
# --------------------------------------------------------------------------


def _ledger_row(*, ident: uuid.UUID, summary: str, distance: float) -> dict[str, Any]:
    from datetime import UTC, datetime

    return {
        "id": ident,
        "summary": summary,
        "occurred_at": datetime(2026, 5, 1, tzinfo=UTC),
        "distance": distance,
    }


@pytest.mark.asyncio
async def test_single_kind_returns_ranked_hits() -> None:
    a = uuid.uuid4()
    b = uuid.uuid4()
    c = uuid.uuid4()
    session = _StubSession(
        per_kind_rows={
            "FROM ledger_events": [
                _ledger_row(ident=a, summary="closest", distance=0.10),
                _ledger_row(ident=b, summary="middle", distance=0.30),
                _ledger_row(ident=c, summary="furthest", distance=0.70),
            ]
        }
    )
    result = await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        query="closest match please",
        kind="ledger",
        limit=3,
        embedder=_StubEmbedder(),
    )
    assert [r["id"] for r in result.rows] == [str(a), str(b), str(c)]
    # score = 1 - distance, descending
    assert [r["score"] for r in result.rows] == [
        pytest.approx(0.90),
        pytest.approx(0.70),
        pytest.approx(0.30),
    ]
    # Every hit becomes a Citation with the event kind.
    assert {c.kind for c in result.citations} == {"event"}
    # detail string carries the agent-readable summary.
    assert "kind=ledger" in (result.detail or "")
    assert "hits=3" in (result.detail or "")


@pytest.mark.asyncio
async def test_merge_path_combines_all_four_kinds_and_ranks_globally() -> None:
    from datetime import UTC, datetime

    occ = datetime(2026, 5, 1, tzinfo=UTC)
    led_a = uuid.uuid4()
    led_b = uuid.uuid4()
    nod = uuid.uuid4()
    ins = uuid.uuid4()
    conv = uuid.uuid4()
    session = _StubSession(
        per_kind_rows={
            "FROM ledger_events": [
                {"id": led_a, "summary": "ledger-best", "occurred_at": occ, "distance": 0.05},
                {"id": led_b, "summary": "ledger-poor", "occurred_at": occ, "distance": 0.80},
            ],
            "FROM matrix_nodes": [
                {"id": nod, "summary": "node-mid", "occurred_at": occ, "distance": 0.25},
            ],
            "FROM matrix_insights": [
                {"id": ins, "summary": "insight-mid", "occurred_at": occ, "distance": 0.20},
            ],
            "FROM oracle_chat_turns": [
                {"id": conv, "summary": "conv-mid", "occurred_at": occ, "distance": 0.15},
            ],
        }
    )
    result = await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        query="something fuzzy",
        limit=3,
        embedder=_StubEmbedder(),
    )
    # 5 candidates pooled, top-3 by score (1-distance):
    #   led_a 0.95, conv 0.85, ins 0.80, nod 0.75, led_b 0.20
    assert [r["id"] for r in result.rows] == [str(led_a), str(conv), str(ins)]
    # truncated=True because 5 > limit 3.
    assert result.truncated is True
    # All four per-kind queries were issued.
    fragments = [sql for sql, _ in session.executions]
    assert any("FROM ledger_events" in s for s in fragments)
    assert any("FROM matrix_nodes" in s for s in fragments)
    assert any("FROM matrix_insights" in s for s in fragments)
    assert any("FROM oracle_chat_turns" in s for s in fragments)


@pytest.mark.asyncio
async def test_truncated_flag_only_when_overflow() -> None:
    """The truncated flag must not fire when hit count <= limit."""
    session = _StubSession(
        per_kind_rows={
            "FROM ledger_events": [
                {
                    "id": uuid.uuid4(),
                    "summary": "only-hit",
                    "occurred_at": None,
                    "distance": 0.10,
                }
            ]
        }
    )
    result = await vector_search(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        query="lonely",
        kind="ledger",
        limit=5,
        embedder=_StubEmbedder(),
    )
    assert len(result.rows) == 1
    assert result.truncated is False


def test_hit_pydantic_model_is_frozen_and_typed() -> None:
    from pydantic import ValidationError

    h = VectorSearchHit(
        kind="ledger",
        id=uuid.uuid4(),
        summary="x",
        score=0.5,
        occurred_at=None,
    )
    assert h.kind == "ledger"
    with pytest.raises(ValidationError):
        h.score = 0.9  # type: ignore[misc]


# --------------------------------------------------------------------------
# Audit emission
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_emit_carries_metadata(
    _stub_audit: list[dict[str, Any]],
) -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    await vector_search(
        _StubSession(),  # type: ignore[arg-type]
        tenant_id=tid,
        engagement_id=eid,
        query="why is the AD migration stalled",
        kind="insight",
        limit=4,
        embedder=_StubEmbedder(),
    )
    assert len(_stub_audit) == 1
    call = _stub_audit[0]
    assert call["tool_name"] == "vector_search"
    assert call["tenant_id"] == tid
    assert call["engagement_id"] == eid
    assert call["row_count"] == 0
    # input_hash is the 32-char hex slice from hash_tool_input.
    assert len(call["input_hash"]) == 32


@pytest.mark.asyncio
async def test_audit_skipped_when_emit_audit_false(
    _stub_audit: list[dict[str, Any]],
) -> None:
    await vector_search(
        _StubSession(),  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        query="quiet",
        embedder=_StubEmbedder(),
        emit_audit=False,
    )
    assert _stub_audit == []


# --------------------------------------------------------------------------
# Registry contract — the spec the LLM sees matches the param shape.
# --------------------------------------------------------------------------


def test_registry_input_schema_matches_new_signature() -> None:
    from control_plane.agents.tools import TOOL_REGISTRY

    spec = TOOL_REGISTRY["vector_search"]
    props = spec.input_schema["properties"]
    assert set(props.keys()) == {"query", "kind", "limit"}
    assert spec.input_schema["required"] == ["query"]
    # The enum carries exactly the four kinds the tool implements.
    kinds = set(props["kind"]["enum"])
    assert kinds == {"ledger", "matrix_node", "insight", "conversation"}


def test_vector_kind_literal_covers_all_four() -> None:
    """A typo in one of the literals would silently break the dispatcher."""
    from typing import get_args

    assert set(get_args(VectorKind)) == {"ledger", "matrix_node", "insight", "conversation"}
