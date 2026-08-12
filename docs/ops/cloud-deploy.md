# Cloud deploy runbook — Railway

Status: live as of 2026-08-11. The stack described here is stood up in the
Railway project **`deployai`** ("Kenny's Projects" workspace). This runbook
stands alone — you should be able to follow it end-to-end without spelunking
the codebase. The Fly.io predecessor is archived at
[`docs/archive/cloud-deploy-fly.md`](../archive/cloud-deploy-fly.md).

> **WARNING — hosted deploys must use real identity.** Do not set
> `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` (or `DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION`)
> on a hosted deploy: role injection is a local-dev-only, opt-in escape hatch —
> setting it on a public URL grants a role to **every request**.
> `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` defaults ON; leave it unset in production.
>
> **The current hosted auth path is a bootstrap shim (§7), not real login.**
> CP-minted 15-minute JWTs via `scripts/cloud-token.sh` are for operator
> access while standing the stack up. **Wire real OIDC (§7.3) before any
> pilot user touches the deployment.**

---

## 0. Why this stack

| Concern | Choice | Why |
|---|---|---|
| Compute | Railway (usage-based) | No per-app minimums, one project holds all services, private networking with zero config, Dockerfile-native builds from the monorepo root. Simpler service model than the Fly setup it replaced (no `fly.toml` per service, no release-command machinery). |
| Postgres | Self-built service (`infra/compose/postgres/Dockerfile`) | Managed Postgres offerings lack Apache AGE (Cypher / mig 0042). pgvector is common, AGE isn't, and AGE is load-bearing for graph traversal — so we ship our own image on a Railway volume. |
| Redis | Railway managed Redis | Token-bucket rate-limit counters + refresh-session cache. Comes with its own volume. |
| Migrations | `RUN_MIGRATIONS=1` on the control-plane service | Railway has no release commands, so `services/control-plane/docker-entrypoint.sh` runs `alembic upgrade head` on boot (swapping `+asyncpg` → `+psycopg` for the migration run only). |
| Embedder | Same CP image, `SERVICE_ROLE=embedder` | Railway has no process groups; the entrypoint dispatches on `SERVICE_ROLE`. |
| Auth | Bootstrap JWT shim today; **OIDC before pilot** (§7) | The CP mints short-lived RS256 session JWTs; the web app verifies them. Real OIDC login is a pre-pilot task. |

Cost: usage-based. This stack idles around **~$5–15/mo** (five small services
+ two volumes) plus LLM usage. See §10.

---

## 1. Prereqs

```bash
# Install the Railway CLI
brew install railway                 # macOS
# or: npm i -g @railway/cli

railway login                        # browser-based

# Verify
railway whoami
```

You need:

- A Railway account **with a payment method attached** (usage-based billing;
  the free trial tier is not enough to run five services + volumes).
- An Anthropic API key (Claude).
- (Optional) A Voyage AI key for embeddings — without it the embedder worker
  writes zero-vectors and `vector_search` becomes a no-op fallback.
- (Optional) Slack OAuth client id/secret for Kenny's outbound Slack calls.

---

## 2. Create the project + services

`scripts/cloud-standup.sh` automates this whole section idempotently (it
also generates and remembers the secrets in `~/.deployai-railway-state`).
The manual sequence, from the repo root:

```bash
railway init --name deployai         # creates the project; links this dir
railway add --database redis         # managed Redis (own volume)

# Empty services — one per deployable
railway add --service postgres
railway add --service control-plane
railway add --service web
railway add --service mcp-server
railway add --service embedder

# Persistent volume for Postgres data
railway volume add --service postgres --mount-path /var/lib/postgresql/data
```

Every service builds **from the repo root** (the CLI tarballs the working
tree, honoring `.gitignore`); `RAILWAY_DOCKERFILE_PATH` selects the
Dockerfile per service:

| Service | `RAILWAY_DOCKERFILE_PATH` | Notes |
|---|---|---|
| `postgres` | `infra/compose/postgres/Dockerfile` | Postgres 16 + pgvector + Apache AGE. The image's entrypoint shim chowns `$PGDATA` under the root-owned volume mount. |
| `control-plane` | `services/control-plane/Dockerfile` | `SERVICE_ROLE=api` (default) + `RUN_MIGRATIONS=1` |
| `web` | `apps/web/Dockerfile` | Next.js web / BFF |
| `mcp-server` | `services/mcp-server/Dockerfile` | Inbound read-only MCP |
| `embedder` | `services/control-plane/Dockerfile` | Same image as CP, `SERVICE_ROLE=embedder` |

---

## 3. Set variables

Names only below — generate/paste values yourself; never commit them.
Set with:

```bash
railway variables --service <service> --set "NAME=value"
```

Generate once and reuse across services:

```bash
INTERNAL_KEY="$(openssl rand -hex 32)"      # BFF/MCP → CP bearer
PG_PASS="$(openssl rand -hex 24)"           # Postgres superuser password
# RS256 session-JWT keypair (CP signs, web verifies):
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt-private.pem
openssl pkey -in jwt-private.pem -pubout -out jwt-public.pem
```

Railway variable **references** let one service read another's values, e.g.
`${{Redis.REDISPASSWORD}}` resolves to the managed Redis password. The
private-network hostname pattern is `<service>.railway.internal`.

### postgres

| Var | Value shape |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `infra/compose/postgres/Dockerfile` |
| `POSTGRES_USER` | `deployai` |
| `POSTGRES_PASSWORD` | the generated `PG_PASS` |
| `POSTGRES_DB` | `deployai` |
| `PGDATA` | `/var/lib/postgresql/data/pgdata` — subdirectory, because Railway volume roots are non-empty and `initdb` refuses them |

### control-plane

| Var | Value shape |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `services/control-plane/Dockerfile` |
| `RUN_MIGRATIONS` | `1` — entrypoint runs `alembic upgrade head` on boot |
| `DATABASE_URL` | `postgresql+asyncpg://deployai:<PG_PASS>@postgres.railway.internal:5432/deployai` |
| `REDIS_URL` | `redis://default:${{Redis.REDISPASSWORD}}@redis.railway.internal:6379/0` |
| `DEPLOYAI_REDIS_URL` | same as `REDIS_URL` (refresh sessions live in Redis) |
| `DEPLOYAI_INTERNAL_API_KEY` | the generated `INTERNAL_KEY` |
| `ANTHROPIC_API_KEY` | your Claude key |
| `VOYAGE_API_KEY` | optional; embeddings |
| `DEPLOYAI_ADMIN_EMAILS` | comma-separated admin emails |
| `DEPLOYAI_JWT_PRIVATE_KEY_B64` | `base64 < jwt-private.pem` — the entrypoint materializes it to a file (Railway has no file-mount secrets) and sets `DEPLOYAI_JWT_PRIVATE_KEY_PATH` |
| `DEPLOYAI_ALLOW_TEST_SESSION_MINT` | `1` **bootstrap only** — enables §7's token mint; unset it once OIDC is live |

### web

| Var | Value shape |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `apps/web/Dockerfile` |
| `DEPLOYAI_INTERNAL_API_KEY` | same `INTERNAL_KEY` |
| `DEPLOYAI_CONTROL_PLANE_URL` | `http://control-plane.railway.internal:8000` — this exact name; `apps/web/src/lib/internal/control-plane.ts` reads it |
| `NEXT_PUBLIC_CONTROL_PLANE_URL` | the CP **public** domain (§5) |
| `DEPLOYAI_WEB_TRUST_JWT` | `1` — middleware verifies CP-minted session JWTs |
| `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` | contents of `jwt-public.pem` (SPKI; concatenate blocks for rotation) |

### mcp-server

| Var | Value shape |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `services/mcp-server/Dockerfile` |
| `DATABASE_URL` | same shape as control-plane's |
| `DEPLOYAI_INTERNAL_API_KEY` | same `INTERNAL_KEY` |

### embedder

| Var | Value shape |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `services/control-plane/Dockerfile` |
| `SERVICE_ROLE` | `embedder` — entrypoint dispatch; no migrations, no HTTP |
| `DATABASE_URL` | same shape as control-plane's |
| `VOYAGE_API_KEY` | embeddings key |

**Slack outbound** (optional, on control-plane): `DEPLOYAI_SLACK_CLIENT_ID`,
`DEPLOYAI_SLACK_CLIENT_SECRET`, `DEPLOYAI_SLACK_REDIRECT_URI`.

---

## 4. First deploy (in order)

Postgres must be up before the control-plane boots (its entrypoint runs
migrations); everything else depends on the CP schema. From the repo root:

```bash
railway up --service postgres      --detach
railway up --service control-plane --detach   # alembic upgrade head on boot
railway up --service embedder      --detach
railway up --service mcp-server    --detach
railway up --service web           --detach
```

`scripts/cloud-deploy.sh` wraps exactly this sequence. Watch each boot:

```bash
railway logs --service control-plane
```

Look for `entrypoint: running alembic upgrade head` followed by
`Application startup complete` on the CP, and the idle poll line on the
embedder.

---

## 5. Domains

Private networking needs no setup: services reach each other at
`<service>.railway.internal` (web → CP at
`http://control-plane.railway.internal:8000`; DB/Redis same pattern —
Postgres, Redis, and the embedder have **no public ingress**).

Public domains (Settings → Networking → Generate Domain, or
`railway domain --service <name>`) — the stood-up project's domains:

| Service | Public URL |
|---|---|
| web | `https://web-production-e4059.up.railway.app` |
| control-plane | `https://control-plane-production-798e.up.railway.app` |
| mcp-server | `https://mcp-server-production-d7af.up.railway.app` |

The CP is public because the browser talks to it directly for SSE streaming
(`NEXT_PUBLIC_CONTROL_PLANE_URL`) and because seeding (§6) and the token
mint (§7) hit it from the operator's laptop. The MCP server is public for
third-party MCP clients (Claude Desktop) that auth with CP-minted bearer
tokens. Custom domains attach in the same Settings → Networking panel.

---

## 6. Seed the first tenant

The default local-dev tenant id is `11111111-1111-1111-1111-111111111111`;
some flows 404 until a tenant row exists.

**Path A — psql via the CLI:**

```bash
railway connect postgres
# then, at the psql prompt:
INSERT INTO app_tenants (id, name)
VALUES ('11111111-1111-1111-1111-111111111111', 'dev')
ON CONFLICT DO NOTHING;
```

**Path B — BlueState seed via the onboarding wizard:** visit
`https://web-production-e4059.up.railway.app/onboarding` (needs a session —
§7), click **Load BlueState demo (26-week scenario)**.

**Path C — host-side seed script against the public CP URL** (auths with
the internal key as the `X-DeployAI-Internal-Key` bearer):

```bash
DEPLOYAI_CP_BASE_URL=https://control-plane-production-798e.up.railway.app \
DEPLOYAI_INTERNAL_API_KEY=<your INTERNAL_KEY> \
python3 infra/compose/seed/seed_app.py
```

A quick way to prove internal-key auth works end-to-end is the token mint
in §7 (`scripts/cloud-token.sh`) — it hits an internal-key-gated CP route
and fails loudly on a key mismatch.

---

## 7. Bootstrap access (and the OIDC warning)

### 7.1 How it works today

With `DEPLOYAI_ALLOW_TEST_SESSION_MINT=1` on the CP, the internal-key-gated
endpoint `POST /internal/v1/test/session-tokens` mints a real RS256 session
JWT (15-minute access token + refresh JTI). The web app trusts it because
`DEPLOYAI_WEB_TRUST_JWT=1` + `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` let the
middleware verify the signature.

```bash
# Defaults to the Railway CP domain; prints an access token + cookie recipe.
DEPLOYAI_INTERNAL_API_KEY=<your INTERNAL_KEY> ./scripts/cloud-token.sh
```

Set the printed token as the `deployai_access_token` cookie on the web
domain (browser devtools → Application → Cookies), then load `/engagements`.
Re-run the script when the 15 minutes are up.

### 7.2 Why this is acceptable *only* for bootstrap

The mint endpoint is gated on the internal API key and disabled unless the
env flag is set — but it is password-equivalent access with no user
identity, no MFA, and no audit trail per human. It exists so the operator
can verify the deployment end-to-end before login exists.

### 7.3 Before any pilot user: real OIDC

**Pre-pilot blocker.** Wire the OIDC flow (backlog ticket A1 — the CP
already has the OIDC+PKCE machinery; see the archived Fly runbook §6 for
the flow description and the full env-var table, which is
platform-independent): set `DEPLOYAI_OIDC_ISSUER`, `DEPLOYAI_OIDC_CLIENT_ID`,
`DEPLOYAI_OIDC_CLIENT_SECRET` (CP only), `DEPLOYAI_OIDC_REDIRECT_URI` on
both CP and web, register the redirect URI with the IdP, then **unset
`DEPLOYAI_ALLOW_TEST_SESSION_MINT`**.

### 7.1 Demo mode — zero-friction "View live demo" guest access (Wave 4S)

For showcase deploys (recruiters / founders), the login page can show a
**View live demo** button that logs the visitor straight into a read-only
guest session — no SSO, no tokens to paste.

Four envs, all required:

```bash
# Control plane
fly secrets set --app deployai-control-plane \
  DEPLOYAI_DEMO_GUEST_ENABLED=1 \
  DEPLOYAI_DEMO_TENANT_ID=<uuid of the seeded demo tenant> \
  DEPLOYAI_DEMO_USER_ID=<uuid of a seeded app_users row on that tenant>

# Web (NEXT_PUBLIC_* is baked at build time — set it before/at deploy)
fly secrets set --app deployai-web NEXT_PUBLIC_DEMO_MODE=1
```

Seed the demo tenant first (§7 Path B BlueState is a good demo dataset) and
insert the demo `app_users` row on it; the two UUIDs above must exist.

How it works: `GET /api/auth/demo` (404 unless `NEXT_PUBLIC_DEMO_MODE=1`,
lightly rate-limited per IP) calls the CP's `POST /internal/v1/demo/session`
server-side with the internal key. The CP — only when
`DEPLOYAI_DEMO_GUEST_ENABLED=1` and both IDs are set — mints a standard
short-TTL (15 min) access JWT with the single `demo_guest` role on the demo
tenant, which lands in the normal `deployai_access_token` cookie and the
visitor is redirected to `/engagements`. When the session expires the demo
simply ends; the button mints a fresh one.

Security posture (read before enabling):

- `demo_guest` holds `canonical:read` only (docs/authz/role-matrix.md):
  strategist read surfaces + Oracle chat work; `/admin` and every
  `/api/internal/v1` proxy route (bulk proposal accept, MCP config, Agent
  Kenny dashboard) are denied at the web middleware; the cross-tenant rule
  pins all calls to the demo tenant.
- Known residual risk: BFF mutation routes that gate with `canonical:read`
  today (single proposal accept/reject, review-item resolve/dismiss, insight
  actions, onboarding seeds) remain callable by demo sessions. Accepted for
  wave 1 because the demo tenant is disposable — reseed it whenever it gets
  messy.
- **Turn demo mode OFF (all four envs) on any deployment that hosts customer
  tenants.** The demo tenant shares the database; demo mode is for
  dedicated showcase deploys only.

---

## 8. Smoke checks (cloud edition of `make dev-verify`)

```bash
curl https://control-plane-production-798e.up.railway.app/health
# → {"status":"ok","service":"control-plane","version":"..."}

curl https://mcp-server-production-d7af.up.railway.app/health
# → {"status":"ok","service":"mcp-server","version":"..."}

curl -si https://web-production-e4059.up.railway.app/engagements | head -1
# → 401/403/redirect without a session (middleware, not a stub)
```

Then in the browser, with a bootstrap cookie (§7): open `/engagements`,
ask Agent Kenny a question, confirm a streamed reply with citations, and
check `/admin/agent-kenny-dashboard` renders telemetry.

---

## 9. Day-2 operations

| Task | How |
|---|---|
| Logs | `railway logs --service control-plane` (also per-deploy logs in the dashboard) |
| Redeploy current code | `railway up --service <name> --detach` from the repo root |
| CI auto-deploy | `.github/workflows/cloud-deploy.yml` — `workflow_run` on CI success on `main`; needs the `RAILWAY_TOKEN` repo secret (project token: Railway dashboard → Project Settings → Tokens) |
| Rollback | Dashboard → service → Deployments → previous deployment → ⋮ → Rollback/Redeploy |
| Restart | Dashboard → service → ⋮ → Restart |
| psql | `railway connect postgres` (interactive) |
| Manual migrate | Redeploy control-plane (`RUN_MIGRATIONS=1` runs alembic on boot) or `railway ssh --service control-plane` then `alembic upgrade head` in the container (note: `railway run` executes *locally* and can't reach `*.railway.internal`) |
| Change/rotate a var | `railway variables --service <name> --set "K=V"` — triggers a redeploy of that service |
| Rotate internal key | Set the same new `DEPLOYAI_INTERNAL_API_KEY` on control-plane, web, and mcp-server |
| Backups | Railway volume backups + manual pg_dump — see [`docs/ops/backup.md`](./backup.md) |
| Scale | Dashboard → service → Settings (vertical limits; replicas) — defaults are fine at pilot scale |

---

## 10. Cost notes

Railway is usage-based (per-vCPU-second + per-GB-RAM-second + volume GB).
No per-service minimums, so five mostly-idle services stay cheap:

- This stack idle-ish: **~$5–15/mo** (Postgres and Redis volumes are the
  steady cost; compute scales with traffic).
- Anthropic: pay-as-you-go LLM usage (dominates at any real usage).
- Voyage AI: 50M free tokens at signup; then ~$0.10 per M.

Watch the project's Usage page the first week; set a usage limit alert in
workspace billing settings.

---

## 11. Tear-down

Dashboard: Project Settings → Danger → Delete Project (removes all services,
volumes, and domains). Per-service: service → Settings → Delete Service.
Via CLI there is no bulk destroy; `railway down` removes the latest
deployment of the linked service only. Volumes (and their backups) are
deleted with the project — take a final `pg_dump` first if the data matters
(see [`docs/ops/backup.md`](./backup.md)).

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| CP boot loops with `alembic ... Multiple head revisions` | Migration order drift after concurrent PRs | Fix on `main` first, then redeploy |
| CP can't reach Postgres on first boot | Postgres still initializing (first boot runs initdb + init SQL) | Wait for the postgres deploy to go healthy, then redeploy control-plane |
| Web says "service unreachable" on every page | `DEPLOYAI_CONTROL_PLANE_URL` misnamed or wrong | Must be exactly `DEPLOYAI_CONTROL_PLANE_URL=http://control-plane.railway.internal:8000` |
| MCP server returns 401 to a known-good token | Internal API key mismatch | Set the same `DEPLOYAI_INTERNAL_API_KEY` on mcp-server and control-plane |
| `railway up` deploys the wrong service | Directory linked to another service | Always pass `--service <name>` explicitly |
| Build uses the wrong Dockerfile | `RAILWAY_DOCKERFILE_PATH` unset on the service | Set it per the §2 table |
| Token mint returns 404 | `DEPLOYAI_ALLOW_TEST_SESSION_MINT` unset (correct state post-OIDC) | For bootstrap only: set it to `1` on the CP |
| Embedder never drains the queue | `VOYAGE_API_KEY` not set → zero-vec path | Set it on the embedder service and redeploy |
| Agent Kenny says "I don't know" to everything | Nothing seeded | §6 |
