# Hosted pilot environment — hardening checklist

Use this when moving from **local dev** to a **hosted** strategist pilot (Epic 15–16). Pair with [`session-and-headers.md`](./session-and-headers.md) and [`README.md`](./README.md).

## Identity and tenant boundary

1. **Production `NODE_ENV`** — dev-only strategist role injection is off; actors come from JWT or edge headers.
2. **`DEPLOYAI_WEB_TRUST_JWT=1`** — set `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` (control-plane signing key material), align `DEPLOYAI_JWT_ISSUER` / `DEPLOYAI_JWT_AUDIENCE`, and issue access tokens with `tid` + V1 `roles`.
3. **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`** (recommended for pilot) — strategist routes require `x-deployai-tenant` after middleware; satisfied by JWT `tid` when JWT trust is on.
4. **Strip forged headers at the edge** — if you terminate SSO at a reverse proxy, do not forward client-supplied `x-deployai-role` / `x-deployai-tenant` unless you fully trust that path. When JWT trust is enabled and a Bearer/cookie is sent but invalid, the web app returns **401** (see session doc).
5. **`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1`** — optional defense-in-depth with JWT trust + PEM: Next middleware clears inbound strategist headers before applying JWT-derived role/tenant (see [`session-and-headers.md`](./session-and-headers.md)).

## Control plane coupling

1. **`DEPLOYAI_CONTROL_PLANE_URL`** + **`DEPLOYAI_INTERNAL_API_KEY`** on `apps/web` — required for meeting presence, ingestion status, integration listing, and CP-backed digest/evidence (below).
2. **TLS** — use `https` for CP and web in pilot; OAuth redirect URIs must match Entra (or IdP) registration.
3. **Network** — web server must reach CP internal routes; do not expose `X-DeployAI-Internal-Key` to browsers.

## Pilot data loaders (Epic 16)

Oracle HTTP probe + digest/evidence grounding are summarized in [`oracle-and-digest-pilot.md`](./oracle-and-digest-pilot.md).

1. **`DEPLOYAI_DIGEST_SOURCE=cp`** — `/digest` loads top items from `GET /internal/v1/strategist/pilot-surfaces/morning-digest-top` (tenant query param). Populate **`DEPLOYAI_PILOT_SURFACE_DATA_PATH`** on the control plane with JSON (see [`examples/pilot-surface.example.json`](./examples/pilot-surface.example.json)) until canonical query APIs replace it.
2. **`DEPLOYAI_EVIDENCE_SOURCE=cp`** or **`DEPLOYAI_PILOT_TENANT_ID`** matching JWT `tid` (see Epic 16 pilot loaders) — `/evidence/[nodeId]` loads from `GET /internal/v1/strategist/pilot-surfaces/evidence-node/{node_id}?tenant_id=…`. Wrong tenant or unknown node → HTTP **404** from CP; the web app rejects payloads whose `id` does not match the requested path segment (defense in depth). Mock fixtures remain dev-only and are not tenant-isolated.

## Observability and support

1. Correlation — follow [`support-runbook.md`](./support-runbook.md) for auth vs empty data vs CP down.
2. Queue / meeting scope — [`queue-durability-modes.md`](./queue-durability-modes.md), [`meeting-presence-pilot-scope.md`](./meeting-presence-pilot-scope.md).

## Optional test-only keys

Playwright ships a **fixture RSA pair** under `apps/web/tests/e2e/fixtures/` for CI only. Production pilots must use **real** CP keys and rotation policy from [`tenant-provisioning.md`](./tenant-provisioning.md).
