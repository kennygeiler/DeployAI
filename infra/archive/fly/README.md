# infra/archive/fly — superseded Fly.io configs (historical)

**Superseded by Railway on 2026-08-11.** The cloud stack now runs on Railway
(project `deployai`), where each service builds from the repo root with
`RAILWAY_DOCKERFILE_PATH` pointing at the same Dockerfiles these `fly.toml`
files referenced — there is no Railway equivalent of a per-service config file
in the repo. See [`docs/ops/cloud-deploy.md`](../../../docs/ops/cloud-deploy.md).

These configs are kept for reference (machine sizing, health-check tuning,
`release_command` migration wiring, per-service env). They were **not
re-verified** on archival and the Fly apps they describe are being torn down.
The Fly-era runbook is archived at
[`docs/archive/cloud-deploy-fly.md`](../../../docs/archive/cloud-deploy-fly.md).

| File | Was |
|---|---|
| `postgres/fly.toml` | Self-hosted Postgres 16 + pgvector + Apache AGE (built from `infra/compose/postgres/Dockerfile`) |
| `control-plane/fly.toml` | FastAPI control plane; `release_command: alembic upgrade head` (Railway replaces this with `RUN_MIGRATIONS=1` handled by `services/control-plane/docker-entrypoint.sh`) |
| `web/fly.toml` | Next.js web / BFF |
| `mcp-server/fly.toml` | Inbound read-only MCP server |
| `embedder/fly.toml` | Embedding worker (same CP image; Railway replaces the process group with `SERVICE_ROLE=embedder`) |
