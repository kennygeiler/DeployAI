# Cloud deploy architecture — Railway

Companion to [`cloud-deploy.md`](./cloud-deploy.md). Diagrams the topology +
trust boundaries of the Railway project `deployai`. The Fly.io predecessor is
archived at
[`docs/archive/cloud-deploy-architecture-fly.md`](../archive/cloud-deploy-architecture-fly.md).

---

## Topology

```
                     ┌──────────────────────────────────────────┐
                     │  Browser / operator                      │
                     │  (bootstrap JWT cookie today; OIDC is a  │
                     │   pre-pilot blocker — runbook §7)        │
                     └───────┬──────────────────┬───────────────┘
                             │ HTTPS            │ HTTPS (SSE direct to CP)
                             ▼                  ▼
      ┌──────────────────────────────────────────────────────────────────┐
      │  Railway edge (per-service public domains, auto-TLS)             │
      │                                                                  │
      │  web-production-e4059.up.railway.app        ──► web              │
      │  control-plane-production-798e.up.railway.app ─► control-plane   │
      │  mcp-server-production-d7af.up.railway.app  ──► mcp-server       │
      │                                                                  │
      │  Private network (<service>.railway.internal, no public ingress  │
      │  for postgres / redis / embedder):                               │
      │    control-plane.railway.internal:8000                           │
      │    postgres.railway.internal:5432                                │
      │    redis.railway.internal:6379                                   │
      └──────┬───────────────┬───────────────┬──────────────────────────┘
             │               │               │
             ▼               ▼               ▼
      ┌──────────────────────────────────────────────────────────────┐
      │  Railway project `deployai` — services                       │
      │                                                              │
      │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐   │
      │  │  web         │  │ control-plane│  │ mcp-server        │   │
      │  │  Next.js 16  │  │ FastAPI      │  │ FastAPI (JSON-RPC)│   │
      │  │  (BFF → CP)  │  │ RUN_MIGRA-   │  │                   │   │
      │  │              │  │ TIONS=1      │  │                   │   │
      │  └──────────────┘  └──────┬───────┘  └────────┬──────────┘   │
      │                          │                    │              │
      │  ┌───────────────────────▼────────────────────▼───────────┐  │
      │  │  embedder — same CP image, SERVICE_ROLE=embedder       │  │
      │  │  (no ingress; polls the embedding job queue)           │  │
      │  └───────────────────────┬────────────────────────────────┘  │
      │                          ▼                                   │
      │  ┌────────────────────────────────────────────────────────┐  │
      │  │  postgres — Postgres 16 + pgvector + Apache AGE 1.6.0  │  │
      │  │  built from infra/compose/postgres/Dockerfile          │  │
      │  │  volume: postgres-volume → /var/lib/postgresql/data    │  │
      │  └────────────────────────────────────────────────────────┘  │
      │  ┌────────────────────────────────────────────────────────┐  │
      │  │  Redis (Railway managed, own volume)                   │  │
      │  └────────────────────────────────────────────────────────┘  │
      └──────────────────────────────────────────────────────────────┘
             │                                      │
             ▼                                      ▼
      ┌──────────────────────────┐    ┌────────────────────────────┐
      │  Anthropic API (Claude)  │    │  Voyage AI API (embeddings)│
      └──────────────────────────┘    └────────────────────────────┘
```

One image, two roles: `services/control-plane/docker-entrypoint.sh`
dispatches on `SERVICE_ROLE` (api | embedder) and runs
`alembic upgrade head` on boot when `RUN_MIGRATIONS=1` — Railway has no
release commands or process groups, so the entrypoint carries both jobs.

---

## Trust boundaries

Two rings — outside-in:

1. **Public internet** — anyone can reach the three public domains. The web
   app's middleware rejects requests without a verified session JWT
   (`DEPLOYAI_WEB_TRUST_JWT=1` + the CP's public key). The CP's `/internal/v1`
   surface requires `X-DeployAI-Internal-Key` (or a tenant service token);
   the MCP server requires CP-minted bearer tokens.
2. **Railway private network** — only services in the project resolve
   `*.railway.internal`. The internet cannot reach Postgres, Redis, or the
   embedder at all.

There is no SSO perimeter in front of the public domains (the Fly-era
Cloudflare Access plan was dropped in favor of app-level OIDC). Until OIDC
lands, operator access uses CP-minted 15-minute bootstrap JWTs — runbook §7
— which is why **real OIDC is a pre-pilot blocker**.

---

## Where each secret lives

Set per-service with `railway variables --service <name> --set K=V`; the
reference syntax `${{Service.VAR}}` shares values without duplication
(e.g. `${{Redis.REDISPASSWORD}}` inside `REDIS_URL`).

| Secret | Stored on | Who reads it |
|---|---|---|
| `POSTGRES_PASSWORD` | postgres | Postgres init; embedded in each `DATABASE_URL` |
| `DATABASE_URL` | control-plane, embedder, mcp-server | Each service's DB driver |
| `REDIS_URL` / `DEPLOYAI_REDIS_URL` | control-plane | Rate limits + refresh sessions (composed from `${{Redis.REDISPASSWORD}}`) |
| `DEPLOYAI_INTERNAL_API_KEY` | control-plane, web, mcp-server | BFF → CP and MCP → CP internal bearer |
| `ANTHROPIC_API_KEY` | control-plane only | Claude calls (extraction, Kenny, adversarial review) |
| `VOYAGE_API_KEY` | control-plane, embedder | Embedding API |
| `DEPLOYAI_JWT_PRIVATE_KEY_B64` | control-plane only | RS256 session-JWT signing key; entrypoint materializes it to a file (no file-mount secrets on Railway) |
| `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` | web (not secret) | Verifies CP-minted session JWTs |
| `DEPLOYAI_SLACK_CLIENT_*` | control-plane only | Slack OAuth start/callback |
| Tenant OAuth tokens | Postgres `tenant_mcp_configs.encrypted_auth_token` | Encrypted with tenant DEK; plaintext never leaves `mcp_client.py` |

No secrets in any committed file. Every value lives in Railway service
variables.

---

## Outbound network calls — what reaches the public internet

| Caller | Destination | Why |
|---|---|---|
| control-plane | `api.anthropic.com` | Claude calls (extraction, Kenny turn, adversarial review) |
| control-plane, embedder | `api.voyageai.com` | Embedding generation |
| control-plane | tenant-configured MCP servers | Agent Kenny outbound (kill switch → allow-list → rate limit → egress guard) |
| browser | CP public domain | SSE streaming for Kenny chat |

Everything else stays on the Railway private network.

---

## Backups

- **Postgres**: Railway volume backups on `postgres-volume` (schedule in the
  dashboard) + a documented manual `pg_dump` path over a TCP proxy — see
  [`docs/ops/backup.md`](./backup.md). The Fly-era nightly pg_dump→S3
  workflow was retired with the migration; scheduled offsite dumps are an
  open item (backlog H1).
- **Ledger immutability**: `ledger_events` is append-only + notarised via
  the FreeTSA chain. The notarisation cron is not wired in the cloud; run
  locally for now.

---

## What we explicitly do NOT do at deploy time

- **No Terraform / Pulumi.** Railway dashboard + CLI + this runbook is
  enough infra for a single-tenant pilot. Add IaC at 3+ environments.
- **No multi-region.** Single region until latency is a real complaint.
- **No HSM / KMS for tenant DEKs.** In-process DEK provider, tenant-scoped
  seed. Sufficient for the v1 pilot; move to a cloud KMS for multi-tenant
  SaaS.
- **CI auto-deploy is deliberately thin.** `.github/workflows/cloud-deploy.yml`
  runs `railway up` per service after CI passes on `main`; rollbacks are
  manual via the dashboard's deployment history. No auto-rollback machinery
  at pilot scale.
