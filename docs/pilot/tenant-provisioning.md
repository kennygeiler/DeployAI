# Tenant provisioning (pilot repeatability)

Goal: every pilot starts from a **known** tenant UUID and strategist role, without one-off engineer hacks.

## 1. Control plane + database

1. Run CP with Postgres (see [`../dev-environment.md`](../dev-environment.md) §docker-compose or your staging chart).
2. Apply migrations: `uv run alembic upgrade head` (from `services/control-plane`).

## 2. Synthetic tenant (local reference)

Docker Compose / Story 1.7 stack seeds a **synthetic tenant** and fixture events—use that UUID for local strategist testing when documented in your compose README.

## 3. Test session tokens (internal only)

**Route:** `POST /test/session-tokens` on the control plane (see [`internal_session.py`](../../services/control-plane/src/control_plane/api/routes/internal_session.py)).

- Guarded by **`X-DeployAI-Internal-Key`** (same as other internal routes).
- Disabled unless **`DEPLOYAI_ALLOW_TEST_SESSION_MINT=1`** on CP.

**Body (JSON):** `tenant_id`, `user_id` (UUIDs), `roles` (non-empty list, e.g. `["deployment_strategist"]`).

**Response:** `access_token`, `refresh_token`, `expires_in` — use for **API** tests against CP. The Next.js app does not yet consume these cookies end-to-end for strategists; for **web** pilot, use a **trusted proxy** that maps IdP identity → `x-deployai-role` + `x-deployai-tenant` (see [session-and-headers.md](./session-and-headers.md)).

## 4. Web app headers for strategist surfaces

For server-side `loadStrategistActivityForActor` and ingestion scoping, the browser (or proxy) must send:

- `x-deployai-role: deployment_strategist` (or allowed role)
- `x-deployai-tenant: <same UUID CP uses for that customer>`

Meeting-presence stub tenants: set **`DEPLOYAI_STUB_IN_MEETING_TENANT_IDS`** on CP (comma-separated UUIDs) if you need deterministic “in meeting” for demos—documented in dev-environment.

## 5. Checklist before external visitor

- [ ] Tenant UUID recorded in runbook
- [ ] Strategist user ↔ tenant ↔ role verified
- [ ] `DEPLOYAI_CONTROL_PLANE_URL` + internal key on web match CP deployment
- [ ] `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1` in staging if using header-based pilot
