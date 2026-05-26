"""Cypher helper for the Apache AGE ``deployai_matrix`` graph.

Thin async wrapper that wires an ``AsyncSession`` to AGE's ``cypher(...)``
function call. Two non-obvious invariants are enforced here, and only
here, so callers can stay focused on the query they want to write:

1. **Tenant + engagement filter required.** AGE has no SQL-style parameter
   binding — every Cypher property filter is embedded as a literal in the
   query string. To keep multi-tenant isolation honest we refuse any
   Cypher payload that does not literally reference both ``tenant_id``
   and ``engagement_id`` as property names. Callers always embed the
   actual UUID literal too; this module checks the *property name* is
   present so a typo can't silently bypass isolation.

2. **AGE session preamble.** Every connection that talks to ag_catalog
   must ``LOAD 'age'`` and put ag_catalog on the search_path first; we
   run that on the underlying psycopg connection before the cypher call.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GRAPH_NAME = "deployai_matrix"


class CypherIsolationError(ValueError):
    """Raised when a Cypher payload omits required tenant_id / engagement_id filters."""


def _ensure_isolation_filters(cypher: str) -> None:
    if "tenant_id" not in cypher or "engagement_id" not in cypher:
        raise CypherIsolationError(
            "Cypher payload must explicitly filter on both tenant_id and "
            "engagement_id properties; AGE does not parameter-bind."
        )


async def cypher_query(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    cypher: str,
    return_columns: list[str],
) -> list[dict[str, Any]]:
    """Run a Cypher query against ``deployai_matrix`` scoped to one engagement.

    ``cypher`` MUST embed both ``tenant_id`` and ``engagement_id`` as
    property filters on every vertex / edge MATCH it touches — AGE has no
    SQL-style parameter binding, so isolation is enforced literally in the
    query text. We validate the property *names* are present; callers
    must embed the literal UUID values themselves with proper quoting.

    The ``tenant_id`` and ``engagement_id`` kwargs are accepted to document
    caller intent and are reserved for future audit-emit integration; they
    are intentionally not interpolated for the caller. Returns a list of
    dicts keyed by ``return_columns``.
    """

    _ensure_isolation_filters(cypher)
    # tenant_id / engagement_id reserved for future audit emission; caller
    # embeds the literals into the cypher string today.
    del tenant_id, engagement_id

    column_decl = ", ".join(f"{name} agtype" for name in return_columns)
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {cypher} $$) AS ({column_decl})"

    await session.execute(text("LOAD 'age'"))
    await session.execute(text('SET search_path = ag_catalog, "$user", public'))
    result = await session.execute(text(sql))
    rows = result.all()
    return [dict(zip(return_columns, row, strict=True)) for row in rows]
