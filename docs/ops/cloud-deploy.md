# Cloud deploy runbook — Fly.io + Cloudflare Access

Status: ready to deploy as of 2026-05-27. v2 build complete on `main`. This
runbook stands alone — you should be able to follow it end-to-end without
spelunking the codebase.

---

## 0. Why this stack

| Concern | Choice | Why |
|---|---|---|
| Compute | Fly.io (`shared-cpu-1x` machines) | Cheap, fast cold starts, internal 6PN DNS lets services talk privately, no VPC config. |
| Postgres | Self-hosted Fly app (`infra/fly/postgres`) | Fly Managed Postgres lacks Apache AGE (Cypher / mig 0042). pgvector IS there, but AGE isn't, and AGE is load-bearing for graph traversal. So we ship our own image. |
| Redis | `fly redis create` (Upstash-backed) | Token-bucket rate-limit counters + session cache. Free tier covers our usage. |
| Auth | Cloudflare Access (free tier, ≤50 users) | Email allowlist + magic-link / OTP IdP. CF injects `CF-Access-Authenticated-User-Email` on every request. App reads it; no separate auth code needed. |
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
fly secrets set \
  DEPLOYAI_INTERNAL_API_KEY="${INTERNAL_KEY}" \
  CONTROL_PLANE_INTERNAL_URL="http://deployai-control-plane.internal:8000" \
  NEXT_PUBLIC_CONTROL_PLANE_URL="https://api.<your-domain>" \
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

## 6. Trust the CF Access header inside the app

By default the web app and control-plane are agnostic to who is calling.
With Cloudflare Access in front, every request carries
`CF-Access-Authenticated-User-Email: <email>`.

**TODO before customers can log in** — this is the one piece of code we
haven't written yet:

> Add Next.js middleware in `apps/web/src/middleware.ts` that:
> 1. Reads `CF-Access-Authenticated-User-Email` from the request
> 2. If missing in production → 401 (defense-in-depth in case Access is bypassed)
> 3. Sets it as a server-only header `X-DeployAI-Actor-Email` for the BFF
>    to forward to the control-plane.
>
> Add CP middleware in
> `services/control-plane/src/control_plane/api/middleware/cf_access_auth.py` that:
> 1. Reads `X-DeployAI-Actor-Email`
> 2. Looks up or creates an `app_user` for that email under the
>    operator's tenant (single-tenant deploy for v2)
> 3. Sets `request.state.actor_id` so downstream routes use it
> 4. Marks `request.state.is_admin = email in DEPLOYAI_ADMIN_EMAILS.split(",")`
>
> Both middlewares are < 50 lines each. Ship them as a follow-up PR; the
> rest of the deploy works without them (you just won't have multi-user
> identity — every request gets the bootstrap user).

For now, deploy without that middleware to verify the rest of the stack
works, then add it.

---

## 7. Seed the first tenant

`make seed-app` from the repo root won't work against Fly Postgres
because it talks to localhost. Instead:

```bash
# Open a shell on the control-plane machine
fly ssh console --app deployai-control-plane

# Inside the container:
python -m control_plane.cli.init \
  --tenant-name "<your org>" \
  --user-email <your email> \
  --engagement-name "First engagement"
```

Or use the `/onboarding` wizard the first time you load
`https://app.<your-domain>` — Sprint 1's first-run wizard handles this
when the DB is empty.

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
