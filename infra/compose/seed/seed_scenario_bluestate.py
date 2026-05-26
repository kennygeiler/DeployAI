#!/usr/bin/env python3
"""BlueState Health — 26-week end-to-end test bed scenario.

Host-side compose-driven wrapper. The scenario data + SQL builders live in
``control_plane.scenarios.bluestate`` so the same logic powers both this
shellout path (``make seed-scenario-bluestate``) and the in-process CP
route used by the onboarding wizard. Tenant/users/engagement/members
seeding still uses psql + the CP HTTP API for parity with seed_app.py.

Usage::

    python3 infra/compose/seed/seed_scenario_bluestate.py
    # or
    make seed-scenario-bluestate

Requires the compose stack up (``make dev``) and the same ``.env`` as
``seed_app.py``. Idempotent: re-running upserts the same UUIDs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Make the CP src tree importable so the host-side script can call into the
# moved scenario builder + event corpus without round-tripping through docker.
_CP_SRC = REPO_ROOT / "services" / "control-plane" / "src"
if str(_CP_SRC) not in sys.path:
    sys.path.insert(0, str(_CP_SRC))

from control_plane.scenarios.bluestate.builder import (  # noqa: E402
    ENGAGEMENT_ID as _CP_ENGAGEMENT_ID,
)
from control_plane.scenarios.bluestate.builder import (  # noqa: E402
    TRAILING_SILENCE_DAYS,
    TimeAnchor,
    build_scenario_sql,
)
from control_plane.scenarios.bluestate.events import (  # noqa: E402
    ALL_EVENTS,
)
from seed_app import (  # noqa: E402
    COMPOSE_FILE,
    ENV,
    ENV_FILE,
    POSTGRES_DB,
    POSTGRES_USER,
    TENANT_ID,
    USER_BIZDEV_ID,
    USER_FDE_ID,
    USER_STRATEGIST_ID,
    _psql,
    _wait_for_cp,
    seed_engagement,
    seed_members,
    seed_tenant_and_users,
)

_POSTGRES_PASSWORD = ENV.get("POSTGRES_PASSWORD", "deployai-local-dev")
_INTERNAL_DB_URL = f"postgresql+psycopg://{POSTGRES_USER}:{_POSTGRES_PASSWORD}@postgres:5432/{POSTGRES_DB}"

ENGAGEMENT_ID = _CP_ENGAGEMENT_ID
ENGAGEMENT_NAME = "BlueState Health — Member Portal Replatform"
CUSTOMER_ACCOUNT = "BlueState Health"
ENGAGEMENT_PHASE = "build"


def backfill_snapshots(engagement_id: str) -> None:
    """Backfill 182 daily matrix snapshots for the engagement (via CP container)."""
    print(f"seed: backfilling 182 snapshots for {engagement_id}…")
    snippet = (
        "import asyncio, uuid\n"
        "from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine\n"
        "import control_plane.domain.app_identity.models  # noqa: F401\n"
        "import control_plane.domain.engagement  # noqa: F401\n"
        "import control_plane.domain.matrix_snapshot  # noqa: F401\n"
        "from control_plane.snapshots.cron import backfill_snapshots\n"
        f"URL = {_INTERNAL_DB_URL!r}\n"
        f"TENANT_ID = uuid.UUID('{TENANT_ID}')\n"
        f"ENGAGEMENT_ID = uuid.UUID('{engagement_id}')\n"
        "async def main():\n"
        "    engine = create_async_engine(URL)\n"
        "    Session = async_sessionmaker(engine, expire_on_commit=False)\n"
        "    async with Session() as s:\n"
        "        n = await backfill_snapshots(s, tenant_id=TENANT_ID, engagement_id=ENGAGEMENT_ID, days=182, rebuild=True)\n"
        "        await s.commit()\n"
        "        print('wrote', n, 'snapshots')\n"
        "    await engine.dispose()\n"
        "asyncio.run(main())\n"
    )
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "control-plane",
        "python",
        "-c",
        snippet,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"snapshot backfill failed (rc={r.returncode})")


def run_analyzers_at(now_iso: str) -> None:
    """Invoke run_analyzers programmatically inside the CP container with a custom now."""
    snippet = (
        "import asyncio, uuid\n"
        "from datetime import datetime\n"
        "from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine\n"
        "from control_plane.intelligence.scheduler import run_analyzers\n"
        f"URL = {_INTERNAL_DB_URL!r}\n"
        f"TENANT_ID = uuid.UUID('{TENANT_ID}')\n"
        f"ENGAGEMENT_ID = uuid.UUID('{ENGAGEMENT_ID}')\n"
        f"NOW = datetime.fromisoformat('{now_iso}')\n"
        "async def main():\n"
        "    engine = create_async_engine(URL)\n"
        "    Session = async_sessionmaker(engine, expire_on_commit=False)\n"
        "    async with Session() as s:\n"
        "        w = await run_analyzers(s, tenant_id=TENANT_ID, engagement_id=ENGAGEMENT_ID, now=NOW)\n"
        "        await s.commit()\n"
        "        print('wrote', len(w), 'insights for now=' + NOW.isoformat())\n"
        "    await engine.dispose()\n"
        "asyncio.run(main())\n"
    )
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "control-plane",
        "python",
        "-c",
        snippet,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"run_analyzers (now={now_iso}) failed (rc={r.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="Skip snapshot backfill (faster reruns for content iteration).",
    )
    parser.add_argument(
        "--skip-analyzers",
        action="store_true",
        help="Skip running analyzers (manual run later via the helper).",
    )
    args = parser.parse_args()

    print(f"seed: target tenant={TENANT_ID}")
    print(f"seed: engagement_id={ENGAGEMENT_ID}")
    print(f"seed: events to emit = {len(ALL_EVENTS)}")

    _wait_for_cp()
    seed_tenant_and_users()
    seed_engagement(ENGAGEMENT_ID, ENGAGEMENT_NAME, CUSTOMER_ACCOUNT)
    seed_members(
        ENGAGEMENT_ID,
        [
            (USER_STRATEGIST_ID, "deployment_strategist"),
            (USER_FDE_ID, "fde"),
            (USER_BIZDEV_ID, "biz_dev"),
        ],
    )

    base_now = datetime.now(UTC)
    anchor = TimeAnchor(base_now=base_now)
    print(f"seed: W1 Monday   = {anchor.w1_monday.isoformat()}")
    print(f"seed: W26 end     = {anchor.w26_end.isoformat()}")
    print(
        f"seed: NOW         = {base_now.isoformat()} (trailing {TRAILING_SILENCE_DAYS}d silent for engagement_silence)"
    )

    sql, registry = build_scenario_sql(anchor)
    print(f"seed: applying ledger + matrix scenario SQL ({len(sql)} chars)…")
    _psql(sql)

    if not args.skip_snapshots:
        backfill_snapshots(ENGAGEMENT_ID)

    if not args.skip_analyzers:
        w14_end = anchor.at(14, 7, 23)
        w16_end_plus1 = anchor.at(16, 7, 23) + timedelta(days=1)
        w22_end_plus1 = anchor.at(22, 7, 23) + timedelta(days=1)
        w24_end_plus2 = anchor.at(24, 7, 23) + timedelta(days=2)
        go_create = anchor.at(26, 2, 15)
        go_accept_plus12 = go_create + timedelta(hours=72 + 12)
        runs = (
            ("W14 end → stakeholder_churn", w14_end),
            ("W16 end+1d → decision_cycle_slowdown", w16_end_plus1),
            ("W22 end+1d → risk_open_rate", w22_end_plus1),
            ("W24 end+2d → extractor_acceptance_drift", w24_end_plus2),
            ("W26 GO accept +12h → decision_provenance_summary", go_accept_plus12),
            ("now → engagement_silence", base_now),
        )
        for label, t in runs:
            print(f"seed: running analyzers @ {label} ({t.isoformat()})…")
            run_analyzers_at(t.isoformat())

    print()
    print("seed: scenario complete.")
    print(f"  Engagement:  {ENGAGEMENT_ID}")
    print(f"  Tenant:      {TENANT_ID}")
    print(f"  Stakeholder nodes seeded: {len(registry['stakeholders'])}")
    print(f"  Decision nodes seeded:    {len(registry['decisions'])}")
    print(f"  Risks seeded:             {len(registry['risks'])}")
    print()
    print("Verify counts via:")
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT source_kind, count(*) FROM ledger_events WHERE engagement_id='"
        + ENGAGEMENT_ID
        + "' GROUP BY 1 ORDER BY 2 DESC;\""
    )
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT count(*) FROM matrix_snapshots WHERE engagement_id='"
        + ENGAGEMENT_ID
        + "';\""
    )
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT insight_kind, severity, title FROM temporal_insights WHERE engagement_id='"
        + ENGAGEMENT_ID
        + "' ORDER BY created_at;\""
    )


if __name__ == "__main__":
    main()
