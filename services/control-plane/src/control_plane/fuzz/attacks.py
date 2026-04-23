"""Attack-class generators for the cross-tenant isolation fuzzer.

Each class is a coroutine `async def run(session, scope_tenant, other_tenant,
table, rows, rng) -> AttackResult` so the harness can loop uniformly over
them. Keep these **free of business logic** — the harness owns seeding,
reporting, and verdicting; these functions only execute the attack and return
an observed outcome.

Attack classes (Story 1.10, AC3):
    1. Baseline RLS read
    2. No-scope read (run outside any TenantScopedSession)
    3. (intentionally omitted — see cross_tenant._fuzz_table docstring)
    4. SET ROLE / SET SESSION AUTHORIZATION escalation
    5. ORM escape hatches (text() literal-string tenant_ids)
    6. Cross-tenant write (INSERT / UPDATE)
    7. SQL injection via string-concat tenant_id
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


@dataclass
class AttackResult:
    """What the harness records for a single attempt.

    `leaked_rows` is non-empty iff isolation failed. `raised_sqlstate` is the
    Postgres SQLSTATE of an expected deny — recording it lets the report prove
    the deny was a *permission* deny (42501), not an unrelated parse error.

    Rows are typed as ``Sequence[Any]`` rather than ``tuple[Any, ...]`` so
    SQLAlchemy ``Row`` objects (which are tuple-like but not ``tuple``
    instances) can be stored directly without a copy-convert round-trip.
    """

    sql: str
    leaked_rows: list[Any]
    raised_sqlstate: str | None


async def attack_baseline_rls_read(
    session: AsyncSession,
    *,
    scope_tenant: UUID,
    other_tenant: UUID,
    table: str,
    other_tenant_row_ids: list[UUID],
    rng: random.Random,
) -> AttackResult:
    """AC3.1 — under tenant A's scope, SELECT a specific B-owned row id.

    RLS must filter silently (zero rows). If even one row comes back, that is
    a hard isolation break.
    """
    target_id = rng.choice(other_tenant_row_ids)
    sql = f"SELECT id, tenant_id FROM {table} WHERE id = :rid"
    try:
        result = await session.execute(text(sql), {"rid": str(target_id)})
        rows = result.all()
    except DBAPIError as exc:
        return AttackResult(sql=sql, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    leaked = [r for r in rows if _row_tenant_mismatches(r, scope_tenant)]
    return AttackResult(sql=sql, leaked_rows=leaked, raised_sqlstate=None)


async def attack_no_scope_read(
    conn: AsyncConnection,
    *,
    table: str,
) -> AttackResult:
    """AC3.2 — raw connection, no `SET LOCAL`. Must return zero rows."""
    sql = f"SELECT id, tenant_id FROM {table} LIMIT 100"
    try:
        result = await conn.execute(text(sql))
        rows = result.all()
    except DBAPIError as exc:
        return AttackResult(sql=sql, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    return AttackResult(sql=sql, leaked_rows=list(rows), raised_sqlstate=None)


async def attack_set_role_escalation(
    conn: AsyncConnection,
    *,
    table: str,
    rng: random.Random,
) -> AttackResult:
    """AC3.4 — try to escalate to a BYPASSRLS role.

    `deployai_app` is NOINHERIT and has no role-memberships that carry
    BYPASSRLS, so every target below must error with SQLSTATE 42501. Two
    failure modes:

    1. ``SET ROLE`` succeeds and the follow-up SELECT returns rows: classic
       leak, recorded verbatim.
    2. ``SET ROLE`` succeeds but the follow-up SELECT returns zero rows (the
       escalated identity happens to lack an ``app.current_tenant`` GUC, so
       RLS filters to empty): **still a finding** — the escalation itself is
       a privilege regression. A future grant that makes ``SET ROLE
       postgres`` succeed must not slip through simply because the target
       role's scope is empty at call time.
    """
    targets = ["postgres", "deployai"]
    commands = [
        "SET ROLE {tgt}",
        "SET SESSION AUTHORIZATION {tgt}",
        "SET LOCAL ROLE {tgt}",
    ]
    target = rng.choice(targets)
    command = rng.choice(commands).format(tgt=target)
    select_sql = f"SELECT id, tenant_id FROM {table} LIMIT 100"
    try:
        await conn.execute(text(command))
    except DBAPIError as exc:
        # Expected path: permission denied. Record the SQLSTATE for the report.
        return AttackResult(sql=command, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    # Escalation unexpectedly succeeded. Always defensively reset the role on
    # this pooled connection before returning so subsequent attempts start
    # from a clean session, regardless of the SELECT outcome below.
    try:
        try:
            result = await conn.execute(text(select_sql))
            rows = result.all()
        except DBAPIError as exc:
            return AttackResult(sql=command, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
        if rows:
            # Leak path — the escalated identity returned rows.
            return AttackResult(sql=command, leaked_rows=list(rows), raised_sqlstate=None)
        # Zero-row path — still a finding: escalation itself must never succeed.
        return AttackResult(
            sql=command,
            leaked_rows=[("ESCALATION-SUCCEEDED", command, "0 rows returned")],
            raised_sqlstate=None,
        )
    finally:
        try:
            await conn.execute(text("RESET ROLE"))
            await conn.execute(text("RESET SESSION AUTHORIZATION"))
        except DBAPIError:  # pragma: no cover
            pass


async def attack_orm_escape_text_literal(
    session: AsyncSession,
    *,
    scope_tenant: UUID,
    other_tenant: UUID,
    table: str,
) -> AttackResult:
    """AC3.5 — use `text()` with a literal string tenant_id instead of bind params.

    RLS still applies at the DB level regardless of how the ORM composed the
    query, so this should still return zero cross-tenant rows.
    """
    sql = f"SELECT id, tenant_id FROM {table} WHERE tenant_id = '{other_tenant}'"
    try:
        result = await session.execute(text(sql))
        rows = result.all()
    except DBAPIError as exc:
        return AttackResult(sql=sql, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    leaked = [r for r in rows if _row_tenant_mismatches(r, scope_tenant)]
    return AttackResult(sql=sql, leaked_rows=leaked, raised_sqlstate=None)


async def attack_cross_tenant_write(
    session: AsyncSession,
    *,
    scope_tenant: UUID,
    other_tenant: UUID,
    table: str,
    insert_template: str,
    root_engine: Any | None = None,
) -> AttackResult:
    """AC3.6 — under B's scope, try to INSERT a row with tenant_id=A.

    Must raise SQLSTATE 42501 (WITH CHECK violation). A successful insert
    is the loudest possible failure — it means the isolation is completely
    busted.

    The caller is expected to wrap this in `session.begin_nested()` so an
    *expected* deny doesn't poison the outer transaction. On a successful
    insert (the failure path) this function raises `_CrossTenantLeakCommitted`
    back to the caller so the savepoint is rolled back — we never want a
    proven leak to get persisted to the DB, even in CI.

    If `root_engine` is provided, the post-insert blast-radius count is read
    under a superuser connection (bypassing RLS), so the number reflects the
    actual row landing rather than what the attacker-scoped session can see.
    """
    sql = insert_template.format(other_tenant=other_tenant)
    try:
        await session.execute(text(sql))
    except DBAPIError as exc:
        return AttackResult(sql=sql, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    # No error: the INSERT landed. That's the failure we're hunting. Measure
    # blast radius under a superuser connection when available, then raise so
    # the savepoint rolls the persisted row back.
    count: int
    if root_engine is not None:
        try:
            async with root_engine.connect() as rconn:
                confirm = await rconn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tid"),
                    {"tid": str(other_tenant)},
                )
                count = int(confirm.scalar_one())
        except DBAPIError:
            count = -1
    else:
        count = -1
    raise _CrossTenantLeakCommitted(
        AttackResult(
            sql=sql,
            leaked_rows=[("INSERT-SUCCEEDED", f"count={count}", str(other_tenant))],
            raised_sqlstate=None,
        )
    )


class _CrossTenantLeakCommitted(Exception):  # noqa: N818 — internal sentinel, not a user-facing error
    """Sentinel raised when a cross-tenant INSERT lands.

    The outer caller in `cross_tenant._fuzz_table` catches this, records the
    wrapped `AttackResult`, and lets the enclosing `session.begin_nested()`
    ROLLBACK the persisted row. Never caught anywhere else.
    """

    def __init__(self, result: AttackResult) -> None:
        super().__init__("cross-tenant INSERT unexpectedly landed")
        self.result = result


async def attack_sql_injection(
    session: AsyncSession,
    *,
    scope_tenant: UUID,
    other_tenant: UUID,
    table: str,
    rng: random.Random,
) -> AttackResult:
    """AC3.7 — classic SQLi payloads smuggled into a WHERE clause.

    Postgres parses these as one statement each; `text()` does not do multi-
    statement execution. RLS applies to the resulting plan, so any rows that
    come back with a non-matching tenant_id are a leak.
    """
    payloads = [
        f"'{other_tenant}' OR '1'='1'",
        f"' OR tenant_id = '{other_tenant}' --",
        f"' UNION SELECT id, tenant_id FROM {table} WHERE tenant_id = '{other_tenant}' --",
        f"'{other_tenant}' /* comment */ OR true",
        f"'\\x00' OR tenant_id::text = '{other_tenant}'",
    ]
    payload = rng.choice(payloads)
    sql = f"SELECT id, tenant_id FROM {table} WHERE tenant_id::text = {payload}"
    try:
        result = await session.execute(text(sql))
        rows = result.all()
    except DBAPIError as exc:
        # Most of these will ERROR at parse time; that's fine — RLS policy
        # isn't the last line of defense here, the parser is.
        return AttackResult(sql=sql, leaked_rows=[], raised_sqlstate=_sqlstate(exc))
    leaked = [r for r in rows if _row_tenant_mismatches(r, scope_tenant)]
    return AttackResult(sql=sql, leaked_rows=leaked, raised_sqlstate=None)


def _row_tenant_mismatches(row: Any, scope_tenant: UUID) -> bool:
    """Return True if the row's `tenant_id` column is anything but `scope_tenant`.

    Row shape: `(id, tenant_id)` tuple from the SELECTs above. `tenant_id` is
    typed as UUID by SQLAlchemy + psycopg, but we still stringify both sides
    to tolerate any driver-level variance.
    """
    if len(row) < 2:
        return False
    observed = row[1]
    return str(observed) != str(scope_tenant)


def _sqlstate(exc: DBAPIError | ProgrammingError) -> str | None:
    """Pull the Postgres SQLSTATE off a DBAPIError if present."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    return getattr(orig, "sqlstate", None)
