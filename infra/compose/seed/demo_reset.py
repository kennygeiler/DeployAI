#!/usr/bin/env python3
"""Wave 3 K1 — reset the cold-start demo engagement.

Calls ``POST /internal/v1/admin/demo/reset-acme`` on the running control
plane, which deletes the "Acme Robotics — Pilot Deployment" engagement (all
events, ledger entries, matrix rows, proposals, and chat state) and
recreates it empty. Rerunnable between meetings; the endpoint is idempotent.

The three staged demo artifacts live in ``demo/artifacts/`` — they are the
script partners for the three-act demo (capture → ask → teach; see
docs/plans/2026-08-11-pilot-refresh-backlog.md Part 5).

Usage:
    make demo-reset
or:
    python3 infra/compose/seed/demo_reset.py

Env:
    DEMO_TENANT_ID          target tenant (default: the compose seed tenant
                            11111111-1111-1111-1111-111111111111)
    DEPLOYAI_CP_BASE_URL    control plane base URL (default http://localhost:8000)
    DEPLOYAI_WEB_BASE_URL   web base URL for the printed link (default http://localhost:3000)

The internal API key is read from ``infra/compose/.env``
(DEPLOYAI_INTERNAL_API_KEY), falling back to the compose default
``dev-internal-insecure``.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / "infra" / "compose" / ".env"
ARTIFACTS_DIR = REPO_ROOT / "demo" / "artifacts"

DEFAULT_TENANT_ID = "11111111-1111-1111-1111-111111111111"
DEFAULT_INTERNAL_KEY = "dev-internal-insecure"

CP_BASE_URL = os.environ.get("DEPLOYAI_CP_BASE_URL", "http://localhost:8000")
WEB_BASE_URL = os.environ.get("DEPLOYAI_WEB_BASE_URL", "http://localhost:3000")

ARTIFACTS = (
    ("kickoff-transcript.txt", "meeting_note", "Act 1 opener — the kickoff call"),
    ("email-thread.txt", "email", "the buried commitment (safety-cert docs by Oct 3)"),
    ("slack-export.txt", "manual_import", "the unfiled risk (wifi dead zones vs fleet heartbeat)"),
)


def _load_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    env = _load_env_file()
    internal_key = (
        os.environ.get("DEPLOYAI_INTERNAL_API_KEY")
        or env.get("DEPLOYAI_INTERNAL_API_KEY")
        or DEFAULT_INTERNAL_KEY
    )
    tenant_id = os.environ.get("DEMO_TENANT_ID", DEFAULT_TENANT_ID)

    url = f"{CP_BASE_URL}/internal/v1/admin/demo/reset-acme?tenant_id={tenant_id}"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"X-DeployAI-Internal-Key": internal_key, "Content-Type": "application/json"},
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        print(f"demo-reset: control plane returned {e.code}: {detail}", file=sys.stderr)
        if e.code == 404:
            print(
                "demo-reset: tenant not found — bring the stack up and seed it first "
                "(`make dev`, or set DEMO_TENANT_ID to an existing tenant).",
                file=sys.stderr,
            )
        return 1
    except urllib.error.URLError as e:
        print(f"demo-reset: cannot reach control plane at {CP_BASE_URL}: {e.reason}", file=sys.stderr)
        print("demo-reset: is the stack up? (`make dev`)", file=sys.stderr)
        return 1

    eid = body["engagement_id"]
    wiped = body["deleted_engagements"]
    print(f"demo-reset: ✓ {body['engagement_name']}")
    print(f"demo-reset:   engagement {eid} on tenant {tenant_id}")
    if wiped:
        print(
            f"demo-reset:   wiped previous run ({body['deleted_events']} events, "
            f"{body['deleted_ledger_events']} ledger entries) and recreated empty"
        )
    else:
        print("demo-reset:   created fresh (no previous Acme engagement found)")

    print()
    print("Next steps — the three-act cold start:")
    print(f"  1. Open {WEB_BASE_URL}/engagements/{eid} and go to the Capture tab.")
    for i, (fname, source, why) in enumerate(ARTIFACTS, start=2):
        path = ARTIFACTS_DIR / fname
        marker = "" if path.exists() else "  [MISSING]"
        print(f"  {i}. Paste demo/artifacts/{fname} (source: {source}) — {why}.{marker}")
    print("  5. Accept/reject the extraction proposals in Needs-you after each paste.")
    print('  6. Then ask Kenny: "What did we decide about inference latency?"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
