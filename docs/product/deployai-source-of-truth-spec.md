# DeployAI — Source of Truth

**The single canonical reference for DeployAI: product intent, architecture, real-vs-fixture status, and where to track delivery.**

| | |
| --- | --- |
| **Status** | Authoritative. Maintained going forward. |
| **Audience** | Engineers (esp. anyone taking the codebase over), PM/GTM, hosting operators, leadership. |
| **Last verified against code** | 2026-05-21 (commit `c21e9b4`, branch `main`). |
| **Delivery tracking** | [`_bmad-output/implementation-artifacts/sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml) — honest epic-level status, kept in sync with this doc. |
| **Supersedes** | `whats-actually-here.md`, `pm-functionality-and-direction-brief.md`, and the BMAD planning artifacts (`prd.md`, `architecture.md`, `epics.md`, the product briefs, `ux-design-specification.md`, `mvp-operating-plan-2026.md`, `implementation-readiness-report-*`). All are archived under [`docs/archive/`](../archive/) for history. |

**The rule:** when this document and the code disagree, **the code wins** — fix the document. When this document and any archived planning artifact disagree, **this document wins**. Every claim here was checked against the repository at the commit above; sections that describe intent rather than shipped behavior say so explicitly.

---

## 1. What DeployAI is

DeployAI is an **agentic Deployment System of Record** — durable, cited memory for long-cycle, high-stakes customer deployments (municipal and regulated-enterprise accounts running 12–36 months).

**The problem it targets.** A long-cycle deployment's real operating system runs in one person's head — the deployment strategist who is simultaneously project manager, account manager, and customer-success engineer. When that person rotates out, or simply forgets, the deployment loses its memory: skipped calibrations, stakeholder turnover, and unrecorded commitments turn into expensive failures months later.

**The intended solution.** Convert every meeting, email, call, and field note for an account into a canonical, queryable store — an immutable event log, a time-versioned identity/stakeholder graph, and a library of "solidified learnings" with evidence snapshots. Agents are *retrieval-bound*: they may only surface or propose facts that trace back to a stored event, with a mandatory **citation envelope** on every output. Strategist-facing surfaces (morning digest, phase tracking, in-meeting alerts, queues) project that memory at the moment it is needed.

**Who it serves.** The primary user is the **deployment strategist** (also called a Forward Deployed Engineer / deployment lead at peer companies). The first intended deployment is the founder's own NYC DOT hardware engagement; peer GovTech vendors are the next intended customers. See archived [`product-brief-DeployAI.md`](../archive/product-brief-DeployAI.md) for the full GTM and commercial model.

**Important scope note for engagement/portfolio tracking.** DeployAI is architected as **deep single-account memory: one tenant models one deployment**, sitting in one phase of a 7-phase framework (see §6, §12). There is **no first-class "engagement" or portfolio entity**, no per-strategist roster of multiple engagements, and no cross-deployment roll-up. A cross-deployment view is *explicitly deferred* by the product brief ("waits for N ≥ 3 real deployments"), and the Timeline surface is a post-V1 (Epic 14) backlog item. A team that needs to track *many* engagements across *many* strategists would build that portfolio/team layer on top of this per-engagement substrate — it does not exist today.

---

## 2. V1 scope

**In scope for V1** (per the product brief; this is *intent*, not a completion claim — see §3):

- Strategist surfaces: Morning Digest, In-Meeting Alert, Phase & Task Tracking, Evening Synthesis, Action / Validation / Solidification queues, Evidence deep links, Overrides, Personal Audit, Integrations settings.
- Canonical memory: event log, time-versioned identity graph, solidified-learning library, tombstones, action/validation queues.
- Three-agent runtime: Cartographer, Oracle, Master Strategist (internal — no user UI in V1).
- Seven-phase deployment state machine with agent-proposed, human-confirmed transitions.
- Ingestion: M365 calendar/email, Teams transcript import, voice/meeting file upload, manual notes.
- Edge capture agent (Tauri macOS) and a Go FOIA CLI.

**Explicitly out of V1** (architected, not engineered):

- **Cross-deployment / portfolio analytics dashboard** — waits for N ≥ 3 real deployments.
- **Timeline / Visibility surface** — deferred to Epic 14 (post-V1).
- Live multi-agent negotiation trace UI; standalone Blocker dashboard; advanced calibration tooling.
- Successor-strategist inheritance *active role* (data model is V1, the role activates V1.5).

**Never to build:** competitive intelligence, external-threat mapping, vendor-tracking. DeployAI is a deployment-strategist tool, not a market-intelligence product.

---

## 3. Maturity — honest status

Read this before trusting any "done" label anywhere in the repo.

- **This codebase was generated with the BMAD method** (an AI-agent-driven development framework — see the agent personas under [`.cursor/skills/`](../../.cursor/skills/)). The 16-epic / ~95-story / "23-week" roadmap was produced by a single author across ~3 weeks of commit activity. The "week" labels in the roadmap are planning fiction, not elapsed engineering time.
- **"Done" in BMAD artifacts means "story acceptance criteria met / CI green," not "production feature."** Many epics marked `done` deliver production-*shaped* UI on **fixture or stubbed data**. The honest tracker ([`sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml)) reclassifies these — use it, not the BMAD story files.
- **What is genuinely solid:** the engineering scaffolding — typed Next.js + FastAPI code, async SQLAlchemy + Alembic migrations with tenant RLS, a working Anthropic/OpenAI LLM client, 13 CI workflows, SBOM/CVE scanning, accessibility gates, cross-tenant isolation fuzz tests, ~141 test files. Code quality is consistent and clean.
- **What is demo-grade:** digest/evening data (fixtures or optional HTTP feeds), meeting presence (a stub), the "agentic" layer (deterministic Python heuristics, no live LLM-driven loop into the UI — see §11). There is no running agent that ingests meetings and updates surfaces.
- **Overall:** a credible, well-engineered **prototype skeleton** — better scaffolding than most prototypes, but a prototype. It is **demo-usable**, not **pilot-usable** or **production-usable** (see §13 for the precise distinction).

### Phase 0 verification — 2026-05-21

The §16 Phase 0 checklist was executed against commit `de8f3e0`.

**Works:**
- Toolchain matches the repo pins — Node 24.15.0, pnpm 10.33.0, Rust 1.95.0, Go 1.26.2, uv 0.11.7, Docker 29.4.0.
- `pnpm install --frozen-lockfile` — reproducible, no lockfile drift.
- `pnpm turbo run lint typecheck test build` — **67 / 67 tasks pass** (~42s): every workspace lints, typechecks, unit-tests, and builds clean (control-plane 114 unit tests, cartographer 47, etc.).
- `make dev` — all 6 containers (postgres, redis, minio, freetsa-stub, control-plane, web) build and come up healthy; `make dev-verify` green; the demo seed loads 24 `fixtures.canonical_events`.
- All 10 strategist pages render (HTTP 200) through the web shell.

**Broken / gaps:**
- **The compose stack did not migrate the application database.** Postgres contained only the `fixtures` demo schema — no `alembic_version` table and none of the app tables. Root cause: nothing ran `alembic upgrade`, `alembic.ini` carried only a placeholder `sqlalchemy.url`, and `alembic/env.py` did not read `DATABASE_URL`. Compounding it, the control-plane runtime image shipped with **no Postgres driver at all** (`asyncpg` absent from dependencies; `psycopg` dev-only) — so even a migrated database would have been unreachable.
- **Consequently all three BFF strategist-queue routes returned 502** (`cp_error`). Queue *pages* render, but their data layer failed.
- `/evidence/[nodeId]` 404s for IDs absent from the (unmigrated) graph.
- The control-plane integration tests (76 deselected from the unit run — they need testcontainers) were not exercised in this pass.

**Resolved — Phase 0.5 (this PR).** The data layer is now wired: `asyncpg` + `psycopg` are runtime dependencies; `alembic/env.py` honors `DATABASE_URL`; the Dockerfile ships the migration scripts; and a one-shot `migrate` compose service runs `alembic upgrade head` (via the sync `psycopg` driver — `asyncpg` cannot execute the migrations' multi-statement DDL) before the control plane starts. Verified: all 16 migrations apply and the BFF strategist-queue routes return live Postgres data (200) instead of 502. The Phase 1 `Engagement` migration can now build on a working path.

---

## 4. Architecture — as built

Polyglot monorepo: **pnpm + Turborepo** workspaces, **Python (uv)** services, a **Go** CLI, a **Rust/Tauri** desktop app. ~49k lines of code.

```mermaid
flowchart LR
  subgraph client["Browser"]
    U["Strategist + admin routes"]
  end
  subgraph web["apps/web — Next.js 16"]
    MW["middleware.ts — correlation, JWT, authz, tenant gate"]
    BFF["Route handlers — /api/bff/* , /api/internal/*"]
    RSC["SSR loaders — strategist-surface-data, activity"]
  end
  subgraph cp["services/control-plane — FastAPI"]
    PUB["Public: auth (OIDC), integrations, SSO, uploads, SCIM"]
    INT["/internal/v1 — pilot surfaces, queues, meeting-presence, ingestion-runs"]
    DB[("Postgres — Alembic migrations")]
    REDIS[("Redis — optional")]
  end
  subgraph agents["Python services (offline / not wired into the live UI loop)"]
    ING["ingest"]
    CART["cartographer"]
    ORA["oracle"]
    MS["master_strategist"]
  end
  U --> MW --> BFF --> INT
  MW --> RSC --> INT
  INT --> DB
  PUB --> DB
  ING --> DB
  CART --> DB
  ORA --> DB
  MS --> DB
```

**Workspace map:**

| Path | Role | Reality |
| --- | --- | --- |
| `apps/web` | Next.js 16 App Router — strategist + admin routes, BFF/internal route handlers, middleware. | Real, the most complete workspace. |
| `apps/edge-agent` | Tauri macOS edge capture agent (Rust + Vite). | Scaffold + capability model; continuous audio capture is a follow-up. |
| `apps/foia-cli` | Go static CLI for FOIA bundle verification. | Real but small (~11 Go files). |
| `apps/eval` | Replay-parity / evaluation harness (rule + LLM-judge evaluators). | Real harness; not wired to a production agent loop. |
| `apps/tools/vpat-aggregator` | VPAT accessibility evidence aggregator. | Helper tool. |
| `services/control-plane` | FastAPI control plane — auth, integrations, internal APIs, all DB-backed strategist data. | Real; the backend of record. |
| `services/ingest`, `cartographer`, `oracle`, `master_strategist` | Python "agent" services. | Deterministic logic + contracts; **not** wired into a live browser loop (see §11). |
| `services/_shared` | Shared Python: `tenancy`, `authz`, `citation`, `checkpointer`, `runtime`, `tsa`. | Real shared libraries. |
| `packages/*` | `authz`, `contracts` (citation envelope), `shared-ui`, `design-tokens`, `foia-verifier`, `llama-citation-adapter`, `llm-provider`(`-py`). | Real; consumed by web + services. |
| `infra/compose` | Docker Compose reference stack. | Real; the only deployment artifact (see §5). |
| `migrations`, `services/control-plane/alembic` | Schema migrations. | Real; 16 Alembic versions. |

---

## 5. Intended architecture vs as-built

The archived [`architecture.md`](../archive/architecture.md) describes a far heavier production posture than what exists. A successor must not assume any of the following is present:

| Archived architecture.md says | Actually in the repo |
| --- | --- |
| AWS: ECS Fargate, RDS Multi-AZ, ALB+WAF, S3, ElastiCache, SQS, EventBridge, Secrets Manager, KMS. | **None.** No cloud infra. Deployment artifact is `infra/compose/docker-compose.yml` only. |
| Terraform + Terragrunt IaC. | **No `.tf` files exist.** |
| Bifurcated database (separate clusters / encryption domains). | Single Postgres. Logical scoping via `tenant_id` + RLS. |
| Every agent is a LangGraph state machine (`graph.py` per service). | No LangGraph state machines. Cartographer has `stub_graph.py` / `degradation_graph.py`; agents are plain Python. |
| Grafana/Loki/Tempo/Prometheus + OnCall observability. | Not present. CP exposes `/healthz`; correlation IDs are stamped. |
| FIPS modules, KMS envelope encryption, RFC 3161 TSA in the live path. | KMS DEK path raises "not implemented"; FreeTSA exists as a compose stub. |
| Services split as `api-gateway`, `canonical-memory`, etc. | Collapsed into one `control-plane` service. |

The compose stack runs six services: `postgres`, `redis`, `minio`, `freetsa-stub`, `control-plane`, `web`. Treat `architecture.md` as a **design aspiration / target state**, not a description of the system.

---

## 6. Data model

Schema lives in [`services/control-plane/alembic/versions/`](../../services/control-plane/alembic/versions/) (16 migrations) and the SQLAlchemy models under `services/control-plane/src/control_plane/domain/`. ~23 tables; tenant isolation via mandatory `tenant_id` + Postgres Row-Level Security policies (`20260422_0002_tenant_rls_policies.py`).

**Core groups:**

- **Canonical memory** — `canonical_memory_events` (immutable event log), `identity_nodes` + `identity_attribute_history` + `identity_supersessions` (time-versioned stakeholder graph), `solidified_learnings` + `learning_lifecycle_states`, `tombstones`, `schema_proposals`.
- **Deployment state** — `tenant_deployment_phases` (one phase row per tenant), `phase_transition_proposals`.
- **Strategist work queues** — `strategist_action_queue_items`, `strategist_validation_queue_items`, `strategist_solidification_queue_items`, `strategist_activity_events`, `adjudication_queue_items`.
- **Override / audit** — `private_override_annotations`.
- **Identity / tenancy / integrations** — `app_tenants`, `app_users`, `integrations`, `edge_agents`, `break_glass_sessions`, `ingestion_runs`.

**The shape that matters most:** the unit of tenancy is **one tenant = one deployment/account**, and `tenant_deployment_phases` gives that tenant exactly one current phase. There is **no `engagement` table, no portfolio entity, and no user-to-many-engagements assignment.** This is the central architectural fact for anyone whose goal is multi-engagement / team tracking — see §1 scope note.

---

## 7. Strategist surfaces & data provenance

All surfaces under `apps/web/src/app/(strategist)/` render in the browser. **Data provenance is flag-driven** — the surface looking real does not mean the data is real. Verified against [`strategist-surface-data.ts`](../../apps/web/src/lib/strategist-data/strategist-surface-data.ts) and [`strategist-pilot-tenant.ts`](../../apps/web/src/lib/internal/strategist-pilot-tenant.ts).

| Surface | Default data | "More real" path |
| --- | --- | --- |
| `/digest` | `MORNING_DIGEST_TOP` fixture in code | `STRATEGIST_DIGEST_SOURCE_URL` (validated JSON) or CP pilot surface |
| `/phase-tracking` | Seeded fallback rows + banner | Remote feed wired to schema, or CP pilot surface |
| `/evening` | Mock slice + patterns; nudge count from CP queue | `STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL` or CP pilot surface |
| `/in-meeting` | Activity poll + digest-aligned fixtures | CP `meeting-presence` (stub) + `?inMeeting=1` demo flag |
| `/action-queue` | **Postgres via CP** (empty until carryover/inserts) | needs `DEPLOYAI_CONTROL_PLANE_URL` + `DEPLOYAI_INTERNAL_API_KEY` + migrated DB |
| `/validation-queue` | **Postgres via CP** — auto-seeded with 10 **mock** rows on first tenant touch | same CP requirement |
| `/solidification-review` | **Postgres via CP** — auto-seeded with 20 **mock** rows on first tenant touch | same CP requirement |
| `/evidence/[nodeId]` | Works for fixture IDs linked from digest | needs a canonical graph backing the same IDs |
| `/overrides`, `/audit/personal` | BFF → CP durable overrides / activity APIs | CP migrated + tenant-scoped actor |
| Activity / degrade banners | `GET /api/internal/strategist-activity` → CP health + ingest + optional Oracle health URL | `DEPLOYAI_ORACLE_HEALTH_URL` (liveness only) |

**Key honesty points:**

- Queues are **always** Postgres-backed via CP — there is no in-memory web fallback. Without CP env + a migrated DB, queue routes return **503**.
- The CP queue rows for validation/solidification are **hardcoded mock seed data** (`"Validation candidate N: low-confidence extraction…"`), not real extractions.
- "Pilot surfaces" from CP are **operator-supplied JSON files** (`DEPLOYAI_PILOT_SURFACE_DATA_PATH`), not automatic canonical-memory projections. Canonical projections are types-only (`strategist-canonical-projections.ts`; flag `DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB` reserved, not wired).

---

## 8. Identity & tenancy

Middleware: [`apps/web/middleware.ts`](../../apps/web/middleware.ts).

- Stamps `x-deployai-correlation-id` on inbound requests.
- With `DEPLOYAI_WEB_TRUST_JWT=1` + PEM: verifies an RS256 access JWT (issuer `deployai-control-plane`, audience `deployai`), sets `x-deployai-role` / `x-deployai-tenant` from claims; bad token → **401**. Optionally strips inbound role/tenant headers first (`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1`).
- **In `NODE_ENV=development`, injects `deployment_strategist`** when headers are missing — disable with `DEPLOYAI_DISABLE_DEV_STRATEGIST=1`.
- Runs `canAccess` from `@deployai/authz`; blocks `external_auditor` from strategist surfaces (403).
- With `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`, strategist pages/APIs require `x-deployai-tenant` (403 if missing).
- Control plane implements OIDC and SCIM routes (`auth_oidc.py`, `scim.py`); **SAML is explicitly not implemented** (`auth_saml.py` returns "not implemented").

Production identity must replace dev role injection with real tenant SSO/session.

---

## 9. Queues & durability

- BFF queue handlers (`apps/web/src/app/api/bff/{action,validation,solidification}-queue/`) proxy to CP `/internal/v1/strategist/*-queue-items` ([`strategist_queues_internal.py`](../../services/control-plane/src/control_plane/api/routes/strategist_queues_internal.py)).
- **Fail-closed:** `strategist-queues-route-guard.ts` returns **503 `cp_misconfigured`** when CP URL/key is missing; CP unreachable → **502 `cp_error`**. No silent fallback.
- Queue state is **never** held in web-process memory — multi-replica web is safe for queue state when CP is healthy.

---

## 10. Meetings & presence

- CP endpoint `GET /internal/v1/strategist/meeting-presence?tenant_id=` ([`strategist_meeting_presence.py`](../../services/control-plane/src/control_plane/api/routes/strategist_meeting_presence.py)).
- Stub tenants listed in `DEPLOYAI_STUB_IN_MEETING_TENANT_IDS` return `in_meeting: true`; everyone else returns `in_meeting: false`, `detection_source: off`.
- **There is no live calendar/Graph integration for meeting presence.** The `/in-meeting` surface is driven by stub tenants or the `?inMeeting=1` URL demo flag (production-gated by `NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO=1`).

---

## 11. Intelligence / agent layer

The product is positioned as "agentic." Be precise about what that means today:

- **LLM client is real.** `packages/llm-provider-py` has working Anthropic (`claude-sonnet-4-20250514`) and OpenAI clients with retries and SSE streaming.
- **The "agents" are deterministic Python.** `master_strategist` "arbitration" is a weighted linear formula (`0.45·confidence + 0.35·phase_fit + 0.20·override_strength`). `oracle`, `cartographer`, `ingest` are likewise mostly deterministic logic and contracts/harnesses. Cartographer has a `stub_graph.py`.
- **There is no live agent loop.** Nothing ingests meetings, runs the LLM, and updates strategist surfaces in real time. "Activity poll" is not an agent stream.
- The replay-parity / evaluation harness (`apps/eval`, `tests/continuity-of-reference/`) is real and runnable, but it tests contracts, not a production agent.

Treat the agent services as **a lab and a spec**, not a running intelligence layer.

---

## 12. The 7-phase deployment framework

Authoritative labels are in code — [`services/control-plane/src/control_plane/phases/machine.py`](../../services/control-plane/src/control_plane/phases/machine.py):

`P1_pre_engagement → P2_discovery → P3_ecosystem_mapping → P4_design → P5_pilot → P6_scale → P7_inheritance`

Transitions are strictly forward, one step at a time (`can_transition`). A tenant has exactly one current phase (`tenant_deployment_phases`).

**Doc-vs-code drift to be aware of:** the archived PRD (FR30) names the phases differently ("Pre-sale/Scoping, Preparation, Integration/Data Collection, User Training, Value Creation, Preparing for Expansion, Expansion"). The **code labels above are authoritative**; the PRD names are stale.

---

## 13. Deployment modes & configuration

Full env catalog: [`.env.example`](../../.env.example). Three modes:

| Mode | Posture | What you get |
| --- | --- | --- |
| **Local demo** | `NODE_ENV=development`, dev role injection on, sources unset. | Walk the UX on fixtures. Queues still need a running CP + migrated DB. |
| **Hosted pilot** | `DEPLOYAI_WEB_TRUST_JWT=1` + PEM; `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`; CP URL + internal key; optional `DEPLOYAI_PILOT_TENANT_ID` / `DEPLOYAI_*_SOURCE=cp`. | SSO-shaped headers, tenant-scoped routes, Postgres queues, CP file-backed pilot surfaces. |
| **Production-shaped** | `NODE_ENV=production`; CP URL/key present; meeting URL demo off. | Fail-closed: queue routes 503 without CP. |

**Demo vs pilot vs production:**

- **Demo-usable** (today): walk the workflow with fixtures + dev role + a running CP for queues.
- **Pilot-usable** (not yet): same surfaces backed by durable per-tenant data, real SSO, real meeting signal, ingestion feeding the evidence graph.
- **Production-usable** (not yet): the above + a real agent loop driving updates, plus the operability/compliance work in Epic 12.

Run it locally: `pnpm install --frozen-lockfile` then `pnpm --filter @deployai/web dev`, or the full stack via `make dev` (see [`docs/dev-environment.md`](../dev-environment.md)).

---

## 14. Known gaps & risks

- **No portfolio / multi-engagement model** — the single largest gap for a team tracking many engagements (§1, §6).
- **No live agent loop** — surfaces do not update from model output (§11).
- **Meeting presence is a stub** — no calendar truth (§10).
- **Canonical-memory projections are unwired** — digest/evidence cannot be auto-materialized per tenant; pilot surfaces are operator JSON files (§7).
- **~131 stub / TODO / not-implemented markers in core code** — including SAML, S3-backed stores, KMS DEK encryption, real ASR transcription, the integration kill-switch.
- **Intended architecture is unbuilt** — no AWS, no IaC, no production observability (§5).
- **Epic 12 (FOIA / compliance / operability) is mostly backlog** — story 12-2 in review, 12-3…12-14 not started.
- **Doc-vs-code drift exists** — e.g. phase names (§12), CP correlation logging promised in `docs/production/correlation-ids-rollout.md` has no matching CP middleware. Keep this document as the reconciliation point.

---

## 15. Requirements & delivery tracking

- **Live status:** [`_bmad-output/implementation-artifacts/sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml) — rewritten to honest, code-verified epic-level statuses. **This is the tracker to update as work lands.** Update it in the same PR that changes delivery status, and update §3/§7/§14 here if a surface moves from fixture to real.
- **Requirements baseline:** the PRD defined 79 functional requirements, 78 non-functional requirements, and 12 design-philosophy commitments (DP1–DP12). The full text is archived at [`docs/archive/prd.md`](../archive/prd.md); the epic→FR mapping at [`docs/archive/epics.md`](../archive/epics.md). These are a historical baseline, not a delivery promise.
- **Forward roadmap:** see **§16** — the sequenced Phase 0–5 plan for the team-based direction.

---

## 16. Forward roadmap

**Status:** Direction, not a delivery promise.

**The pivot.** The archived BMAD epics ([`epics.md`](../archive/epics.md)) targeted a *single-strategist, single-deployment, agent-driven* product sold into government procurement. The direction going forward is a *team tool*: a cross-functional team (FDE, deployment strategist, biz dev) tracking many engagements and finding insight across them. The two share the canonical-memory substrate and little else. This roadmap supersedes the archived epic plan for prioritization; `sprint-status.yaml` remains the record of what the old plan delivered.

**Principle:** fix the foundation, don't polish the demo. Build what *any* version needs; defer what only the old product needed — SAML, KMS/FIPS, FOIA export, immutable audit log, compliance packets are all deferred.

### Phase overview

| Phase | Goal | Gate to next |
| --- | --- | --- |
| 0 | Ground truth — it builds, it runs, baseline recorded | A written what-works / what-breaks note |
| 1 | `Engagement` data-model pivot | Engagement-scoped data, isolation tested |
| 2 | Real identity + team roles | Real auth; `fde` / `deployment_strategist` / `biz_dev` roles |
| 3 | Manual capture + portfolio view | A team logs real engagements and sees them rolled up |
| 4 | Shared-brain layer — collaboration, role lenses, cross-role insight | — |
| 5 | Intelligence — agents, ingestion, synthesis | — |

### Phase 0 — Ground truth

Goal: a verified baseline. You cannot plan on a codebase you have not run.

> **Executed 2026-05-21 — results in §3 (Phase 0 verification).** Headline: builds clean (67/67 turbo tasks); the compose stack runs. Phase 0 found the application DB was never migrated and the control-plane image shipped no Postgres driver, so CP-backed queues returned 502. **Phase 0.5 (this PR) repaired that** — `make dev` now produces a migrated DB and the queues serve live data. Phase 1 builds on it.

- [ ] Install the toolchain per repo pins — Node 24.x + pnpm 10.x (`.nvmrc`, root `package.json` `engines`), Python (`.python-version`, `uv`), Go + Rust (`.tool-versions`, `rust-toolchain.toml`).
- [ ] `pnpm install --frozen-lockfile` — reproducible, no lockfile drift.
- [ ] `pnpm turbo run lint typecheck test build` — record pass/fail per workspace.
- [ ] Python service tests — `control-plane`, `ingest`, `cartographer`, `oracle`, `master_strategist` (pytest via `uv`).
- [ ] Bring up the stack — `make dev` then `make dev-verify` (postgres, redis, minio, freetsa-stub, control-plane, web).
- [ ] Run Alembic migrations against the compose Postgres; confirm `GET /healthz` on the control plane.
- [ ] `pnpm --filter @deployai/web dev`; walk every strategist surface — `/digest`, `/phase-tracking`, `/evening`, `/in-meeting`, `/action-queue`, `/validation-queue`, `/solidification-review`, `/evidence/[id]`, `/overrides`, `/audit/personal`, `/settings/integrations`. Note which render, which 503, which are fixtures.
- [ ] Confirm queue routes return real Postgres data with `DEPLOYAI_CONTROL_PLANE_URL` + `DEPLOYAI_INTERNAL_API_KEY` set.

**Exit:** a short "ground truth" note — what builds, what runs, what's broken — recorded in §3 (or a linked `ground-truth.md`).

### Phase 1 — `Engagement` data-model pivot

Goal: make *a team with many engagements* the native shape. This is the keystone — Phases 2–4 are blocked on it.

**Decision (confirm before implementation):** an `engagement` lives *within* a tenant — **tenant = team/company, engagement = one customer deployment**. Recommended over a portfolio-above-tenants model: simpler, matches "one team, many engagements," and keeps the existing tenant RLS as the outer boundary.

**New table — `engagements`:** `id`, `tenant_id` (FK), `name`, `customer_account`, `current_phase` (one of the 7 phases — §12; moves off `tenant_deployment_phases`), `status` (active / paused / closed), `created_at`, `updated_at`.

**Optional but cheap — `engagement_members`:** `engagement_id`, `user_id`, `role`. This is the seam that makes Phase 2 (roles) and Phase 4 (collaboration) drop-in; recommend including it now.

**Tables that become engagement-scoped** (add `engagement_id` FK): `canonical_memory_events`, `identity_nodes` + `identity_attribute_history` + `identity_supersessions`, `solidified_learnings`, `learning_lifecycle_states`, `tombstones`, `phase_transition_proposals`, `strategist_action_queue_items`, `strategist_validation_queue_items`, `strategist_solidification_queue_items`, `private_override_annotations`. `tenant_deployment_phases` folds into `engagements.current_phase` (keep an `engagement_phase_history` table if the audit trail is wanted).

**Stays tenant-scoped** (team-level): `app_tenants`, `app_users`, `integrations`, `edge_agents`, `break_glass_sessions`, `schema_proposals`, `adjudication_queue_items`, `ingestion_runs`.

**Workstreams:**

1. **Schema** — Alembic migration, expand-contract: add `engagements` (+ `engagement_members`); add *nullable* `engagement_id` to the scoped tables; backfill (one default engagement per existing tenant; set `engagement_id`); flip `NOT NULL`; add indexes; extend RLS / app-layer scoping to engagement.
2. **Domain models** — new `Engagement` SQLAlchemy model; add `engagement_id` to the affected `domain/` models; fold the phase model.
3. **Control-plane API** — engagement CRUD (list / create / get); internal queue + pilot-surface routes take `engagement_id` alongside `tenant_id`.
4. **BFF + web** — the actor/context carries a selected `engagement_id`; BFF queue routes pass it through; an engagement selector in the strategist shell (a dropdown is enough).
5. **Isolation tests** — extend the cross-tenant fuzz (`services/control-plane/.../fuzz/`) to also assert no cross-*engagement* leakage.

**Sequencing:** schema (additive) → backfill → `NOT NULL` flip → domain models → CP API → BFF/web → tests. Do it on a branch.

**Risk / effort:** touches ~11 tables, RLS, the domain layer, CP routes, the BFF, and the web shell — multi-week, and the highest-leverage build in the plan. Nothing downstream is safe to start until the schema is flipped.

### Phases 2–5 — direction (scope when Phase 1 lands)

- **Phase 2 — Real identity + roles.** Replace dev-header role injection (§8) with real auth — the control plane already has OIDC (`auth_oidc.py`). Add `fde`, `deployment_strategist`, `biz_dev` via the existing `AuthzResolver`. Populate `engagement_members`.
- **Phase 3 — Manual capture + portfolio.** A fast per-engagement "log meeting / decision / risk / next action" form writing real `canonical_memory_events`; a "my engagements" portfolio view (phase, last activity, attention flag). First real value — no agents.
- **Phase 4 — Shared-brain layer.** Per-engagement collaboration (assignment, notes, attribution), role lenses (FDE → technical, biz dev → commercial, strategist → both), cross-role insight (surface where their views diverge).
- **Phase 5 — Intelligence.** Wire the agent loop, M365 ingestion, meeting presence, insight synthesis — the original "magic," deferred until the manual loop is trusted and used daily.

---

## 17. Documentation map

This document is the canonical product/architecture reference. **Operational runbooks remain standalone** and are not duplicated here — find them below.

**Engineering & environment**
- [`docs/dev-environment.md`](../dev-environment.md) — toolchains, pnpm workflows, dev middleware, compose stack.
- [`docs/repo-layout.md`](../repo-layout.md) — detailed workspace map.
- [`docs/canonical-memory.md`](../canonical-memory.md) — canonical memory schema notes.
- [`docs/contracts/citation-envelope.md`](../contracts/citation-envelope.md) — citation envelope contract.
- [`docs/a11y-gates.md`](../a11y-gates.md), [`docs/design-tokens.md`](../design-tokens.md), [`docs/shadcn.md`](../shadcn.md), [`docs/design-system/governance.md`](../design-system/governance.md) — frontend/design system.
- [`docs/testing/`](../testing/) — golden corpus & fixtures.

**Identity, authz, security**
- [`docs/auth/`](../auth/) — SSO, SCIM, sessions setup.
- [`docs/authz/`](../authz/) — role matrix, RLS alignment.
- [`docs/security/`](../security/) — tenant isolation, cross-tenant fuzz.

**Pilot & operations**
- [`docs/pilot/`](../pilot/) — hosted pilot operator pack: `README.md`, `phase-0-checklist.md`, `hosted-environment.md`, `session-and-headers.md`, `support-runbook.md`, `queue-durability-modes.md`, and more.
- [`docs/production/`](../production/) — operations & release, Gate-1 verification, strategist data plane, runbooks.
- [`docs/human-ops-runbook.md`](../human-ops-runbook.md) — secrets, CI, release operations.
- [`docs/platform/`](../platform/) — account provisioning, break-glass, integration kill-switch.

**Specialized**
- [`docs/edge-agent/`](../edge-agent/) — Tauri agent capabilities & platform assessment.
- [`docs/foia/bundle-format.md`](../foia/bundle-format.md) — FOIA export bundle format.
- [`docs/compliance/nist-ai-rmf-mapping.md`](../compliance/nist-ai-rmf-mapping.md), [`docs/standards/agent-posture.md`](../standards/agent-posture.md).

**Archived (history only — superseded by this document)**
- [`docs/archive/`](../archive/) — the BMAD planning artifacts and prior product docs.

---

## 18. Changelog

| Date | Change |
| --- | --- |
| 2026-05-21 | **Consolidation.** This document established as the single source of truth, cross-referenced against code at `c21e9b4`. Absorbed `whats-actually-here.md`, `pm-functionality-and-direction-brief.md`, and the BMAD planning artifacts (archived under `docs/archive/`). `sprint-status.yaml` rewritten with honest, code-verified statuses. |
| 2026-05-21 | **§16 Forward roadmap added.** Phase 0 (build verification) and Phase 1 (`Engagement` data-model pivot) scoped concretely; Phases 2–5 outlined. Reflects the pivot from a single-strategist government-sales product to a team-based multi-engagement tracker. |
| 2026-05-21 | **Phase 0 executed** — results recorded in §3. Builds clean (67/67 turbo tasks); compose stack runs healthy; key finding: `make dev` did not migrate the app DB, so CP-backed queues 502'd. |
| 2026-05-21 | **Phase 0.5 — control-plane data layer repaired.** Added `asyncpg` + `psycopg` as runtime dependencies (the image shipped with no Postgres driver), made `alembic/env.py` honor `DATABASE_URL`, shipped the migration scripts in the image, and added a one-shot `migrate` compose service. `make dev` now produces a migrated database; BFF queue routes return live data (verified end-to-end). |

**Maintenance rule:** when code behavior changes, update this document and `sprint-status.yaml` in the same PR. When in doubt, verify against code and record the verification date in the header table.
