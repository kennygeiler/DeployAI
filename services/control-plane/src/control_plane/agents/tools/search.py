"""Search tools: ``keyword_search`` + ``vector_search`` (Phase 5.5).

``keyword_search`` falls back to a simple ``ILIKE`` over ledger summaries +
matrix-node titles. ``vector_search`` (operational as of Wave C, scope-v2
§10.3) is a pgvector HNSW cosine-similarity recall over the four embedded
source tables:

- ``ledger_events`` (summary)
- ``matrix_nodes`` (title)
- ``matrix_insights`` (title + body)
- ``oracle_chat_turns`` (content)

Per the ethos (§5.2), vector search is the **fuzzy fallback**, not the
hot path: the agent loop's tiered retrieval reaches the curated index +
``keyword_search`` first; ``vector_search`` is what answers "I half-
remember a thread about X" when those miss.

The query vector is ALWAYS bound as a parameter — never interpolated
into the SQL string — so a hostile or malformed embedder return value
cannot become SQL injection. Returns top-N hits merged by similarity
score across all requested ``kinds``.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import bindparam, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.tools import (
    Citation,
    ToolError,
    ToolResult,
    ToolSpec,
    _require_scope,
    register_tool,
)
from control_plane.agents.tools.audit import emit_tool_invocation, hash_tool_input
from control_plane.domain.canonical_memory.matrix import MatrixNode
from control_plane.domain.ledger import LedgerEvent

if TYPE_CHECKING:
    from control_plane.agents.agent_kenny.embeddings.voyage_client import (
        VoyageEmbedder,
    )

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 100
_VECTOR_DEFAULT_LIMIT = 10

# scope-v2 §10.3: four source tables carry an ``embedding vector(1024)``
# column written by Wave B's embedder worker. The literal strings are
# the canonical ``kind`` values the agent loop + audit ledger speak.
VectorKind = Literal["ledger", "matrix_node", "insight", "conversation"]
_VECTOR_KINDS: tuple[VectorKind, ...] = ("ledger", "matrix_node", "insight", "conversation")


KEYWORD_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "kinds": {
            "type": "array",
            "items": {"type": "string", "enum": ["event", "node"]},
            "description": "Which substrates to search; default both.",
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
    "required": ["query"],
}

VECTOR_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Natural-language query to embed + match against curated content.",
        },
        "kind": {
            "type": "string",
            "enum": list(_VECTOR_KINDS),
            "description": (
                "Restrict the search to one source table. Omit to merge results across all four embedded surfaces."
            ),
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": _MAX_LIMIT,
            "description": "Max hits returned (default 10).",
        },
    },
    "required": ["query"],
}


class VectorSearchHit(BaseModel):
    """One row returned by :func:`vector_search`.

    ``score`` is cosine *similarity* in ``[0, 1]`` (computed as
    ``1 - cosine_distance``). Higher = closer. ``occurred_at`` is
    populated for kinds that carry a timestamp (ledger events,
    matrix nodes via ``updated_at``, insights via ``created_at``,
    conversation turns via ``created_at``); otherwise ``None``.
    """

    model_config = ConfigDict(frozen=True)

    kind: VectorKind
    id: uuid.UUID
    summary: str
    score: float
    occurred_at: str | None = None


async def keyword_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    query: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """ILIKE-based recall over ledger summaries + matrix node titles/attributes."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not query or not query.strip():
        raise ToolError("query must be non-empty")
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")

    search_kinds = tuple(kinds) if kinds else ("event", "node")
    like = f"%{query.strip()}%"

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []

    if "event" in search_kinds:
        ev_stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.tenant_id == tid,
                LedgerEvent.engagement_id == eid,
                LedgerEvent.summary.ilike(like),
            )
            .order_by(LedgerEvent.occurred_at.desc())
            .limit(limit)
        )
        for ev in (await session.execute(ev_stmt)).scalars().all():
            rows.append(
                {
                    "kind": "event",
                    "id": str(ev.id),
                    "summary": ev.summary,
                    "source_kind": ev.source_kind,
                    "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                }
            )
            citations.append(Citation(kind="event", id=ev.id))

    if "node" in search_kinds:
        nd_stmt = (
            select(MatrixNode)
            .where(
                MatrixNode.tenant_id == tid,
                MatrixNode.engagement_id == eid,
                MatrixNode.title.ilike(like),
            )
            .order_by(MatrixNode.updated_at.desc())
            .limit(limit)
        )
        for n in (await session.execute(nd_stmt)).scalars().all():
            rows.append(
                {
                    "kind": "node",
                    "id": str(n.id),
                    "title": n.title,
                    "node_type": n.node_type,
                    "status": n.status,
                }
            )
            citations.append(Citation(kind="node", id=n.id))

    truncated = len(rows) >= limit
    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="keyword_search",
            input_hash=hash_tool_input({"query": query, "kinds": list(search_kinds), "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )
    return ToolResult(
        name="keyword_search",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


# --------------------------------------------------------------------------
# vector_search (Phase 5.5 Wave C)
# --------------------------------------------------------------------------


# Per-kind SQL templates. Each template:
#   - SELECTs id, a ``summary`` text expression, an ``occurred_at`` timestamp
#     (NULL where the table doesn't carry one), and the cosine *distance*
#     ``embedding <=> :qvec``. The Python layer converts distance to a
#     similarity ``score = 1 - distance``.
#   - Filters ``tenant_id = :tenant_id`` and excludes ``embedding IS NULL``
#     rows so unembedded backlog is invisible to the agent.
#   - Adds engagement scoping only when the caller supplied one *and* the
#     table carries an ``engagement_id`` (oracle_chat_turns reaches
#     engagement via ``oracle_conversations`` — we filter through a JOIN
#     in that case).
#   - ORDERs by the cosine distance + LIMITs.
#
# ``:qvec`` is bound as a string the pg driver casts to ``vector`` via the
# explicit ``CAST(... AS vector)``. Binding (not interpolation) is the
# vector-injection mitigation called out in scope-v2 §10.3.

_LEDGER_SQL = """
SELECT
    id,
    summary AS summary,
    occurred_at AS occurred_at,
    (embedding <=> CAST(:qvec AS vector)) AS distance
FROM ledger_events
WHERE tenant_id = :tenant_id
  AND embedding IS NOT NULL
  {engagement_clause}
ORDER BY embedding <=> CAST(:qvec AS vector)
LIMIT :row_limit
"""

_MATRIX_NODE_SQL = """
SELECT
    id,
    title AS summary,
    updated_at AS occurred_at,
    (embedding <=> CAST(:qvec AS vector)) AS distance
FROM matrix_nodes
WHERE tenant_id = :tenant_id
  AND embedding IS NOT NULL
  {engagement_clause}
ORDER BY embedding <=> CAST(:qvec AS vector)
LIMIT :row_limit
"""

_INSIGHT_SQL = """
SELECT
    id,
    title AS summary,
    created_at AS occurred_at,
    (embedding <=> CAST(:qvec AS vector)) AS distance
FROM matrix_insights
WHERE tenant_id = :tenant_id
  AND embedding IS NOT NULL
  {engagement_clause}
ORDER BY embedding <=> CAST(:qvec AS vector)
LIMIT :row_limit
"""

# oracle_chat_turns carries only tenant_id directly; engagement scoping
# requires a join to oracle_conversations. When the caller does NOT
# supply engagement_id, we skip the join entirely (cheaper plan).
_CONVERSATION_SQL_NO_ENG = """
SELECT
    id,
    content AS summary,
    created_at AS occurred_at,
    (embedding <=> CAST(:qvec AS vector)) AS distance
FROM oracle_chat_turns
WHERE tenant_id = :tenant_id
  AND embedding IS NOT NULL
ORDER BY embedding <=> CAST(:qvec AS vector)
LIMIT :row_limit
"""

_CONVERSATION_SQL_WITH_ENG = """
SELECT
    t.id AS id,
    t.content AS summary,
    t.created_at AS occurred_at,
    (t.embedding <=> CAST(:qvec AS vector)) AS distance
FROM oracle_chat_turns AS t
JOIN oracle_conversations AS c ON c.id = t.conversation_id
WHERE t.tenant_id = :tenant_id
  AND c.engagement_id = :engagement_id
  AND t.embedding IS NOT NULL
ORDER BY t.embedding <=> CAST(:qvec AS vector)
LIMIT :row_limit
"""


def _resolve_sql(kind: VectorKind, *, engagement_scoped: bool) -> str:
    """Return the parameterized SQL for ``kind`` with optional engagement filter."""
    if kind == "ledger":
        clause = "AND engagement_id = :engagement_id" if engagement_scoped else ""
        return _LEDGER_SQL.format(engagement_clause=clause)
    if kind == "matrix_node":
        clause = "AND engagement_id = :engagement_id" if engagement_scoped else ""
        return _MATRIX_NODE_SQL.format(engagement_clause=clause)
    if kind == "insight":
        # matrix_insights.engagement_id is nullable — when the caller
        # supplied an engagement, restrict to insights that match it
        # (tenant-wide insights stay out of an engagement-scoped query).
        clause = "AND engagement_id = :engagement_id" if engagement_scoped else ""
        return _INSIGHT_SQL.format(engagement_clause=clause)
    if kind == "conversation":
        return _CONVERSATION_SQL_WITH_ENG if engagement_scoped else _CONVERSATION_SQL_NO_ENG
    raise ToolError(f"unknown vector_search kind: {kind!r}")


def _vector_literal(vec: list[float]) -> str:
    """Render a Python float list as a pgvector text literal.

    pgvector accepts ``'[0.1,0.2,...]'`` cast to ``vector``. We bind this
    string as a parameter (the SQL template carries ``CAST(:qvec AS
    vector)``); pgvector parses the literal server-side. Floats are
    formatted with ``repr`` so we don't lose precision on common round
    numbers and so the format stays deterministic for caching.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _is_missing_embedding_error(exc: Exception) -> bool:
    """True when the SQL failed because Wave A's migration hasn't landed."""
    msg = str(exc).lower()
    return "column" in msg and "embedding" in msg and "does not exist" in msg


async def _search_one_kind(
    session: AsyncSession,
    *,
    kind: VectorKind,
    qvec_literal: str,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    row_limit: int,
) -> list[VectorSearchHit]:
    """Issue the per-kind HNSW cosine query + materialize ``VectorSearchHit``s.

    Returns an empty list when the underlying table either has no
    embedded rows or doesn't yet carry the ``embedding`` column (Wave A
    may not be merged). Tool callers see the same "no recall" outcome
    in either case so the agent loop's fallback chain ("vector_search
    miss -> keyword_search") works identically pre- and post-migration.
    """
    # Scope when the caller supplied one. ``matrix_insights.engagement_id``
    # is nullable in the schema, but the agent's contract for an
    # engagement-scoped query is "give me only rows that match this
    # engagement" — tenant-wide insights are intentionally excluded so
    # cross-engagement pollution can't leak via the insight surface.
    engagement_scoped = engagement_id is not None

    sql = _resolve_sql(kind, engagement_scoped=engagement_scoped)
    params: dict[str, Any] = {
        "qvec": qvec_literal,
        "tenant_id": tenant_id,
        "row_limit": int(row_limit),
    }
    if engagement_scoped:
        params["engagement_id"] = engagement_id

    stmt = text(sql).bindparams(
        bindparam("qvec"),
        bindparam("tenant_id"),
        bindparam("row_limit"),
        *([bindparam("engagement_id")] if engagement_scoped else []),
    )
    try:
        result = await session.execute(stmt, params)
    except ProgrammingError as exc:
        if _is_missing_embedding_error(exc):
            # Wave A migration hasn't landed in this environment — the
            # agent loop should still get a clean empty recall.
            await session.rollback()
            return []
        raise

    hits: list[VectorSearchHit] = []
    for row in result.mappings().all():
        distance = float(row["distance"])
        # pgvector cosine distance is in ``[0, 2]``; similarity is the
        # standard ``1 - distance`` so a perfect match is 1.0. We do
        # NOT clamp negative values here — that would mask an upstream
        # numerical bug in the embedder.
        score = 1.0 - distance
        summary = row["summary"] or ""
        if isinstance(summary, str) and len(summary) > 500:
            summary = summary[:500] + "..."
        occurred_at_val = row["occurred_at"]
        occurred_at_iso: str | None
        if occurred_at_val is None:
            occurred_at_iso = None
        elif hasattr(occurred_at_val, "isoformat"):
            occurred_at_iso = occurred_at_val.isoformat()
        else:
            occurred_at_iso = str(occurred_at_val)
        hits.append(
            VectorSearchHit(
                kind=kind,
                id=row["id"] if isinstance(row["id"], uuid.UUID) else uuid.UUID(str(row["id"])),
                summary=summary,
                score=score,
                occurred_at=occurred_at_iso,
            )
        )
    return hits


def _citation_kind_for(kind: VectorKind) -> str:
    """Map a vector_search ``kind`` to the Citation taxonomy (Phase 1)."""
    if kind == "ledger":
        return "event"
    if kind == "matrix_node":
        return "node"
    if kind == "insight":
        return "insight"
    if kind == "conversation":
        return "turn"
    raise ToolError(f"no citation mapping for kind: {kind!r}")


async def vector_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    query: str,
    embedder: VoyageEmbedder,
    kind: VectorKind | None = None,
    limit: int = _VECTOR_DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """HNSW cosine-similarity recall across the four embedded source tables.

    Scope:
        - ``kind=None`` (default): search all four tables, merge by
          similarity, return the top ``limit`` overall.
        - ``kind="ledger" | "matrix_node" | "insight" | "conversation"``:
          search only that table.

    Tenant + engagement scoping:
        - ``tenant_id`` is always required and applied.
        - ``engagement_id`` (when supplied) is applied to *all* kinds.
          For ``conversation`` the filter joins through
          ``oracle_conversations``. For ``insight`` the
          (nullable) engagement column must equal the supplied id —
          tenant-wide insights are excluded from an engagement-scoped
          call.

    SQL safety:
        - The query vector is bound as a single ``:qvec`` parameter and
          cast server-side. Never interpolated.
        - ``tenant_id`` and ``engagement_id`` are bound UUID parameters.

    Audit:
        - One ``agent_tool_invocation`` ledger row per call carrying
          ``{tool, kind, query_chars, hits, latency_ms}`` in ``detail``
          (mirrors the helper's existing shape; see ``audit.py``).
    """
    started = time.perf_counter()
    if tenant_id is None:
        raise ToolError("tenant_id is required")
    if isinstance(tenant_id, str):
        try:
            tenant_id = uuid.UUID(tenant_id)
        except ValueError as exc:
            raise ToolError(f"tenant_id is not a valid UUID: {tenant_id!r}") from exc
    if engagement_id is not None and isinstance(engagement_id, str):
        try:
            engagement_id = uuid.UUID(engagement_id)
        except ValueError as exc:
            raise ToolError(f"engagement_id is not a valid UUID: {engagement_id!r}") from exc
    if not query or not query.strip():
        raise ToolError("query must be non-empty")
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")
    if kind is not None and kind not in _VECTOR_KINDS:
        raise ToolError(f"kind must be one of {_VECTOR_KINDS}, got {kind!r}")
    if embedder is None:
        raise ToolError("embedder is required for vector_search")

    # Embed the query. Any embedder transport error is surfaced as a
    # ToolError so the dispatcher converts it into an is_error
    # tool_result rather than crashing the turn.
    try:
        # Wave B's VoyageEmbedder.embed() takes a batch + returns a list of
        # vectors. We embed exactly one query string and take vector 0.
        qvecs = await embedder.embed([query.strip()])
    except Exception as exc:
        raise ToolError(f"embedder failed: {exc!s}") from exc
    if not isinstance(qvecs, list) or not qvecs or not isinstance(qvecs[0], list) or not qvecs[0]:
        raise ToolError("embedder returned an empty or non-list vector")
    qvec = qvecs[0]

    qvec_literal = _vector_literal(qvec)
    target_kinds: tuple[VectorKind, ...] = (kind,) if kind is not None else _VECTOR_KINDS
    # When merging multiple kinds, overfetch so each kind contributes its
    # best candidates to the global ranking. The final slice trims to
    # ``limit``. Per-kind fetch cap stays bounded by ``_MAX_LIMIT``.
    per_kind_fetch = limit if len(target_kinds) == 1 else min(limit * 2, _MAX_LIMIT)

    all_hits: list[VectorSearchHit] = []
    for k in target_kinds:
        all_hits.extend(
            await _search_one_kind(
                session,
                kind=k,
                qvec_literal=qvec_literal,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                row_limit=per_kind_fetch,
            )
        )

    # Merge: higher score first, ties broken deterministically by id so
    # the audit ledger sees stable ordering across reruns of the same query.
    all_hits.sort(key=lambda h: (-h.score, str(h.id)))
    top = all_hits[:limit]

    rows: list[dict[str, Any]] = [h.model_dump(mode="json") for h in top]
    citations: list[Citation] = [
        Citation(kind=_citation_kind_for(h.kind), id=h.id)  # type: ignore[arg-type]
        for h in top
    ]
    duration_ms = (time.perf_counter() - started) * 1000.0
    truncated = len(all_hits) > limit

    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="vector_search",
            input_hash=hash_tool_input(
                {
                    "query": query,
                    "kind": kind,
                    "limit": limit,
                    "engagement_scoped": engagement_id is not None,
                }
            ),
            tenant_id=tenant_id,
            # engagement_id may be None — emit_tool_invocation typed it
            # as required, so pass a zero-UUID sentinel in that rare path.
            engagement_id=engagement_id if engagement_id is not None else uuid.UUID(int=0),
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )

    detail = (
        f"vector_search kind={kind or 'all'} hits={len(rows)} query_chars={len(query)} latency_ms={duration_ms:.1f}"
    )
    return ToolResult(
        name="vector_search",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
        detail=detail,
    )


register_tool(
    ToolSpec(
        name="keyword_search",
        description="ILIKE keyword recall over ledger event summaries + matrix node titles.",
        input_schema=KEYWORD_SEARCH_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="vector_search",
        description=(
            "Semantic vector recall over ledger events, matrix nodes, "
            "matrix insights, and Oracle chat turns. Use as a fuzzy "
            "fallback when curated lookup (matrix index, keyword_search) "
            "misses; returns top-N hits ranked by cosine similarity."
        ),
        input_schema=VECTOR_SEARCH_INPUT_SCHEMA,
    )
)


__all__ = [
    "KEYWORD_SEARCH_INPUT_SCHEMA",
    "VECTOR_SEARCH_INPUT_SCHEMA",
    "VectorKind",
    "VectorSearchHit",
    "keyword_search",
    "vector_search",
]
