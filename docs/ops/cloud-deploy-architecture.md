# Cloud deploy architecture

Companion to `cloud-deploy.md`. Diagrams the topology + trust boundaries.

---

## Topology

```
                                  ┌──────────────────────────────────────┐
                                  │  Browser / customer                  │
                                  │  (allowlisted email only)            │
                                  └──────────────┬───────────────────────┘
                                                 │ HTTPS
                                                 ▼
                            ┌────────────────────────────────────────────┐
                            │  Cloudflare DNS + Access (free tier)       │
                            │  - email allowlist → OTP                   │
                            │  - injects CF-Access-Authenticated-User-   │
                            │    Email on every request                  │
                            └──────────────┬─────────────────────────────┘
                                           │ (verified email header)
                                           ▼
            ┌──────────────────────────────────────────────────────────────────┐
            │  Fly.io edge (per-app HTTPS + auto-cert)                         │
            │                                                                  │
            │  app.<domain> ─────► deployai-web        (Next.js 16, SSR + BFF) │
            │  api.<domain> ─────► deployai-control-plane  (FastAPI)           │
            │  mcp.<domain> ─────► deployai-mcp-server (no CF Access)          │
            │                                                                  │
            │  Internal 6PN (private DNS, no public ingress):                  │
            │  deployai-control-plane.internal:8000                            │
            │  deployai-postgres.internal:5432                                 │
            │  (Redis hostname from `fly redis create` output)                 │
            └──────┬──────────────┬──────────────┬────────────────┬───────────┘
                   │              │              │                │
                   ▼              ▼              ▼                ▼
            ┌──────────────────────────────────────────────────────────────┐
            │  Fly apps (all `iad`, shared-1x by default)                  │
            │                                                              │
            │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
            │  │  web         │  │ control-plane│  │ mcp-server       │    │
            │  │  Next.js 16  │  │ FastAPI      │  │ FastAPI (JSON-RPC)│   │
            │  │  port 3000   │  │ port 8000    │  │ port 3030        │    │
            │  └──────────────┘  └──────┬───────┘  └────────┬─────────┘    │
            │                           │                   │              │
            │                           ▼                   ▼              │
            │                  ┌──────────────────────────────────┐        │
            │                  │  embedder (worker; no ingress)   │        │
            │                  │  python -m control_plane.cli.    │        │
            │                  │       embedder                   │        │
            │                  └──────────┬───────────────────────┘        │
            │                             │                                │
            │                             ▼                                │
            │  ┌────────────────────────────────────────────────────────┐  │
            │  │  deployai-postgres                                     │  │
            │  │  Postgres 16 + pgvector + Apache AGE 1.6.0             │  │
            │  │  /var/lib/postgresql/data (10GB Fly volume)            │  │
            │  └────────────────────────────────────────────────────────┘  │
            │                                                              │
            │  ┌────────────────────────────────────────────────────────┐  │
            │  │  deployai-redis (Upstash via Fly)                      │  │
            │  └────────────────────────────────────────────────────────┘  │
            └──────────────────────────────────────────────────────────────┘
                   │                                       │
                   ▼                                       ▼
            ┌──────────────────────────┐    ┌────────────────────────────┐
            │  Anthropic API (Claude)  │    │  Voyage AI API (embeddings)│
            └──────────────────────────┘    └────────────────────────────┘
```

---

## Trust boundaries

Three rings — outside-in:

1. **Public internet** — anyone can attempt a request.
2. **Cloudflare Access perimeter** — only allowlisted emails pass; CF
   injects a verified email header.
3. **Fly 6PN private network** — only siblings in the same org/app can
   resolve `*.internal` DNS names. The internet cannot reach Postgres,
   Redis, or the embedder.

The MCP inbound server sits OUTSIDE ring 2 by design — third-party MCP
clients (Claude Desktop) authenticate with a bearer token minted from
the CP. They don't have a CF Access session.

---

## Where each secret lives

| Secret | Stored on | Who reads it |
|---|---|---|
| `POSTGRES_PASSWORD` | `deployai-postgres` Fly secret | Postgres init only; embedded in CP's `DATABASE_URL` |
| `DATABASE_URL` | `deployai-control-plane`, `deployai-embedder`, `deployai-mcp-server` Fly secrets | Each service's DB driver |
| `DEPLOYAI_INTERNAL_API_KEY` | All app services | BFF → CP, MCP → CP — the bearer for internal-only routes |
| `ANTHROPIC_API_KEY` | `deployai-control-plane` only | Claude calls (extraction, Kenny, adversarial review) |
| `VOYAGE_API_KEY` | `deployai-control-plane`, `deployai-embedder` | Embedding API |
| `DEPLOYAI_SLACK_CLIENT_*` | `deployai-control-plane` only | Slack OAuth start/callback |
| `DEPLOYAI_ADMIN_EMAILS` | `deployai-control-plane` env (not secret) | Admin/viewer split. Comma-separated |
| Tenant OAuth tokens (Slack workspace bearer, etc.) | Postgres `tenant_mcp_configs.encrypted_auth_token` | Encrypted with tenant DEK (`deployai_tenancy.envelope`). Plaintext never leaves `mcp_client.py` |

No secrets in any committed file. Every value comes from `fly secrets`
or Cloudflare configuration.

---

## Outbound network calls — what reaches the public internet

From the cluster's perspective:

| Caller | Destination | Why |
|---|---|---|
| `control-plane` → `api.anthropic.com` | Claude calls (extraction, Kenny turn, adversarial review) |
| `control-plane`, `embedder` → `api.voyageai.com` | Embedding generation |
| `control-plane` → tenant-configured MCP servers | When Agent Kenny calls Slack / Linear / GDrive / etc. |
| `web` → `api.<your-domain>` | SSE streaming for Kenny chat (browser-initiated; relayed via Fly edge) |

Everything else stays inside Fly 6PN.

---

## Backups

- **Postgres**: out-of-the-box you get the Fly volume snapshots (manual:
  `fly volumes snapshots create <vol-id>`). For automated daily S3 backup
  point `scripts/backup.sh` at a S3 / R2 bucket and run it from a Fly
  cron — see `docs/ops/backup.md` (existing) for the cron knobs.
- **Ledger immutability**: the `ledger_events` table is append-only +
  notarised via the FreeTSA chain (Phase F1). The notarisation cron is
  not yet wired to Fly; run it locally for now and turn on later.

---

## What we explicitly do NOT do at deploy time

- **No Terraform / Pulumi.** Fly + CF dashboards + this runbook is
  enough infra for a single-tenant pilot. Add IaC when there are 3+
  environments.
- **No CI/CD pipeline auto-deploys.** Deploys are manual `fly deploy`
  invocations. A pilot is at the wrong scale to invest in auto-rollback.
  Add a GitHub Action that runs `fly deploy --remote-only` on `main`
  push once you have green sign-off from at least one customer.
- **No multi-region.** Single `iad` region until latency from EU/APAC
  customers becomes a real complaint.
- **No HSM / KMS for tenant DEKs.** The encryption pattern uses an
  in-process DEK provider that derives keys from a tenant-scoped seed.
  Sufficient for v1 self-hosted pilot. Move to AWS KMS / GCP KMS for
  multi-tenant SaaS.
