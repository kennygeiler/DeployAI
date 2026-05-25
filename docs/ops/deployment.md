# Deployment runbook — self-hosted DeployAI

This is the operator-facing runbook for standing up, upgrading, and
recovering a self-hosted DeployAI install. It covers the reference
compose topology in `infra/compose/docker-compose.yml`; deployments to
Kubernetes or non-compose orchestrators are out of scope.

## Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose ...`).
  `docker --version` and `docker compose version` should both succeed.
- A host with at least 4 CPU / 8 GB RAM and ~20 GB free disk for the
  Postgres + MinIO volumes. Cold first-build pulls ~3 GB of base images.
- The following host ports free (or override via env): `3000` (web),
  `8000` (control plane), `5432` (postgres), `6379` (redis), `9000`
  and `9001` (minio API + console), `2020` (freetsa-stub).
- An S3 endpoint for backups. Local dev uses the in-stack MinIO; pilots
  and production should point at a managed S3 bucket. See `docs/ops/backup.md`
  § Local dev (MinIO) quickstart.
- Anthropic API key (set `ANTHROPIC_API_KEY` in `infra/compose/.env`) if
  you want real LLM extraction in `make seed-app` and `/ingest`. Without
  it the stub provider returns empty proposals; the rest of the stack
  works fine.

## First-run install

```bash
# Repo root
cp infra/compose/.env.example infra/compose/.env   # edit secrets in place
make dev                                            # builds + brings up stack
make dev-verify                                     # probes every health endpoint
make seed-app                                       # 1 engagement + ~20 events + extraction
```

`make dev` blocks until all services report healthy (timeout 15 min).
`make seed-app` requires the stack to be up and the LLM provider to be
configured for non-empty proposals.

Once green:

- Web UI:        http://localhost:3000
- Control plane: http://localhost:8000/health
- MinIO console: http://localhost:9001  (user/pass from `.env`)

For a scripted first install (tenant + LLM config + first engagement +
first user + first member), use `make init` instead of clicking through
the `/onboarding` wizard. See `python3 infra/compose/seed/init.py --help`.

## Environment variables

Source of truth: `.env.example` at the repo root, `infra/compose/.env.example`
for compose overrides. All `DEPLOYAI_*` vars are documented inline there.
This runbook lists only the operator-facing ones grouped by surface.

### Control plane (`services/control-plane`)

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@host:5432/db`. Migrations use `+psycopg`. |
| `REDIS_URL` / `DEPLOYAI_REDIS_URL` | yes | `redis://host:6379/0`. Session store + rate-limit state. |
| `DEPLOYAI_INTERNAL_API_KEY` | yes | Gate on every `/internal/v1/*` route. Rotate per pilot. |
| `DEPLOYAI_OIDC_ISSUER` / `DEPLOYAI_OIDC_CLIENT_ID` / `DEPLOYAI_OIDC_CLIENT_SECRET` / `DEPLOYAI_OIDC_REDIRECT_URI` | hosted only | Entra/Azure AD OIDC; see `docs/auth/sso-setup.md`. |
| `DEPLOYAI_JWT_PRIVATE_KEY_PATH` / `DEPLOYAI_JWT_PUBLIC_KEY_PATHS` | hosted only | RS256 access-token key pair. |
| `DEPLOYAI_LLM_PROVIDER` | optional | `anthropic` enables real extraction; unset/empty → stub. |
| `ANTHROPIC_API_KEY` | when `DEPLOYAI_LLM_PROVIDER=anthropic` | LLM key. |
| `DEPLOYAI_ANTHROPIC_SECRET_ARN` | optional | AWS Secrets Manager fallback when `ANTHROPIC_API_KEY` is unset. |

### Web / BFF (`apps/web`)

| Var | Required | Notes |
|---|---|---|
| `DEPLOYAI_CONTROL_PLANE_URL` | yes | Server-to-server URL. In compose: `http://control-plane:8000`. |
| `NEXT_PUBLIC_CONTROL_PLANE_URL` | yes | Browser-visible URL. |
| `DEPLOYAI_INTERNAL_API_KEY` | yes | Must match the control plane's key. |
| `DEPLOYAI_WEB_TRUST_JWT` | hosted only | `1` to enable Path A (middleware-verified JWT). |
| `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` | when `_TRUST_JWT=1` | SPKI PEM; multiple blocks may be concatenated for rotation. |
| `DEPLOYAI_PILOT_TENANT_ID` | hosted single-tenant | Tenant UUID for pilot identity wiring. |
| `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` | local only | `1` in compose to inject `x-deployai-role` without rebuild. **Never set in hosted.** |

### S3 / backup (`scripts/backup.sh`, `scripts/restore.sh`, `scripts/backup-prune.sh`)

| Var | Required | Notes |
|---|---|---|
| `S3_BUCKET` | yes | Destination bucket. Scripts refuse to run without it. |
| `S3_PREFIX` | no (default `deployai/backups`) | Key prefix. |
| `S3_ENDPOINT_URL` | MinIO/local | e.g. `http://localhost:9000`. Unset for real AWS. |
| `AWS_REGION` | no (default `us-east-1`) | Forwarded to `aws s3`. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | yes | Standard AWS env. IAM-role creds on the host are preferred in prod. |
| `BACKUP_RETENTION_DAYS` | no (default `30`) | `make backup-prune` retention window. |
| `DEPLOYAI_PRUNE_CONFIRM` | yes for actual delete | `YES` to actually delete; otherwise dry-run. |
| `DEPLOYAI_RESTORE_CONFIRM` | yes for restore | `YES` to allow restore; restore is destructive. |
| `DEPLOYAI_RESTORE_FORCE_OVERWRITE` | when target DB is non-empty | `YES` to clobber an already-populated DB. |

### Observability (optional)

| Var | Notes |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP/HTTP receiver (e.g. `http://otel-collector:4318`). Enables export of control-plane app + LLM token metrics. Sibling slice D1.c may add a `/readyz` probe wired to the same SDK. |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Per-signal override. |
| `OTEL_SERVICE_NAME` | Default `deployai-control-plane`. |
| `OTEL_METRIC_EXPORT_INTERVAL` | Milliseconds; default 5000. |
| `OTEL_SDK_DISABLED` | `true` to skip OTel init (local dev without a collector). |

The full inline catalog (including M365/Google/Slack integration creds,
upload pipeline, eval harness, strategist plumbing) lives in
`.env.example` at the repo root.

## Backup + restore cycle

```bash
# Backup — writes s3://${S3_BUCKET}/${S3_PREFIX}/<TIMESTAMP>/{postgres.dump, dek_metadata.json}
export S3_BUCKET=deployai-prod-backups
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
make backup

# Restore — destructive; requires explicit confirmation
export DEPLOYAI_RESTORE_CONFIRM=YES
# If the target DB is non-empty, also:
# export DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES
make restore BACKUP=s3://deployai-prod-backups/deployai/backups/20260524T172500Z/
```

Backup contents and the full restore procedure (provisioning a fresh
Postgres, re-applying migrations, importing DEK metadata) are documented
in `docs/ops/backup.md`. The dump is a custom-format `pg_dump`; it
**contains tenant API keys and engagement contents** — the destination
S3 bucket MUST be encrypted at rest and access-controlled. See
`docs/security/self-host-surface.md` § Backup file sensitivity.

### Retention

```bash
# Dry-run — lists folders that would be deleted, changes nothing
S3_BUCKET=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... make backup-prune

# Actually delete (older than BACKUP_RETENTION_DAYS, default 30)
DEPLOYAI_PRUNE_CONFIRM=YES \
S3_BUCKET=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
make backup-prune
```

Wire `make backup-prune` into cron alongside `make backup`. Both scripts
exit non-zero on misconfig — surface failures to your monitoring.

## Upgrade

The reference compose stack builds images locally from this repo. The
upgrade flow is:

```bash
git fetch && git checkout <new-tag>
cp infra/compose/.env infra/compose/.env.bak    # keep the old env
# Reconcile any new vars in .env.example into .env (diff or manual)
make dev                                         # rebuilds + reapplies migrations
make dev-verify                                  # confirm health
```

`make dev` re-runs the one-shot `migrate` service (`alembic upgrade head`)
on every bring-up — the `control-plane` service waits on it, so the app
never serves against an unmigrated DB. There is no separate `make migrate`
target; migrations are an implicit part of `make dev`.

If you ship pre-built images (not the default for this repo), pull the
new digest and `docker compose up -d` to roll forward; the `migrate`
service still runs because `control-plane` depends on it
`service_completed_successfully`.

## Rollback

1. **Stop the stack** so the new image isn't actively writing:
   ```bash
   make dev-down       # NOTE: also removes named volumes; restore overwrites
   ```
2. **Check out the previous tag** (or pull the previous image digest if
   you ship pre-built images):
   ```bash
   git checkout <previous-tag>
   ```
3. **Restore the last good backup:**
   ```bash
   export DEPLOYAI_RESTORE_CONFIRM=YES
   export DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES   # the volume just came back empty
   make restore BACKUP=s3://${S3_BUCKET}/deployai/backups/<TIMESTAMP>/
   ```
4. **Bring the old version back up:**
   ```bash
   make dev
   make dev-verify
   ```

The DB schema is the rollback hazard: if the failed upgrade applied a
migration that the previous app code does not understand, the rollback
must restore from a backup taken *before* the migration ran. Take a
backup immediately before every upgrade.

## Health probes

| Probe | Endpoint | Notes |
|---|---|---|
| Liveness | `GET http://localhost:8000/healthz` | k8s convention; alias `/health`. Returns `{status, service, version}`. |
| Readiness | `GET http://localhost:8000/readyz` | Sibling slice D1.c adds this; verifies DB + Redis reachability before the app is marked ready to serve. |
| Web | `GET http://localhost:3000/` (expect 307 → `/engagements`) | `make dev-verify` runs this. |
| MinIO | `GET http://localhost:9000/minio/health/live` | Built-in. |
| Postgres | `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}` | Compose healthcheck. |
| Redis | `redis-cli ping` → `PONG` | Compose healthcheck. |

`make dev-verify` exercises every public probe and the seed assertion in
one shot — wire it into your monitoring smoke tests.
