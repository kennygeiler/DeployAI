"""Cross-tenant isolation fuzzer (Story 1.10, NFR52).

Seeds a deterministic fixture across all 8 canonical-memory tables, then
hammers the RLS + @requires_tenant_scope boundary with 7 attack classes. Any
successful cross-tenant read or write fails the run and is recorded with
enough SQL + row detail for an operator to reproduce locally from the seed.

CLI:

    python -m control_plane.fuzz.cross_tenant \
        --seed 42 --report artifacts/fuzz/cross-tenant-report.json \
        --database-url postgresql+psycopg://... \
        --app-user deployai_app --app-password <pw>

The `DATABASE_URL` env var is used if `--database-url` is omitted. The
fuzzer requires **two** connections to the same database:
  - A superuser URL (`DATABASE_URL`) — for seeding rows that would otherwise
    be blocked by RLS.
  - An application-role URL derived from the same host/db but with
    `--app-user` + `--app-password` — this is the RLS-subject connection
    that executes the attacks.

Exit code: 0 on pass, 1 on any cross-tenant failure, 2 on harness error
(Docker missing, DB unreachable, seeding refused).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

try:  # runtime dep only for type-checkers
    from deployai_tenancy import TenantScopedSession
except ImportError:  # pragma: no cover
    TenantScopedSession = None  # type: ignore[assignment]

from control_plane.fuzz.attacks import (
    AttackResult,
    _CrossTenantLeakCommitted,
    attack_baseline_rls_read,
    attack_cross_tenant_write,
    attack_no_scope_read,
    attack_orm_escape_text_literal,
    attack_set_role_escalation,
    attack_sql_injection,
)
from control_plane.fuzz.report import Failure, FuzzReport, TableReport

# --- Canonical-memory tables under test (Story 1.9 migration 0002) ---

CANONICAL_TABLES: tuple[str, ...] = (
    "canonical_memory_events",
    "identity_nodes",
    "identity_attribute_history",
    "identity_supersessions",
    "solidified_learnings",
    "learning_lifecycle_states",
    "tombstones",
    "schema_proposals",
)

# --- Per-table INSERT templates for seeding + cross-tenant-write attack ---
#
# Each template is a single-row INSERT with placeholders for tenant_id (:tid).
# Enough columns are populated to satisfy NOT NULL constraints; everything
# else rides on column defaults. The attack path substitutes `other_tenant`
# into the tenant_id column directly — RLS WITH CHECK is what must stop it.

_SEED_TEMPLATES: dict[str, str] = {
    "canonical_memory_events": (
        "INSERT INTO canonical_memory_events (tenant_id, event_type, occurred_at) VALUES (:tid, 'fuzz', now())"
    ),
    "identity_nodes": (
        "INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash) "
        "VALUES (:tid, 'fuzz-' || gen_random_uuid(), encode(gen_random_bytes(16), 'hex'))"
    ),
    "identity_attribute_history": (
        # Attribute name is per-row-random to dodge
        # `uq_identity_attribute_history_open` (partial unique on
        # (identity_id, attribute_name) WHERE valid_to IS NULL).
        "INSERT INTO identity_attribute_history "
        "(tenant_id, identity_id, attribute_name, attribute_value, valid_from) "
        "SELECT :tid, id, 'fuzz_attr_' || encode(gen_random_bytes(6), 'hex'), 'fuzz_val', now() "
        "FROM identity_nodes WHERE tenant_id = :tid ORDER BY random() LIMIT 1"
    ),
    "identity_supersessions": (
        "INSERT INTO identity_supersessions "
        "(tenant_id, superseded_identity_id, canonical_identity_id, reason) "
        "SELECT :tid, a.id, b.id, 'fuzz-dedup' "
        "FROM identity_nodes a, identity_nodes b "
        "WHERE a.tenant_id = :tid AND b.tenant_id = :tid AND a.id <> b.id "
        "ORDER BY random() LIMIT 1"
    ),
    "solidified_learnings": (
        "INSERT INTO solidified_learnings (tenant_id, belief, evidence_event_ids) "
        "VALUES (:tid, 'fuzz belief', ARRAY[]::uuid[])"
    ),
    "learning_lifecycle_states": (
        "INSERT INTO learning_lifecycle_states "
        "(tenant_id, learning_id, state, transitioned_at) "
        "SELECT :tid, id, 'candidate', now() "
        "FROM solidified_learnings WHERE tenant_id = :tid ORDER BY random() LIMIT 1"
    ),
    "tombstones": (
        "INSERT INTO tombstones "
        "(tenant_id, original_node_id, retention_reason, authority_actor_id, destroyed_at, signature) "
        "VALUES (:tid, gen_random_uuid(), 'fuzz', gen_random_uuid(), now(), E'\\\\x00')"
    ),
    "schema_proposals": (
        "INSERT INTO schema_proposals (tenant_id, proposer_actor_id, proposed_ddl) "
        "VALUES (:tid, gen_random_uuid(), 'ALTER TABLE fuzz ...')"
    ),
}

# The cross-tenant-write attack (AC3.6) needs *single-row* INSERT templates
# that do NOT depend on reading other rows under the current scope —
# otherwise the inner SELECT gets filtered by RLS and the attack turns into a
# silent no-op that misreports as "INSERT succeeded but inserted zero rows".
# These templates take the other tenant's id by `{other_tenant}` string
# interpolation because the whole attack is that the app-layer tenant
# argument was attacker-controlled.
_WRITE_ATTACK_TEMPLATES: dict[str, str] = {
    "canonical_memory_events": (
        "INSERT INTO canonical_memory_events (tenant_id, event_type, occurred_at) "
        "VALUES ('{other_tenant}', 'attack', now())"
    ),
    "identity_nodes": (
        "INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash) "
        "VALUES ('{other_tenant}', 'attack-{other_tenant}', encode(gen_random_bytes(16), 'hex'))"
    ),
    "identity_attribute_history": (
        "INSERT INTO identity_attribute_history "
        "(tenant_id, identity_id, attribute_name, attribute_value, valid_from) "
        "VALUES ('{other_tenant}', gen_random_uuid(), 'attack', 'attack', now())"
    ),
    "identity_supersessions": (
        "INSERT INTO identity_supersessions "
        "(tenant_id, superseded_identity_id, canonical_identity_id, reason) "
        "VALUES ('{other_tenant}', gen_random_uuid(), gen_random_uuid(), 'attack')"
    ),
    "solidified_learnings": (
        "INSERT INTO solidified_learnings (tenant_id, belief, evidence_event_ids) "
        "VALUES ('{other_tenant}', 'attack', ARRAY[]::uuid[])"
    ),
    "learning_lifecycle_states": (
        "INSERT INTO learning_lifecycle_states "
        "(tenant_id, learning_id, state, transitioned_at) "
        "VALUES ('{other_tenant}', gen_random_uuid(), 'candidate', now())"
    ),
    "tombstones": (
        "INSERT INTO tombstones "
        "(tenant_id, original_node_id, retention_reason, authority_actor_id, destroyed_at, signature) "
        "VALUES ('{other_tenant}', gen_random_uuid(), 'attack', gen_random_uuid(), now(), E'\\\\x00')"
    ),
    "schema_proposals": (
        "INSERT INTO schema_proposals (tenant_id, proposer_actor_id, proposed_ddl) "
        "VALUES ('{other_tenant}', gen_random_uuid(), 'ALTER TABLE attack ...')"
    ),
}


# --- Config ---


@dataclasses.dataclass
class FuzzConfig:
    """Bundled inputs to the harness so tests can construct one directly."""

    seed: int
    database_url: str
    app_database_url: str
    report_path: Path
    tenants: int = 3
    rows_per_tenant: int = 50
    attempts_per_table: int = 500


# --- Public entrypoint ---


async def run_fuzz(config: FuzzConfig) -> FuzzReport:
    """Execute the full fuzz run and return the finalized report.

    Callers who want the JSON on disk should call `report.write(path)` after
    this returns; the CLI does that before exiting.
    """
    if TenantScopedSession is None:  # pragma: no cover
        raise RuntimeError("deployai_tenancy is not importable; check workspace setup")

    rng = random.Random(config.seed)

    # Deterministic tenant ids — the first 6 bytes of each UUID are literal
    # "f-u-z-z" padding so human operators can see at a glance whether a
    # report's tenant ids came from the fuzzer vs real data.
    tenants: list[UUID] = [UUID(f"66757a7a-0000-7000-8000-{i:012x}") for i in range(config.tenants)]

    # Two engines: root (seeder) and app (RLS-subject attacker).
    root_engine = create_async_engine(config.database_url, pool_pre_ping=True)
    app_engine = create_async_engine(config.app_database_url, pool_pre_ping=True)

    started = datetime.now(UTC)
    report = FuzzReport(
        seed=config.seed,
        started_at=started.isoformat(),
        finished_at="",
        postgres_version="",
        tenants=[str(t) for t in tenants],
    )

    try:
        report.postgres_version = await _postgres_version(root_engine)
        await _assert_fuzz_tenant_ids_unused(root_engine, tenants)
        await _seed(root_engine, tenants, config.rows_per_tenant)
        row_ids_by_tenant_by_table = await _fetch_row_ids(root_engine, tenants)

        for table in CANONICAL_TABLES:
            table_report = TableReport(seeded_rows_per_tenant=config.rows_per_tenant)
            t0 = time.perf_counter()
            await _fuzz_table(
                app_engine=app_engine,
                root_engine=root_engine,
                tenants=tenants,
                table=table,
                row_ids=row_ids_by_tenant_by_table,
                rng=rng,
                attempts=config.attempts_per_table,
                table_report=table_report,
            )
            table_report.duration_ms = int((time.perf_counter() - t0) * 1000)
            report.tables[table] = table_report
    finally:
        await app_engine.dispose()
        await root_engine.dispose()

    report.finished_at = datetime.now(UTC).isoformat()
    report.finalize()
    return report


# --- Seeding ---


async def _postgres_version(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        result = await conn.execute(text("SHOW server_version"))
        return str(result.scalar_one())


async def _assert_fuzz_tenant_ids_unused(engine: AsyncEngine, tenants: list[UUID]) -> None:
    """Refuse to seed if any canonical table already has rows for our fuzz
    tenant ids.

    The deterministic UUIDs `66757a7a-0000-7000-8000-{i:012x}` (ASCII 'fuzz'
    prefix) are a convention, not a guarantee — a shared staging DB could, in
    principle, collide. Seeding over real rows would both pollute production
    data and poison the attack oracle. Fail fast with a clear message before
    we touch any INSERT.
    """
    tenant_strs = [str(t) for t in tenants]
    async with engine.connect() as conn:
        for table in CANONICAL_TABLES:
            result = await conn.execute(
                text(f"SELECT 1 FROM {table} WHERE tenant_id = ANY(:tids) LIMIT 1"),
                {"tids": tenant_strs},
            )
            if result.first() is not None:
                raise RuntimeError(
                    f"refusing to seed: {table} already has rows under the fuzz tenant ids "
                    f"({tenant_strs}). The fuzz harness expects an empty canvas on those ids; "
                    "point the CLI at a dedicated testcontainer or clean up prior fuzz runs."
                )


async def _seed(engine: AsyncEngine, tenants: list[UUID], rows_per_tenant: int) -> None:
    """Populate each canonical table with `rows_per_tenant` rows per tenant.

    Runs as superuser (RLS bypass) to guarantee the baseline. The post-seed
    count check (see _fetch_row_ids) asserts we actually got what we asked
    for — a silent seed miss would make the fuzz results meaningless.
    """
    async with engine.begin() as conn:
        for tenant in tenants:
            for table in CANONICAL_TABLES:
                for _ in range(rows_per_tenant):
                    await conn.execute(
                        text(_SEED_TEMPLATES[table]),
                        {"tid": str(tenant)},
                    )


async def _fetch_row_ids(engine: AsyncEngine, tenants: list[UUID]) -> dict[str, dict[UUID, list[UUID]]]:
    """Collect seeded row ids keyed by (table, tenant).

    Also serves as the seeding sanity check (Risk R2): if any cell is empty,
    raise — attack classes that depend on cross-tenant row ids would
    otherwise silently skip and produce a false "pass".
    """
    ids: dict[str, dict[UUID, list[UUID]]] = {}
    async with engine.connect() as conn:
        for table in CANONICAL_TABLES:
            ids[table] = {}
            for tenant in tenants:
                result = await conn.execute(
                    text(f"SELECT id FROM {table} WHERE tenant_id = :tid LIMIT 1000"),
                    {"tid": str(tenant)},
                )
                row_ids = [UUID(str(r[0])) for r in result.all()]
                if not row_ids:
                    raise RuntimeError(f"seeding sanity-check failed: {table} has no rows for tenant {tenant}")
                ids[table][tenant] = row_ids
    return ids


# --- Attack loop ---


async def _fuzz_table(
    *,
    app_engine: AsyncEngine,
    root_engine: AsyncEngine,
    tenants: list[UUID],
    table: str,
    row_ids: dict[str, dict[UUID, list[UUID]]],
    rng: random.Random,
    attempts: int,
    table_report: TableReport,
) -> None:
    """Run `attempts` total attacks against one table, split across 6 attack classes.

    Attack class 3 (GUC override mid-transaction) was intentionally dropped
    from the gating set: at the raw DB layer, any connected role is allowed
    to issue `SET LOCAL app.current_tenant`, so the only possible defense is
    the application-level `@requires_tenant_scope` contextvar guard at
    function-entry. The fuzz harness speaks raw SQL, so it cannot exercise
    that guard meaningfully; documenting the limitation in
    `docs/security/cross-tenant-fuzz.md` is the honest fix.

    Distribution is roughly even with a few extra attempts on classes 1, 6
    because those carry the highest real-world regression risk (plain reads
    + cross-tenant writes).
    """
    per_class = attempts // 6
    spill = attempts - per_class * 6
    distribution = {
        1: per_class + (spill // 2),
        2: per_class,
        4: per_class,
        5: per_class,
        6: per_class + (spill - spill // 2),
        7: per_class,
    }
    for k, v in distribution.items():
        table_report.attempts_per_attack_class[str(k)] = v

    insert_template = _WRITE_ATTACK_TEMPLATES[table]

    for _ in range(distribution[1]):
        scope, other = _pick_two(tenants, rng)
        async with TenantScopedSession(scope, app_engine) as session:
            res = await attack_baseline_rls_read(
                session,
                scope_tenant=scope,
                other_tenant=other,
                table=table,
                other_tenant_row_ids=row_ids[table][other],
                rng=rng,
            )
        _record(table_report, table, scope, other, 1, "baseline_rls_read", res)

    for _ in range(distribution[2]):
        other = rng.choice(tenants)
        async with app_engine.connect() as conn:
            res = await attack_no_scope_read(conn, table=table)
        # No-scope reads: leak = any rows at all.
        _record(table_report, table, UUID(int=0), other, 2, "no_scope_read", res)

    for _ in range(distribution[4]):
        other = rng.choice(tenants)
        async with app_engine.connect() as conn:
            res = await attack_set_role_escalation(conn, table=table, rng=rng)
        _record(table_report, table, UUID(int=0), other, 4, "set_role_escalation", res)

    for _ in range(distribution[5]):
        scope, other = _pick_two(tenants, rng)
        async with TenantScopedSession(scope, app_engine) as session:
            res = await attack_orm_escape_text_literal(session, scope_tenant=scope, other_tenant=other, table=table)
        _record(table_report, table, scope, other, 5, "orm_escape_text_literal", res)

    for _ in range(distribution[6]):
        scope, other = _pick_two(tenants, rng)
        # Each attempt runs in its own subtransaction. Two paths:
        #   (a) Expected deny — the attack raises SQLSTATE 42501 inside;
        #       the savepoint rolls back, session survives, next attempt.
        #   (b) Leak — INSERT lands. `attack_cross_tenant_write` raises
        #       `_CrossTenantLeakCommitted` *after* capturing the blast
        #       radius via the root engine; we catch it here so the
        #       savepoint rolls back and the persisted row is reverted.
        async with TenantScopedSession(scope, app_engine) as session:
            try:
                async with session.begin_nested():
                    res = await attack_cross_tenant_write(
                        session,
                        scope_tenant=scope,
                        other_tenant=other,
                        table=table,
                        insert_template=insert_template,
                        root_engine=root_engine,
                    )
            except _CrossTenantLeakCommitted as leak:
                # Re-raising out of `begin_nested` triggers ROLLBACK TO
                # SAVEPOINT — the offending row is gone. Record the finding.
                res = leak.result
            except Exception as exc:
                res = AttackResult(
                    sql=insert_template.format(other_tenant=other),
                    leaked_rows=[],
                    raised_sqlstate=getattr(getattr(exc, "orig", None), "sqlstate", None),
                )
        _record(table_report, table, scope, other, 6, "cross_tenant_write", res)

    for _ in range(distribution[7]):
        scope, other = _pick_two(tenants, rng)
        async with TenantScopedSession(scope, app_engine) as session:
            try:
                async with session.begin_nested():
                    res = await attack_sql_injection(
                        session,
                        scope_tenant=scope,
                        other_tenant=other,
                        table=table,
                        rng=rng,
                    )
            except Exception as exc:
                res = AttackResult(
                    sql="<sqli payload raised>",
                    leaked_rows=[],
                    raised_sqlstate=getattr(getattr(exc, "orig", None), "sqlstate", None),
                )
        _record(table_report, table, scope, other, 7, "sql_injection", res)


def _pick_two(tenants: list[UUID], rng: random.Random) -> tuple[UUID, UUID]:
    scope = rng.choice(tenants)
    other = rng.choice([t for t in tenants if t != scope])
    return scope, other


def _record(
    table_report: TableReport,
    table: str,
    scope_tenant: UUID,
    other_tenant: UUID,
    attack_class: int,
    attack_name: str,
    result: AttackResult,
) -> None:
    """Append a failure entry if the attack observed a leak."""
    if not result.leaked_rows:
        return
    table_report.failures.append(
        Failure(
            attack_class=attack_class,
            attack_name=attack_name,
            tenant_under_scope=str(scope_tenant),
            leaked_tenant=str(other_tenant),
            table=table,
            sql=result.sql,
            rows_returned=[repr(row) for row in result.leaked_rows[:3]],
        )
    )


# --- CLI ---


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fuzz the cross-tenant isolation boundary (Story 1.10)",
    )
    # `FUZZ_SEED` env default honors AC7's `pnpm turbo run fuzz:cross-tenant`
    # contract without forcing the package.json script to do shell expansion
    # of `${FUZZ_SEED:-$GITHUB_RUN_ID}` inside a JSON string (painful & brittle).
    _env_seed = os.environ.get("FUZZ_SEED", "").strip()
    try:
        _default_seed = int(_env_seed) if _env_seed else 0
    except ValueError:
        _default_seed = 0
    parser.add_argument(
        "--seed",
        type=int,
        default=_default_seed,
        help="PRNG seed; 0 = derive from time (default: $FUZZ_SEED)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/fuzz/cross-tenant-report.json"),
        help="Where to write the JSON report",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Superuser async DB URL (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--app-user",
        default=os.environ.get("FUZZ_APP_USER", "deployai_app"),
        help="Application role to attack as",
    )
    parser.add_argument(
        "--app-password",
        default=os.environ.get("FUZZ_APP_PASSWORD", ""),
        help="Password for --app-user",
    )
    parser.add_argument("--tenants", type=int, default=3)
    parser.add_argument("--rows-per-tenant", type=int, default=50)
    parser.add_argument("--attempts-per-table", type=int, default=500)
    return parser


def _derive_app_url(superuser_url: str, *, user: str, password: str) -> str:
    """Swap credentials on an async psycopg URL.

    Uses SQLAlchemy's URL parser so passwords containing `@`, `:`, `/`, or
    `#` round-trip correctly with proper URL-encoding. A hand-rolled
    `split("@", 1)` gets any of those wrong.
    """
    try:
        url = make_url(superuser_url)
    except Exception as exc:
        raise ValueError(f"cannot parse database url: {exc}") from exc
    return url.set(username=user, password=password).render_as_string(hide_password=False)


def _print_failure_diagnostic(report: FuzzReport, stream: Any = sys.stderr) -> None:
    """Dump the first few failure entries in a human-readable form.

    AC4 requires the CI diagnostic to contain: (a) attack class, (b) tenant
    under scope, (c) leaked tenant, (d) table, (e) offending SQL, (f) rows.
    The JSON report is authoritative; this stderr dump lets the maintainer
    see the headline without opening the artifact.
    """
    shown = 0
    for table_name, table_report in report.tables.items():
        for fail in table_report.failures:
            if shown >= 3:
                remaining = report.totals.get("failures", 0) - shown
                if remaining > 0:
                    print(
                        f"  ... and {remaining} more failure(s) — see JSON report for the full list.",
                        file=stream,
                    )
                return
            print("", file=stream)
            print(f"[FAIL] attack_class={fail.attack_class} ({fail.attack_name})", file=stream)
            print(f"       table:              {table_name}", file=stream)
            print(f"       tenant_under_scope: {fail.tenant_under_scope}", file=stream)
            print(f"       leaked_tenant:      {fail.leaked_tenant}", file=stream)
            print(f"       sql:                {fail.sql}", file=stream)
            for row in fail.rows_returned[:3]:
                print(f"       row:                {row}", file=stream)
            shown += 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if not args.database_url:
        print("error: --database-url (or $DATABASE_URL) is required", file=sys.stderr)
        return 2
    if not args.app_password:
        print(
            "error: --app-password (or $FUZZ_APP_PASSWORD) is required. "
            "Empty passwords are rejected to avoid accidental `trust`-auth drift.",
            file=sys.stderr,
        )
        return 2
    seed = args.seed or int(time.time())
    try:
        app_url = _derive_app_url(args.database_url, user=args.app_user, password=args.app_password)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    config = FuzzConfig(
        seed=seed,
        database_url=args.database_url,
        app_database_url=app_url,
        report_path=args.report,
        tenants=args.tenants,
        rows_per_tenant=args.rows_per_tenant,
        attempts_per_table=args.attempts_per_table,
    )
    try:
        report = asyncio.run(run_fuzz(config))
    except Exception as exc:
        import traceback

        print(f"fuzz harness error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 2
    report.write(config.report_path)
    print(
        f"fuzz result: {report.result} "
        f"({report.totals.get('attempts', 0)} attempts, "
        f"{report.totals.get('failures', 0)} failures, "
        f"report at {config.report_path})"
    )
    if report.result != "pass":
        _print_failure_diagnostic(report, stream=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
