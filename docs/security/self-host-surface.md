# Self-host security surface

This document is the operator-facing inventory of every network surface,
credential store, and known limitation in a self-hosted DeployAI install
running the `infra/compose/docker-compose.yml` reference stack. Pair it
with `docs/security/tenant-isolation.md` (which covers in-process
multi-tenant defense in depth) and `docs/ops/deployment.md` (which
covers operating the stack).

If your threat model differs from "single-tenant pilot behind a trusted
reverse proxy," **read this end-to-end before exposing the stack to the
public internet.** Several listed limitations are explicit short-term
choices, not bugs, and they assume an operator-controlled perimeter.

## Network surface

| Service | Port (compose default) | Bind scope | Notes |
|---|---|---|---|
| `web` (Next.js) | `3000` | Host-published | Public surface. Behind a TLS-terminating reverse proxy in any non-dev deployment. |
| `control-plane` (FastAPI) | `8000` | Host-published | Public surface for browser BFF calls; also serves `/internal/v1/*` gated by `DEPLOYAI_INTERNAL_API_KEY`. Behind the same proxy as `web`. |
| `postgres` | `5432` | Host-published in compose default | **Internal-only.** The default port publish is a dev convenience; in any pilot/prod deploy, override `POSTGRES_PORT` to bind to `127.0.0.1` or remove the host publish entirely so only the compose network can reach it. |
| `redis` | `6379` | Host-published in compose default | **Internal-only.** Same caveat as Postgres — bind to loopback or drop the host publish in non-dev. |
| `minio` | `9000` (API), `9001` (console) | Host-published in compose default | **Internal-only** in production (the control-plane writes via the in-network service name `minio:9000`). The console is convenient for dev but should not be exposed to the public internet — gate at the proxy or drop the publish. |
| `freetsa-stub` | `2020` | Host-published in compose default | Local-dev TSA stub. **Never expose** — replace with a real RFC 3161 TSA in any production deploy. |

**TLS** is not terminated inside the compose stack. The expected pattern
is a TLS-terminating reverse proxy (nginx, Caddy, an ALB, Cloudflare,
etc.) in front of `web` and `control-plane`. The stack itself speaks
plain HTTP on the host network.

## Authentication

| Surface | Mechanism | Notes |
|---|---|---|
| Web → BFF | Browser cookie `deployai_access_token` (RS256 JWT) | When `DEPLOYAI_WEB_TRUST_JWT=1`, `apps/web/middleware.ts` verifies in-process and sets `x-deployai-role` / `x-deployai-tenant` for downstream BFF routes. |
| BFF → Control Plane | Server-side bearer | The web BFF forwards calls server-to-server using `DEPLOYAI_INTERNAL_API_KEY` against `/internal/v1/*`. Browsers never see the internal key. |
| Control Plane public API | OIDC (Entra/Azure AD) | RS256 access token. See `docs/auth/sso-setup.md`. |
| Control Plane `/internal/v1/*` | Static API key (`X-DeployAI-Internal-Key`) | One key for the entire surface, including audit-event read/write. Rotate per pilot. |
| SCIM (`/scim/v2/*`) | Bearer token | Configured per tenant; see SCIM docs. |

## Credential storage

| Credential | Where it lives | Encryption at rest | Risk |
|---|---|---|---|
| OIDC client secret | Process env (`DEPLOYAI_OIDC_CLIENT_SECRET`) | Operator-supplied; lives in `infra/compose/.env` on disk | Standard secret-handling — keep the env file `chmod 600`, don't commit it. |
| Internal API key | Process env (`DEPLOYAI_INTERNAL_API_KEY`) | Same as above | Same as above. |
| JWT signing key | File on disk (`DEPLOYAI_JWT_PRIVATE_KEY_PATH`) | Filesystem-level only | Mount as a read-only secret in any real deployment; don't bake into the image. |
| Tenant LLM API keys (Anthropic, etc.) | **Plaintext in Postgres** (`tenant_llm_provider_config` table) | **None at the application layer** | **Known limitation.** Encrypt-at-rest is future work (see § Known limitations). Operator MUST rely on the DB volume's underlying disk encryption and on backup-bucket encryption (see § Backup file sensitivity) until then. |
| Tenant DEK ciphertext | Postgres, wrapped by external KMS key | KMS-wrapped | DEK metadata (`tenant_id`, `name`, `dek_key_id`) is dumped by `make backup`; the wrapped ciphertext stays put. Restoring requires the same KMS key. |
| Session state | Redis | None | Bound to TTLs; sessions are short-lived. Redis is not exposed externally (see § Network surface). |
| Object storage (MinIO) | MinIO root user/password | Configured in `infra/compose/.env` | Same handling as OIDC secret. |

## Audit log surface

Two endpoints under `/internal/v1/audit-events`, both gated by
`DEPLOYAI_INTERNAL_API_KEY`:

- `POST /internal/v1/audit-events` — append an audit event. Used by
  internal services to record security-relevant actions (break-glass
  requests/approvals/revocations, etc.).
- `GET /internal/v1/audit-events` — list/page audit events. Read access
  is gated on the same internal key; there is no per-actor RBAC layer
  on top.

Audit events are stored in Postgres alongside the rest of the schema
and are included in `make backup`'s `pg_dump`. They are not exfiltrated
to an external SIEM by default — wire that up out-of-band if your
compliance posture requires it.

## Backup file sensitivity

`make backup` writes two artifacts per run to S3 (or MinIO):

- `postgres.dump` — **the entire control-plane database**, including
  tenant rows, engagement contents, transcripts, audit events, and
  plaintext tenant LLM API keys (see § Credential storage). Treat this
  file as production-sensitive credential material.
- `dek_metadata.json` — `(tenant_id, name, dek_key_id)` tuples that
  point at KMS-side wrapped material. By itself this is not directly
  exploitable (the key ciphertext lives in the dump, the key material
  lives in KMS), but combined with the dump it lets a restore proceed.

**The destination S3 bucket MUST be encrypted at rest (SSE-S3 or
SSE-KMS) with access scoped to the operator role only.** The backup
script does not encrypt the dump itself before upload — it relies on
the bucket's own at-rest encryption.

Pruning (`make backup-prune`) defaults to dry-run; an operator must
set `DEPLOYAI_PRUNE_CONFIRM=YES` to actually delete. The pruner does
not lifecycle-tag objects — it deletes whole timestamped prefixes
older than `BACKUP_RETENTION_DAYS` (default 30).

## Known limitations

Recorded here so reviewers don't have to read the codebase to find
them. Each is a deliberate near-term posture, not an undiscovered bug.

- **Tenant LLM API keys are stored plaintext in Postgres.** Encrypt-at-
  rest with per-tenant DEKs is the planned next step; until then, the
  defense relies on (a) disk encryption on the DB volume, (b) tenant
  isolation enforced at the application + RLS layers
  (`docs/security/tenant-isolation.md`), and (c) backup-bucket
  encryption (above).
- **No rate limiting on `/internal/v1/*` routes.** The internal API key
  is the only gate; there is no per-key or per-IP throttling. Assume
  the operator controls every caller of the internal surface.
- **DEK rotation is manual.** There is no scheduled rotation job; an
  operator wraps a new DEK in KMS and updates `tenant_llm_provider_config`
  by hand. Plan a runbook before turning the stack over to a customer.
- **No OIDC provider for the public surface beyond Entra.** Generic
  OIDC (Okta, Google Workspace, Keycloak) is not tested end-to-end.
  Adding a provider requires verifying the issuer + JWKS handshake in
  `services/_shared/runtime` — out of scope for this slice.
- **Audit events are not streamed to an external SIEM by default.**
  See § Audit log surface — wire this in out-of-band.
- **The reference `freetsa-stub` is not RFC 3161 conformant.** Replace
  with a real TSA in any production deployment that signs anything
  with the result.
- **The compose stack publishes Postgres, Redis, and MinIO ports to
  the host by default.** Acceptable for local dev; in any pilot/prod
  deploy, bind to `127.0.0.1` or drop the host publish entirely so
  these services are reachable only on the compose network.
