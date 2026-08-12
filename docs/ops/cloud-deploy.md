# Cloud deploy runbook — Fly.io

Status: ready to deploy as of 2026-08-11 (auth: OIDC, see §6; the earlier
Cloudflare Access plan was dropped in Wave 1 ticket A1). This
runbook stands alone — you should be able to follow it end-to-end without
spelunking the codebase.

> **WARNING — hosted deploys must use real identity (§6).** Do not set
> `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` (or `DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION`)
> on a hosted deploy: since Wave 1 (ticket A2) role injection is a local-dev-only,
> opt-in escape hatch and refuses to activate on production builds unless both
> flags are set — setting them on a public URL grants a role to **every request**.
> `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` defaults ON; leave it unset in production.

---

## 0. Why this stack

| Concern | Choice | Why |
|---|---|---|
| Compute | Fly.io (`shared-cpu-1x` machines) | Cheap, fast cold starts, internal 6PN DNS lets services talk privately, no VPC config. |
| Postgres | Self-hosted Fly app (`infra/fly/postgres`) | Fly Managed Postgres lacks Apache AGE (Cypher / mig 0042). pgvector IS there, but AGE isn't, and AGE is load-bearing for graph traversal. So we ship our own image. |
| Redis | `fly redis create` (Upstash-backed) | Token-bucket rate-limit counters + session cache. Free tier covers our usage. |
| Auth | **NOT YET IMPLEMENTED** (planned: Cloudflare Access, free tier ≤50 users) | CF Access would inject `CF-Access-Authenticated-User-Email` on every request, but the app-side code that reads that header does not exist yet (§6, backlog ticket A1). Today the app has no real login. |
| Admin/viewer split | `DEPLOYAI_ADMIN_EMAILS` env var on control-plane | Comma-separated list; CF-verified email compared against it. Everyone else gets viewer. |
| Object storage | MinIO container OR Cloudflare R2 | Free for our volume. Wire later if you turn on the S3 backup path. |
| TSA | freetsa-stub container (compose has one) | Free time-stamping for ledger chain notarisation. Wire optional. |

Total cost at minimum: **~$0/mo** if you stay on Fly free machines + CF Access free tier + Voyage free tier. Realistic with traffic: **~$15-30/mo** (Postgres machine + Redis paid tier + Voyage usage).

---

## 1. Prereqs

```bash
# Install Fly CLI
brew install flyctl                  # macOS
# or: curl -L https://fly.io/install.sh | sh

fly auth signup                      # creates account
fly auth login                       # browser-based

# Verify
fly orgs list
```

You need:

- A Cloudflare account (free).
- A domain you control (recommend; not strictly required — Fly gives you
  `*.fly.dev` hostnames for free, but Cloudflare Access wants a domain
  proxied through Cloudflare DNS).
- An Anthropic API key (Claude).
- (Optional) A Voyage AI key for embeddings — without it the embedder
  worker writes zero-vectors and `vector_search` becomes a no-op
  fallback.
- (Optional) Slack OAuth client id/secret if you want Kenny to call Slack
  outbound. Skip if not used; the rest of the MCP outbound surface
  (kill-switch / rate-limit / Linear / GDrive / etc) still works,
  Slack-OAuth specifically returns 503 until wired.

---

## 2. Create the Fly apps

Run each from the repo root. Order matters — Postgres has to exist before
control-plane runs migrations.

```bash
# Postgres (self-hosted; AGE + pgvector)
fly apps create deployai-postgres --org personal
fly volumes create deployai_pg_data --app deployai-postgres --region iad --size 10
fly secrets set POSTGRES_PASSWORD="$(openssl rand -hex 24)" --app deployai-postgres

# Redis (Fly's Upstash-backed offering)
fly redis create --name deployai-redis --org personal --region iad
# Save the redis:// URL it prints; you'll need it as REDIS_URL below.

# App slots (not yet deployed — just claim the names)
fly apps create deployai-control-plane --org personal
fly apps create deployai-web           --org personal
fly apps create deployai-mcp-server    --org personal
fly apps create deployai-embedder      --org personal
```

---

## 3. Set secrets

Generate one shared internal API key — it's the bearer the BFF and the
MCP server use to call the control-plane.

```bash
INTERNAL_KEY="$(openssl rand -hex 32)"
PG_PASS="$(fly secrets list --app deployai-postgres -j | jq -r '.[] | select(.Name=="POSTGRES_PASSWORD") | .Value')"
# (fly doesn't actually expose the value; capture it from step 2's openssl output)

# Control plane
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://deployai:${PG_PASS}@deployai-postgres.internal:5432/deployai" \
  REDIS_URL="<paste the redis URL from step 2>" \
  DEPLOYAI_INTERNAL_API_KEY="${INTERNAL_KEY}" \
  ANTHROPIC_API_KEY="<your Claude key>" \
  VOYAGE_API_KEY="<your Voyage key, or skip>" \
  DEPLOYAI_ADMIN_EMAILS="you@example.com,cofounder@example.com" \
  --app deployai-control-plane

# Web BFF
#
# `DEPLOYAI_CONTROL_PLANE_URL` (NOT `CONTROL_PLANE_INTERNAL_URL`) is what
# apps/web/src/lib/internal/control-plane.ts reads. Setting the wrong name
# causes Kenny chat + every BFF→CP call to fail with "service unreachable".
#
# Do NOT set DEPLOYAI_LOCAL_DEV_ROLE_INJECT on a hosted deploy. Since Wave 1
# (ticket A2) role injection is opt-in and additionally refuses to activate on
# production builds unless DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION=1 is set;
# both flags are local-dev-only escape hatches. Hosted identity must come from
# the CP-issued access JWT / SSO proxy headers (ticket A1). Note also that
# DEPLOYAI_STRATEGIST_REQUIRE_TENANT now defaults ON: requests without a
# tenant (JWT `tid` or `x-deployai-tenant`) are rejected on gated paths.
fly secrets set \
  DEPLOYAI_INTERNAL_API_KEY="${INTERNAL_KEY}" \
  DEPLOYAI_CONTROL_PLANE_URL="http://deployai-control-plane.internal:8000" \
  NEXT_PUBLIC_CONTROL_PLANE_URL="https://deployai-control-plane.fly.dev" \
  --app deployai-web

# MCP inbound server (public)
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://deployai:${PG_PASS}@deployai-postgres.internal:5432/deployai" \
  DEPLOYAI_INTERNAL_API_KEY="${INTERNAL_KEY}" \
  --app deployai-mcp-server

# Embedder worker
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://deployai:${PG_PASS}@deployai-postgres.internal:5432/deployai" \
  VOYAGE_API_KEY="<your Voyage key>" \
  --app deployai-embedder
```

**Slack outbound** (optional, for tenant-admin MCP outbound to Slack):

```bash
fly secrets set \
  DEPLOYAI_SLACK_CLIENT_ID="<from Slack app config>" \
  DEPLOYAI_SLACK_CLIENT_SECRET="<from Slack app config>" \
  DEPLOYAI_SLACK_REDIRECT_URI="https://<your-domain>/api/internal/v1/tenants/{tenant_id}/mcp_configs/{config_id}/oauth/callback" \
  --app deployai-control-plane
```

---

## 3.1 (Recommended) Wire CI auto-deploy on every `main` push

`.github/workflows/cloud-deploy.yml` ships with this repo. Once you set
one repo secret it auto-deploys every push to `main` and writes the
URLs to GitHub's Environments UI (sidebar + commit-level
"View deployment" links).

```bash
# On your laptop, get a long-lived Fly token:
fly auth token

# Then in the GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
# Name: FLY_API_TOKEN
# Value: <paste the token>
```

That's it. The next push to `main` triggers the workflow. Order is
enforced (postgres → control-plane → web / mcp-server / embedder in
parallel). The Postgres job is no-op after the first run if nothing
changed in `infra/compose/postgres/`.

You can still deploy manually anytime via `scripts/cloud-deploy.sh` or
trigger a one-shot from the Actions tab (`workflow_dispatch`).

---

## 4. First deploy (in order)

```bash
# 1) Postgres — has to exist before migrations
fly deploy --config infra/fly/postgres/fly.toml --remote-only

# 2) Control plane — `release_command: alembic upgrade head` runs all migrations
fly deploy --config infra/fly/control-plane/fly.toml --remote-only

# 3) Embedder — depends on the schema being there
fly deploy --config infra/fly/embedder/fly.toml --remote-only

# 4) MCP server — depends on the schema
fly deploy --config infra/fly/mcp-server/fly.toml --remote-only

# 5) Web — last, since it depends on CP being reachable
fly deploy --config infra/fly/web/fly.toml --remote-only
```

After each, watch the logs:

```bash
fly logs --app deployai-control-plane
```

Press Ctrl-C once you see `Application startup complete` on the CP and
`embedder: idle, 0 queued` on the embedder.

---

## 5. Wire Cloudflare Access

The web app is public on `https://deployai-web.fly.dev`. You want
Cloudflare in front of it so only allowlisted emails can reach it.

### 5.1 Point Cloudflare DNS at Fly

In Cloudflare DNS:

- Add a CNAME `app` → `deployai-web.fly.dev` (proxied, orange cloud ON)
- Add a CNAME `api` → `deployai-control-plane.fly.dev` (proxied)
- Add a CNAME `mcp` → `deployai-mcp-server.fly.dev` (proxied, but ZTrust DISABLED — see §5.3)

In Fly, attach the domains:

```bash
fly certs add app.<your-domain> --app deployai-web
fly certs add api.<your-domain> --app deployai-control-plane
fly certs add mcp.<your-domain> --app deployai-mcp-server
```

Wait ~1-2 minutes for certs to issue.

### 5.2 Create the Cloudflare Access application

In the Cloudflare dashboard:

1. **Zero Trust → Access → Applications → Add an application → Self-hosted**.
2. **Name**: DeployAI Web
3. **Subdomain**: `app`, **domain**: `<your-domain>`
4. **Session duration**: 24h
5. **Identity providers**: enable One-Time PIN (email-based; free)
6. **Policies → Add a policy**:
   - Name: "Allowlist"
   - Action: Allow
   - Rule: Emails — paste the same list as `DEPLOYAI_ADMIN_EMAILS` + any
     viewer-only emails
7. **Save**.

Now visiting `https://app.<your-domain>` shows the Cloudflare email prompt
first; only allowed addresses get through to the Fly web app.

Cloudflare also injects `CF-Access-Authenticated-User-Email` on every
request. The app reads it as the authenticated identity.

**Repeat for `api.<your-domain>`** — control-plane SSE endpoint. Same
policy. The web app talks to `api.<your-domain>` from the browser via
SSE; that browser request inherits the user's CF Access session.

### 5.3 Do NOT put `mcp.<your-domain>` behind Access

The MCP inbound server accepts third-party clients (Claude Desktop,
custom agents) that auth with a bearer token minted from the CP. They
don't carry a CF Access session. Leave Cloudflare proxying (orange
cloud) for DDoS protection but **do not add an Access application** for
this hostname.

---

## 6. Authentication: OIDC login (implemented — ticket A1)

> Decision (2026-08-11 pilot-refresh backlog): **OIDC is the auth path.**
> The earlier Cloudflare-Access-header plan described in previous versions
> of this section is dropped — CF Access remains optional as an extra wall
> in front (§5) but the app no longer plans to read its header.

### 6.1 How the flow works

1. Browser hits `GET /api/auth/login` on the **web app**. The route
   generates state + nonce + PKCE (S256), stores them in short-lived
   HttpOnly cookies (`dep_oidc_state` / `dep_oidc_verifier` /
   `dep_oidc_nonce`, 10 min), and 302s to the issuer's authorize endpoint
   (discovered via `{issuer}/.well-known/openid-configuration`).
2. The IdP redirects back to `GET /api/auth/callback/oidc` (web app).
   The route validates `state` against the cookie, then calls the
   **control plane's** `GET /auth/oidc/callback` server-side, forwarding
   the three transient cookies. The CP does the sensitive half: code
   exchange with the client secret, JWKS verification of the ID token
   (iss / aud / exp signature) + nonce check, JIT user provisioning, and
   session minting (RS256 access JWT + opaque refresh JTI in Redis).
3. The web route stores the CP-minted session in HttpOnly, SameSite=Lax,
   Path=/ cookies (Secure when the redirect URI is https):
   `deployai_access_token` (the RS256 JWT the existing middleware already
   verifies via `apps/web/src/lib/internal/deployai-access-jwt.ts`),
   `deployai_refresh_token`, and `deployai_session_tenant`, then 303s to
   `/engagements`.
4. `GET|POST /api/auth/logout` best-effort revokes the CP refresh session
   (`POST {CP}/auth/logout` with `{tenant_id, refresh_token}`), clears
   all three cookies, and redirects to `/login`.

Access JWT claims (minted by CP `create_access_token`, verified by web
middleware): `sub` (user id), `tid` (tenant id — this is where
multi-tenancy comes from; the tenant is read from the CP user record),
`roles` (array), `iss`, `aud`, `iat`, `exp`, `jti`, `token_use: "access"`.

JIT provisioning: first login upserts an `app_users` row keyed by the
OIDC `sub` onto the system SSO-pending tenant with the least-privilege
`pending_assignment` role (NOT admin). An admin must then assign the
tenant + real role. Set `DEPLOYAI_OIDC_JIT_ENABLED=0` to reject unknown
users with 403 instead.

Failure paths: state mismatch → 400; issuer unreachable → redirect to
`/login?error=issuer_unreachable`; CP unreachable → redirect to
`/login?error=control_plane_unreachable`; unknown user with JIT disabled
→ 403.

### 6.2 Required env vars

Control plane (`services/control-plane`):

| Var | Value |
|---|---|
| `DEPLOYAI_OIDC_ISSUER` | e.g. `https://login.microsoftonline.com/<tenant-id>/v2.0` (must serve `openid-configuration`) |
| `DEPLOYAI_OIDC_CLIENT_ID` | App registration client id |
| `DEPLOYAI_OIDC_CLIENT_SECRET` | Client secret — **CP only, never set on the web app** |
| `DEPLOYAI_OIDC_REDIRECT_URI` | The **web app's** callback, e.g. `https://deployai-web.fly.dev/api/auth/callback/oidc` (register this in the IdP) |
| `DEPLOYAI_OIDC_JIT_ENABLED` | Optional; default on. `0` = reject unknown users (403) |
| `DEPLOYAI_JWT_PRIVATE_KEY_PATH` | RS256 signing key for session JWTs |
| `DEPLOYAI_REDIS_URL` | Refresh sessions live in Redis |

Web app (`apps/web`):

| Var | Value |
|---|---|
| `DEPLOYAI_OIDC_ISSUER` | Same value as the CP |
| `DEPLOYAI_OIDC_CLIENT_ID` | Same value as the CP |
| `DEPLOYAI_OIDC_REDIRECT_URI` | Same value as the CP (the web callback URL) |
| `DEPLOYAI_CONTROL_PLANE_URL` | Internal CP base URL (server-side calls) |
| `DEPLOYAI_WEB_TRUST_JWT` | `1` — middleware verifies the session JWT |
| `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` | SPKI public PEM(s) matching the CP signing key (concatenate blocks for rotation) |
| `DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE` | Optional; default `deployai_access_token` |
| `DEPLOYAI_WEB_REFRESH_TOKEN_COOKIE` | Optional; default `deployai_refresh_token` |
| `DEPLOYAI_WEB_SESSION_TENANT_COOKIE` | Optional; default `deployai_session_tenant` |
| `DEPLOYAI_WEB_REFRESH_COOKIE_MAX_AGE` | Optional; default 604800 (7 d, matches CP refresh TTL) |
| `DEPLOYAI_OIDC_POST_LOGIN_PATH` | Optional; default `/engagements` |

Make sure `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` is **unset** on hosted
deploys — it bypasses this whole flow (see §3 warning).

### 6.3 Smoke test

```bash
# 1. Unauthenticated app surface should 401/403 (middleware, not a stub):
curl -si https://deployai-web.fly.dev/engagements | head -1
# 2. Login entry point should 302 to the IdP authorize endpoint:
curl -si https://deployai-web.fly.dev/api/auth/login | grep -i '^location'
# 3. Full browser round-trip: visit /login, click "Sign in with SSO",
#    authenticate at the IdP, land on /engagements.
```

First login lands the user on the SSO-pending tenant with
`pending_assignment` — assign the real tenant + role on the `app_users`
row (SCIM or SQL) before they can see engagement surfaces.

---

## 7. Seed the first tenant

**Why this matters:** in local dev the role-inject middleware uses tenant id
`11111111-1111-1111-1111-111111111111` as the default actor tenant (compose
sets `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1`; hosted deploys must not — see the
warning at the top of this runbook). That tenant row must exist in
`app_tenants` or every BFF → CP call 404s ("That queue item was not found").
Onboarding wizard's `/api/bff/tenant/llm-config` probe needs it too.

**Path A — direct SQL (fastest, ~5s):**

```bash
fly ssh console --app deployai-postgres -C \
  "psql -U deployai -d deployai -c \"INSERT INTO app_tenants (id, name) VALUES ('11111111-1111-1111-1111-111111111111', 'dev') ON CONFLICT DO NOTHING;\""
```

**Path B — BlueState seed via the onboarding wizard's button:**

Visit `https://deployai-web.fly.dev/onboarding`, click
**Load BlueState demo (26-week scenario)**. Creates the tenant + 1
engagement + ~7 stakeholders + 20 decisions + 13 risks + 182 snapshots
in ~10s. Good for first-time demos.

**Path C — host-side script against the cloud CP:**

```bash
DEPLOYAI_CP_BASE_URL=https://deployai-control-plane.fly.dev \
DEPLOYAI_INTERNAL_API_KEY=<your-key> \
python3 infra/compose/seed/seed_app.py
```

Requires the same `INTERNAL_API_KEY` you set on the CP. Use this when
you want the synthetic `Acme County` engagement instead of BlueState.

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
curl https://api.<your-domain>/health
# → {"status":"ok","service":"control-plane","version":"..."}

curl https://mcp.<your-domain>/health
# → {"status":"ok","service":"mcp-server","version":"..."}

# Web is behind CF Access; you have to log in via the browser first.
# After that:
curl -H "Cookie: CF_Authorization=<your session cookie>" https://app.<your-domain>/api/health
```

Then in the browser:

1. https://app.<your-domain> → CF email prompt → enter your email →
   get OTP → enter OTP → land on `/engagements`
2. Click an engagement → ask Agent Kenny a question → streamed reply
   with citations
3. http://app.<your-domain>/admin/agent-kenny-dashboard → telemetry
   panel renders

---

## 9. Day-2 operations

| Task | Command |
|---|---|
| Logs | `fly logs --app deployai-control-plane` |
| Open shell | `fly ssh console --app deployai-control-plane` |
| Scale up | `fly scale count 2 --app deployai-control-plane` |
| Restart | `fly machine restart --app deployai-control-plane` |
| psql into DB | `fly ssh console --app deployai-postgres -C "psql -U deployai deployai"` |
| Manual migrate | `fly ssh console --app deployai-control-plane -C "alembic upgrade head"` |
| Rotate internal key | `fly secrets set DEPLOYAI_INTERNAL_API_KEY=$(openssl rand -hex 32) --app deployai-control-plane --app deployai-web --app deployai-mcp-server` then redeploy each |

---

## 10. Cost & quota notes

- Fly free tier: 3 × shared-1x machines free. We have 5 services (postgres, control-plane, web, mcp-server, embedder) → ~2-3 paid at $1.94/mo each + Postgres volume $0.15/GB/mo.
- Cloudflare Access free tier: ≤ 50 users (covers any pilot easily).
- Cloudflare DNS / proxy: free at unlimited traffic.
- Anthropic: pay-as-you-go (Claude Opus ~$15/$75 per Mtok in/out).
- Voyage AI: 50M free tokens at signup; then $0.10 per M.
- Postgres backups (S3): zero if you stay under S3 free tier; ~$0.02/GB/mo otherwise.

Minimum realistic cost for a single-user pilot: **~$5/mo** + LLM usage. For a 10-user pilot with regular traffic: **~$30-50/mo** + LLM.

---

## 11. Tear-down

```bash
fly apps destroy deployai-postgres   --yes
fly apps destroy deployai-control-plane --yes
fly apps destroy deployai-web        --yes
fly apps destroy deployai-mcp-server --yes
fly apps destroy deployai-embedder   --yes
fly redis destroy deployai-redis     --yes
fly volumes destroy <volume-id>      --yes  # the Postgres data volume
```

Cloudflare Access applications are deleted from the Zero Trust dashboard.

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `release_command failed: alembic.util.exc.CommandError: Multiple head revisions` | Migration order drift after concurrent PRs | Fix on `main` first (see git log around `fix/alembic-0048-relink`), then redeploy |
| CP healthcheck flaps | DB connection refused on first boot | `release_command` runs `alembic upgrade head` before serving; if DB is brand-new, increase `grace_period` to 60s |
| MCP server returns 401 to a known good token | Internal API key mismatch | Re-run `fly secrets set DEPLOYAI_INTERNAL_API_KEY` with the same value on both `deployai-mcp-server` and `deployai-control-plane`, then redeploy both |
| Cloudflare Access returns 1101 / 1102 | DNS not proxied (orange cloud off) | Toggle the cloud icon orange in CF dashboard → DNS |
| Embedder never drains the queue | `VOYAGE_API_KEY` not set → zero-vec path | `fly secrets set VOYAGE_API_KEY=...` then `fly machine restart --app deployai-embedder` |
| Agent Kenny says "I don't know" to every question | DB is empty / nothing seeded | Run the init script in §7 |
| Bulk-accept proposals fails with "batch too large" | > 500 IDs in one request | Split into 500-id chunks (the UI button does this for you) |
