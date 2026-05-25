# Changelog

All notable changes to DeployAI ship here. The format follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-05-25

Release-pipeline hardening. No application-surface changes.

### Fixed

- `release.yml` installs `uv` before `pnpm turbo run build` so `@deployai/ingest#build` (`uv sync --frozen`) succeeds in CI.
- cosign signing switched from deprecated `--output-signature`/`--output-certificate` to `--bundle` (cosign v3 default; emits one `.sigstore.json` per artifact).
- Build-and-sign job permissions tightened — dropped unused `packages: write` (image push lives in the new `images` job).

### Added

- Tag pushes now produce a real GitHub Release page with signed tarballs + `.sigstore.json` bundles + SBOMs (SPDX + CycloneDX) attached. Previously artifacts were built+signed inside the runner and discarded.
- New `images` job in `release.yml` builds + pushes `ghcr.io/kennygeiler/deployai/{control-plane,web}:<tag>` + `:latest` on tag push, with build-provenance attestations per image digest.
- `workflow_dispatch` runs validate + build + sign + attest, but skip the publish + image push (tag-triggered only).
- `docs/release/v0.1.1-punch-list.md` — release-cycle findings + 8-step manual e2e checklist.

### Out of scope (still open in punch list)

- O1 OIDC live login (owner-credentialed)
- O2 Failover onboarding wizard surface (deferred)
- S1-S3 UX polish + S3 background-task route label
- P1-P2 ORM relationship() decls + DB-statement alert per-route

## [0.1.0] — 2026-05-25

First tagged release. DeployAI is a self-hosted product for cross-functional
deployment teams: ingest team artifacts (emails, meeting transcripts), build
a per-engagement deployment matrix (stakeholders × systems × risks ×
decisions), and surface oracle insights + master-strategist recommendations
on top of it.

### Added — Deployment matrix model

- Per-engagement matrix store (`matrix_nodes` + `matrix_edges` + `matrix_proposals`).
- 4 built-in node types: `stakeholder`, `system`, `risk`, `decision`; tenants
  can register additional node types via Settings.
- Matrix graph view (`@xyflow/react`) on the engagement-detail page with
  role-lens filter (FDE / Deployment Strategist / Biz Dev + tenant-defined roles).
- Citation drill-down chips so every matrix entry traces back to the source event.

### Added — Ingest + extraction

- Email paste-import path (`/settings/email-import`) accepting RFC 5322 +
  mbox input. Real Gmail OAuth delivery is deferred; the parser is shaped
  so the OAuth swap-in is mechanical.
- Meeting webhook receiver (`POST /internal/v1/meetings/webhook`) accepting
  Zoom / GMeet / Teams / manual_paste payload shapes.
- LLM-driven matrix extractor that turns raw events into `matrix_proposals`
  for strategist review. Pluggable provider via `tenant_llm_configs`.

### Added — Synthesis layer

- Oracle: per-engagement insights with severity + open/closed lifecycle.
- Master Strategist: cross-engagement recommendations surfaced in the
  Engagement Insights panel.

### Added — Per-tenant configuration

- LLM provider picker (`tenant_llm_configs`) — `anthropic`, `openai`, `stub`,
  plus an env-driven `failover` composition. Per-tenant primary + secondary
  failover (provider, api_key, model) supported.
- Prompt overrides (`tenant_agent_prompts`) for `oracle`, `master_strategist`,
  `matrix_extractor`.
- Webhooks (`tenant_webhooks`) for tenant-scoped event delivery with
  HMAC-SHA256 signing.
- Custom node types + custom member roles registered via Settings.

### Added — Audit + observability

- `strategist_activity_events` write path via `emit_audit_event` helper.
- BFF tenant-mutation routes (webhooks, llm-config, node-types, member-roles)
  fire-and-forget audit events on every mutation.
- `/settings/audit` UI for the strategist-facing event log.
- Prometheus metrics via `/metrics`: `deployai_db_statements_total` (per
  route + method), `deployai_http_request_duration_seconds`,
  `deployai_audit_emit_failures_total`, `deployai_slow_request_total`.
- Health probes: `/healthz` (liveness), `/readyz` (DB ping), `/metrics` (scrape).
- `LOG_FORMAT=json` mode + `X-Request-ID` propagation for log/trace
  correlation. OTLP exporter wired via `OTEL_EXPORTER_OTLP_ENDPOINT`.
- 5 recommended PromQL alert rules + Alertmanager routing snippet in
  `docs/ops/observability.md`.

### Added — Self-host ops

- `make backup` → S3 / MinIO-compatible bucket. Bundle is `pg_dump` plus a
  tenant → DEK-key-id manifest. Refuses to run without `S3_BUCKET` +
  `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`.
- `make restore BACKUP=s3://...` companion. Two opt-in safety gates
  (`DEPLOYAI_RESTORE_CONFIRM=YES`, `DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES` when
  the target DB is non-empty). Uses `pg_restore --single-transaction --clean
  --if-exists` so failure rolls back.
- `make backup-prune` retention sweep (default 30-day window). Dry-run by
  default; destructive path gated on `DEPLOYAI_PRUNE_CONFIRM=YES`.
- `make export ENGAGEMENT=<uuid>` writes per-engagement packet
  (`markdown.md` + `packet.pdf` + `data.json`). PDF via WeasyPrint.
- Keycloak compose stub + `/api/auth/callback/oidc` route. Real OIDC needs
  owner-provisioned realm + client secret.

### Added — Operator docs

- `docs/ops/deployment.md` — full self-host deployment runbook.
- `docs/ops/observability.md` — endpoints, env vars, metrics catalog,
  PromQL alert rules, request-correlation guide.
- `docs/ops/backup.md` — backup + restore + retention procedures.
- `docs/ops/export.md` — engagement-packet export CLI.
- `docs/security/self-host-surface.md` — network surface + known limitations.
- `docs/auth/oidc.md` — Keycloak / OIDC operator setup.
- `docs/standards/i18n.md` — string-extraction wiring + second-locale plan.
- `docs/perf/engagement-aggregate-query-budget.md` — query budget +
  measurement methodology for the engagement-detail aggregate.

### Changed

- Engagement-detail page now calls a single CP aggregate route
  (`GET /internal/v1/engagements/{id}/detail`) instead of 6 sequential
  BFF→CP calls. Drops CP query count from ~10–11 to ~8 in one transaction.
- BFF tenant-settings routes (`webhooks`, `node-types`, `member-roles`,
  `llm-config`) narrow JSON bodies via Zod before forwarding to CP.
- Docker compose pins `redis` + `minio` + `keycloak` to specific minor +
  digest. Keycloak ships with a managed-port health check.
- Repo licensed under MIT.

### Security

- Audit emit `detail` payloads explicitly exclude credential fields
  (`api_key`, `signing_secret`, `webhook_url`).
- Engagement packet export omits all DEK + tenant API key material.
- Backup script refuses to run without explicit AWS credentials.
- Restore script requires double opt-in when target DB is populated.
- All `/internal/v1/*` routes gated on `X-DeployAI-Internal-Key`.

### Deferred — explicit pause points

- **Live OAuth delivery** (Gmail / Zoom): owner-credentialed; IMAP/MBOX +
  webhook paste paths are pre-shaped for mechanical OAuth swap-in.
- **OIDC login**: Keycloak compose stub + 503/501 callback route ship in
  this release; real JWT verification + session mint pend owner-provisioned
  realm.
- **Per-tenant failover UI consumption**: schema + ORM + factory ship; the
  Settings picker also ships, but bulk-onboarding UX is a future polish.

[0.1.1]: https://github.com/kennygeiler/DeployAI/releases/tag/v0.1.1
[0.1.0]: https://github.com/kennygeiler/DeployAI/releases/tag/v0.1.0
