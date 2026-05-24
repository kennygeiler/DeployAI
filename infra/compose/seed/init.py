#!/usr/bin/env python3
"""Sprint 1 inc 3 — headless first-run install script.

CLI mirror of the browser onboarding wizard. Use this when you want to
stand DeployAI up from a Makefile / Ansible / CI step instead of clicking
through `/onboarding` in a browser. End state matches what the wizard
produces:

    1 app_tenant + 1 tenant_llm_config + 1 engagement + 1 app_user
    + 1 engagement_member

Tenant create has no public CP route (only SCIM provisions users at
runtime), so we insert that row via psql. Everything else uses the
internal CP API:

    PUT  /internal/v1/tenants/{tid}/llm-config   — Sprint 1 inc 1
    POST /internal/v1/engagements?tenant_id=...  — Phase 1
    POST /internal/v1/tenants/{tid}/users        — Sprint 1 inc 2
    POST /internal/v1/engagements/{eid}/members  — Phase 2

Idempotent at the tenant level: rerunning with the same `--tenant-id`
upserts the tenant row, and the user/member endpoints return 409 on
duplicate (which we treat as success). Calling the LLM PUT again
overwrites the row; pass --no-api-key on subsequent runs to preserve
the stored key.

Usage:
    python3 infra/compose/seed/init.py \\
        --tenant-name "Acme Team" \\
        --llm-provider anthropic --llm-model claude-opus-4-5 \\
        --llm-api-key "$ANTHROPIC_API_KEY" \\
        --engagement-name "Acme migration pilot" \\
        --user-name kenny --user-email kenny@acme.com \\
        --role deployment_strategist

Every flag also reads its DEPLOYAI_INIT_* env-var equivalent so you can
script this from a .env file. Flags win over env. Required values
missing on both sides → exit 2 with the example invocation above.

Requires the compose stack already up (postgres + control-plane
healthy). Run after `make dev`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from templates import TEMPLATES, Template

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "infra" / "compose" / "docker-compose.yml"
ENV_FILE = REPO_ROOT / "infra" / "compose" / ".env"

VALID_PROVIDERS = ("anthropic", "openai", "stub")
VALID_ROLES = ("deployment_strategist", "fde", "biz_dev")
VALID_TEMPLATES = tuple(TEMPLATES.keys())


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


ENV = _load_env_file()


def _env(*names: str) -> str | None:
    """First non-empty value from process env, then compose .env, by name."""
    for n in names:
        v = os.environ.get(n) or ENV.get(n)
        if v:
            return v
    return None


INTERNAL_KEY = _env("DEPLOYAI_INTERNAL_API_KEY") or "dev-internal-insecure"
POSTGRES_USER = ENV.get("POSTGRES_USER", "deployai")
POSTGRES_DB = ENV.get("POSTGRES_DB", "deployai")
CP_BASE_URL = os.environ.get("DEPLOYAI_CP_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _psql(sql: str) -> None:
    """Run a SQL statement inside the compose postgres container."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stdout + "\n" + res.stderr + "\n")
        sys.exit(f"init: psql failed (rc={res.returncode})")


def _http(method: str, path: str, body: dict | None = None) -> dict | list | None:
    url = f"{CP_BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "X-DeployAI-Internal-Key": INTERNAL_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")
        # 409 conflict = "already exists" — caller may want to swallow it.
        raise SystemExit(f"init: HTTP {e.code} on {method} {path}\n{msg}") from e
    except urllib.error.URLError as e:
        raise SystemExit(
            f"init: connection failed to {url} — is the compose stack up? ({e.reason})"
        ) from e


def _http_with_409_ok(method: str, path: str, body: dict | None = None) -> dict | list | None:
    """Same as `_http` but treats 409 (conflict / already exists) as success."""
    try:
        return _http(method, path, body)
    except SystemExit as e:
        if "HTTP 409" in str(e):
            return None
        raise


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def step_tenant(tenant_id: str, tenant_name: str) -> None:
    """Upsert the app_tenants row via psql (no public CP create route)."""
    print(f"init: tenant '{tenant_name}' ({tenant_id[:8]}…)")
    safe_name = tenant_name.replace("'", "''")
    _psql(
        f"INSERT INTO app_tenants (id, name) "
        f"VALUES ('{tenant_id}'::uuid, '{safe_name}') "
        f"ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;"
    )


def step_llm_config(tenant_id: str, provider: str, model: str | None, api_key: str | None) -> None:
    print(f"init: llm-config provider={provider} model={model or '(default)'}")
    body: dict = {"provider": provider}
    if model:
        body["model_name"] = model
    if api_key:
        body["api_key"] = api_key
    _http("PUT", f"/internal/v1/tenants/{tenant_id}/llm-config", body)


def step_engagement(
    tenant_id: str, name: str, customer: str | None, phase: str | None = None
) -> str:
    print(f"init: engagement '{name}'")
    body: dict = {"name": name}
    if customer:
        body["customer_account"] = customer
    if phase:
        body["current_phase"] = phase
    r = _http("POST", f"/internal/v1/engagements?tenant_id={tenant_id}", body)
    assert isinstance(r, dict), f"engagement create returned {type(r)}"
    return str(r["id"])


def step_user(tenant_id: str, user_name: str, email: str | None) -> str | None:
    """Create the AppUser. Returns the new user_id, or None if 409 (already exists)."""
    print(f"init: user '{user_name}'")
    body: dict = {"user_name": user_name}
    if email:
        body["email"] = email
    r = _http_with_409_ok("POST", f"/internal/v1/tenants/{tenant_id}/users", body)
    if r is None:
        print(f"  user '{user_name}' already exists — skip membership add")
        return None
    assert isinstance(r, dict)
    return str(r["id"])


def step_member(tenant_id: str, engagement_id: str, user_id: str, role: str) -> None:
    print(f"init: member role={role} user={user_id[:8]}… → eng {engagement_id[:8]}…")
    _http_with_409_ok(
        "POST",
        f"/internal/v1/engagements/{engagement_id}/members?tenant_id={tenant_id}",
        {"user_id": user_id, "role": role},
    )


def step_starter_nodes(
    tenant_id: str, engagement_id: str, starter_nodes: list[dict]
) -> None:
    """POST a template's starter matrix nodes onto the new engagement."""
    print(f"init: seeding {len(starter_nodes)} starter matrix node(s)")
    for spec in starter_nodes:
        body = {
            "node_type": spec["node_type"],
            "title": spec["title"],
            "attributes": spec.get("attributes", {}),
        }
        node_status = spec.get("status")
        if node_status is not None:
            body["status"] = node_status
        _http(
            "POST",
            f"/internal/v1/engagements/{engagement_id}/matrix/nodes?tenant_id={tenant_id}",
            body,
        )


def step_template_prompts(tenant_id: str, agent_prompts: dict[str, str]) -> None:
    """PUT template prompt overrides per agent. Forward-compat: a 404 means
    sibling B1.1's agent-prompts endpoint is not merged yet — log and skip."""
    if not agent_prompts:
        return
    for agent_name, prompt_suffix in agent_prompts.items():
        path = f"/internal/v1/tenants/{tenant_id}/agent-prompts/{agent_name}"
        try:
            _http("PUT", path, {"prompt_suffix": prompt_suffix})
            print(f"init: prompt override saved for agent={agent_name}")
        except SystemExit as e:
            if "HTTP 404" in str(e):
                print(
                    f"init: skipped agent={agent_name} — "
                    "prompt endpoint not yet available"
                )
                continue
            raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _required(value: str | None, flag: str, env_var: str) -> str:
    if not value:
        sys.exit(
            f"init: --{flag} (or {env_var}) is required. "
            f"See `python3 infra/compose/seed/init.py --help`."
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tenant-id",
        default=_env("DEPLOYAI_INIT_TENANT_ID"),
        help="UUID for the tenant. Defaults to a new random UUID; pass a stable one "
        "to make the init script idempotent across reruns.",
    )
    parser.add_argument("--tenant-name", default=_env("DEPLOYAI_INIT_TENANT_NAME"))
    parser.add_argument(
        "--llm-provider",
        default=_env("DEPLOYAI_INIT_LLM_PROVIDER", "DEPLOYAI_LLM_PROVIDER"),
        choices=VALID_PROVIDERS,
        nargs="?",
    )
    parser.add_argument("--llm-model", default=_env("DEPLOYAI_INIT_LLM_MODEL"))
    parser.add_argument(
        "--llm-api-key",
        default=_env("DEPLOYAI_INIT_LLM_API_KEY", "ANTHROPIC_API_KEY"),
        help="Persisted in the tenant_llm_configs row. Omit to leave the key "
        "unset on the row (the agent factory falls back to the server env).",
    )
    parser.add_argument("--engagement-name", default=_env("DEPLOYAI_INIT_ENGAGEMENT_NAME"))
    parser.add_argument("--customer-account", default=_env("DEPLOYAI_INIT_CUSTOMER_ACCOUNT"))
    parser.add_argument("--user-name", default=_env("DEPLOYAI_INIT_USER_NAME"))
    parser.add_argument("--user-email", default=_env("DEPLOYAI_INIT_USER_EMAIL"))
    parser.add_argument(
        "--role",
        default=_env("DEPLOYAI_INIT_ROLE") or "deployment_strategist",
        choices=VALID_ROLES,
    )
    parser.add_argument(
        "--template",
        default=_env("DEPLOYAI_INIT_TEMPLATE"),
        choices=VALID_TEMPLATES,
        help="Industry template to seed: fills engagement/customer/phase defaults, "
        "creates a small starter set of matrix nodes, and saves vertical-tuned "
        "agent-prompt overrides. Explicit --engagement-name / --customer-account "
        "still win over the template's defaults.",
    )
    args = parser.parse_args(argv)

    tenant_name = _required(args.tenant_name, "tenant-name", "DEPLOYAI_INIT_TENANT_NAME")
    llm_provider = _required(args.llm_provider, "llm-provider", "DEPLOYAI_INIT_LLM_PROVIDER")

    template: Template | None = TEMPLATES[args.template] if args.template else None

    engagement_name = args.engagement_name or (template.default_engagement_name if template else None)
    engagement_name = _required(
        engagement_name, "engagement-name", "DEPLOYAI_INIT_ENGAGEMENT_NAME"
    )
    customer_account = args.customer_account or (
        template.default_customer_account if template else None
    )
    engagement_phase = template.default_phase if template else None

    user_name = _required(args.user_name, "user-name", "DEPLOYAI_INIT_USER_NAME")

    tenant_id = args.tenant_id or str(uuid.uuid4())

    step_tenant(tenant_id, tenant_name)
    step_llm_config(tenant_id, llm_provider, args.llm_model, args.llm_api_key)
    engagement_id = step_engagement(tenant_id, engagement_name, customer_account, engagement_phase)
    user_id = step_user(tenant_id, user_name, args.user_email)
    if user_id is not None:
        step_member(tenant_id, engagement_id, user_id, args.role)
    if template is not None:
        step_starter_nodes(tenant_id, engagement_id, template.starter_nodes)
        step_template_prompts(tenant_id, template.agent_prompts)

    print()
    print("init: done. Next steps:")
    print(f"  Tenant id:     {tenant_id}")
    print(f"  Engagement id: {engagement_id}")
    print(f"  Open the web UI: {os.environ.get('DEPLOYAI_WEB_BASE_URL', 'http://localhost:3000')}/engagements/{engagement_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
