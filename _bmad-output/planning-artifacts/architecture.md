---
stepsCompleted:
  - step-01-init
  - step-02-context
  - step-03-starter
  - step-04-decisions
  - step-05-patterns
  - step-06-structure
  - step-07-validation
  - step-08-complete
status: 'complete'
completedAt: '2026-04-21'
lastStep: 8
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/product-brief-DeployAI.md"
  - "_bmad-output/planning-artifacts/product-brief-DeployAI-distillate.md"
  - "_bmad-output/brainstorming/brainstorming-session-2026-04-21-150108.md"
  - "_bmad-output/planning-artifacts/implementation-readiness-report-2026-04-21.md"
workflowType: 'architecture'
project_name: 'DeployAI — Agentic Deployment System of Record'
user_name: 'Kenny Geiler'
date: '2026-04-21'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Source PRD Summary

**DeployAI** is the agentic Deployment System of Record for long-cycle regulated-customer deployments (initial anchor: NYC DOT). Core substrate: canonical memory (immutable event log + time-versioned identity graph + solidified-learning library + Action Queue + User Validation Queue) with mandatory citation envelopes, feeding three V1 agents (Cartographer / Oracle / Master Strategist-internal) that project onto three V1 user surfaces (Morning Digest / In-Meeting Alert / Phase & Task Tracking). Moat is the memory substrate, NOT the LLM.

**Governing commitments from PRD that architecture MUST respect:**
- 79 Functional Requirements (capability contract)
- 78 Non-Functional Requirements with measurement conventions preamble
- 12 Design Philosophy commitments (DP1–DP12) governing agent behavior and surface feel
- 7-phase DeployAI Deployment Framework as named open methodology
- Bifurcated record-of-truth (logical V1, physical V1.5+)
- Single US region V1 (us-east-2 primary)
- FIPS 140-2, RFC 3161 signed time, SOC 2 Type II by M15–18, StateRAMP Ready target-driven by Anchor
- Dual deployment topology: shared-tenant SaaS + self-hosted reference build


## Project Context Analysis

### Requirements Overview

**Functional Requirements:** 79 FRs across 8 capability areas: Memory & Canonical Record (FR1-8), Capture & Ingestion (FR9-19), Intelligence/Retrieval/Phase Management (FR20-33), User Surfaces (FR34-43), Override & Trust Management (FR44-48), Action Queue Lifecycle (FR49-52), Compliance/Evidence/Security & Audit (FR53-69), Identity/Tenancy/Access & Provisioning (FR70-79). The architecture must provide a substrate where every capability is implementable without violating the Design Philosophy commitments (DP1–DP12).

**Non-Functional Requirements:** 78 NFRs across 12 categories with explicit measurement conventions. Architecturally load-bearing:
- **NFR23 (tenant isolation):** shared-instance Postgres + per-tenant envelope encryption + RLS + mandatory tenant_id. Not separate-engine-per-tenant.
- **NFR25 (bifurcated R.O.T.):** V1 logical bifurcation — separate database clusters with separate encryption domains, shared control plane. Physical bifurcation V1.5+.
- **NFR1/NFR5 (latency & freshness):** In-Meeting Alert ≤ 8s p95; In-Meeting surface freshness ≤ 60s (binding constraint for backpressure).
- **NFR48 (Cartographer throughput):** ≤ 5 min p95 for 40-message thread or 60-minute transcript — **architecture mandates chunked-extract + map-reduce aggregate; monolithic extraction architecturally rejected.**
- **NFR50 (11th-call CI gate):** Zero hallucinated citations on per-release-candidate basis — requires rule-layer citation validator at agent output boundary.
- **NFR51 (replay-parity on LLM upgrades):** Citation-set-identical semantics gated in CI — requires full replay-parity harness.
- **NFR70 (LLM failover):** Primary + secondary LLM provider with ≤ 10 min switchover.
- **NFR14-19 (crypto):** FIPS 140-2 modules, AES-256 at rest, TLS 1.3+, RFC 3161 TSA for signed time.
- **NFR35/66 (residency):** Single US AWS region (us-east-2) V1.
- **NFR62-65 (supply chain):** SBOM (SPDX + CycloneDX), Sigstore/cosign signing, SLSA L2 V1 → SLSA L3 post-StateRAMP, CVE gating in CI.
- **NFR67/68 (dual topology):** Every V1 capability operates on shared-tenant AND self-hosted reference build; V1 self-hosted = docker-compose; Helm deferred V1.5.

**Design Philosophy:** 12 binding commitments. Architecturally significant:
- **DP3 (Symbiotic Posture):** No agent action has customer-visible consequence without human confirmation. Architecture has NO auto-commit-to-external-system code paths for customer-visible effects.
- **DP6 (Retrieval-Only In-Meeting; Generation in Evening):** In-meeting code path is retrieval-only; generation code path is separated and batch-only. Architectural separation, not a prompt-engineering boundary.
- **DP9 (Third-Bin Signal Retention):** Class B review queue is a first-class store, not a deletion-after-window pattern.

**Scale & Complexity:** **High complexity / compliance-native / regulated-customer / greenfield.** Primary technical domain: **full-stack AI platform** (Python services + Next.js web + Tauri desktop + Go CLI + Postgres substrate on AWS). Estimated architectural components: ~18 distinct services/packages in the monorepo.

### Technical Constraints & Dependencies

**Locked by PRD:**
- Single US AWS region (us-east-2) at V1
- Microsoft 365 Graph API + Teams transcription as primary ingestion integrations (FR9-11)
- Microsoft Entra ID as SAML/OIDC provider primary (FR71)
- One-OS edge-capture at V1, second at V1.5 (FR13) — founder-stack-determined, TBD
- FIPS 140-2 validated cryptographic modules (NFR14)
- docker-compose self-hosted reference build at V1 (NFR68)
- V1 resource envelope: 18–20 engineering-months with Option A/B/C resource path decision due M2

**Inherited from Party Mode architectural pre-decisions (already in PRD):**
- Cartographer chunked-extract + map-reduce aggregate (NFR48 rationale)
- Shared-instance Postgres + envelope encryption + RLS (NFR23 Party Mode revision)
- Logical R.O.T. bifurcation V1, physical V1.5+ (NFR25 revision)
- Availability targets: 99.0% V1 → 99.5% StateRAMP → 99.9% post-StateRAMP (NFR10)
- Expand-inline citation resolution default with "navigate to source" option (FR41)

### Cross-Cutting Concerns Identified

1. **Citation envelope enforcement** — every agent output, schema-validated at agent boundary by Control Plane. Shared `citation-envelope` package used by all agents.
2. **Tenant scoping** — every DB query, every S3 access, every cache lookup, every log line must carry tenant_id. Single enforcement library.
3. **Observability** — OpenTelemetry traces + structured logs + metrics, every request and every inter-agent call.
4. **Audit logging** — RFC 3161 signed time on every authorization decision, override event, break-glass session, FOIA export, kill-switch toggle.
5. **Replay-parity harness** — CI-runnable test suite with golden set; must operate against every LLM model-version upgrade.
6. **Schema contracts** — citation envelope, canonical-memory event node, tombstone, Action Queue, override-event all enforced in CI.
7. **Phase-gate awareness** — retrieval, ranking, and surface rendering all consume current phase state; single source-of-truth phase-state service.
8. **LLM provider abstraction** — primary/secondary failover; agents call through abstraction, not directly.

## Starter Template Evaluation

### Primary Technology Domain

**Polyglot monorepo.** Four distinct application runtimes (Python backend services, Next.js web frontend, Tauri desktop edge-capture agent, Go FOIA CLI) plus shared infrastructure. No single starter covers this; the decision is to operate a **pnpm + Turborepo-based monorepo** with per-workspace starters.

### Starter Options Considered

Evaluated: (a) pure Next.js SaaS starter (e.g., `t3-app`), (b) FastAPI full-stack template (tiangolo/full-stack-fastapi-template), (c) LangGraph template apps, (d) custom monorepo from scratch.

### Selected Approach: Monorepo with Per-Workspace Starters

**Rationale:** No single starter supports FastAPI + LangGraph + Tauri + Next.js + Go CLI in one repo; attempting to force-fit would lock us into premature decisions that violate our polyglot reality. Monorepo with per-workspace starters preserves workspace independence while enabling shared packages, unified CI/CD, and coordinated releases. Turborepo (or Nx) provides task-graph caching that offsets monorepo build overhead.

**Initialization Commands:**

```bash
# Root monorepo
pnpm init
pnpm add -D turbo@latest typescript@latest prettier@latest
# (turbo.json and pnpm-workspace.yaml authored directly)

# Web app
cd apps/web
pnpm create next-app@latest . --typescript --tailwind --eslint --app --src-dir --turbo

# Shadcn/ui init
pnpm dlx shadcn@latest init

# Edge agent (Tauri 2.x)
cd apps/edge-agent
pnpm create tauri-app@latest . --template react-ts

# FOIA CLI (Go)
cd apps/foia-cli
go mod init github.com/deployai/foia-cli

# Backend API services (FastAPI) — authored from reference pattern, not from a create-* tool
cd services/api && uv init  # (uv for fast Python dependency management)
```

**Architectural Decisions Provided by Each Starter:**

- **Next.js 16.x + React 19 + App Router + TypeScript + Tailwind v4 + ESLint + Turbopack:** modern React rendering model, React Server Components for dashboard shells (reducing JS bundle), Turbopack for build speed, `eslint-plugin-jsx-a11y` default-included (supports NFR28/41/42). Shadcn/ui initialization sets up Radix primitives, theme tokens, and dark-mode toggle.
- **Tauri 2.x + React + TypeScript:** capability-based permission model in `tauri.conf.json` (principle of least privilege), OS-native WebView (no bundled Chromium), Rust sidecar for FIPS crypto + local audio processing. Sparkle-compatible auto-updater plugin handles macOS; WinSparkle-equivalent for Windows.
- **Go FOIA CLI:** single static binary, cross-platform compile targets, easy Sigstore cosign signing, minimal runtime deps — ideal posture for government IT distribution (no JRE/Python dependency installs required on reviewer machines).
- **FastAPI + Pydantic v2 + SQLAlchemy 2.x async + Alembic:** authored directly from reference patterns (not from a single generator) because our service boundaries (ingest / cartographer / oracle / master-strategist / control-plane / replay-parity-harness) are domain-specific and don't match off-the-shelf starters. Uses `uv` for dependency management (fast, reproducible, locks `uv.lock`).

**First implementation story: "Initialize monorepo with empty workspaces + shared tooling"** — this is deferred to implementation phase; architecture document captures the scaffolding commands above.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Language/framework per workspace, versions verified
- Database engine + migration tool + tenant isolation mechanism
- LLM orchestration + retrieval frameworks
- Message queue / event bus
- Authentication + SSO integration path
- Infrastructure-as-code tool + AWS service map
- Edge-capture desktop framework

**Important Decisions (Shape Architecture):**
- Frontend state management patterns
- CI/CD pipeline + supply-chain security stack
- Observability stack
- Local dev experience (NFR77)

**Deferred Decisions (Post-V1):**
- Helm chart for self-hosted (NFR68 V1.5)
- Multi-region deployment topology (post-StateRAMP)
- Physical R.O.T. bifurcation (NFR25 V1.5+)
- OpenFGA / ReBAC migration (FR74/75 V1.5+)

### Data Architecture

**Database Engine:** **PostgreSQL 16.x** (verified current stable 2026), managed via **AWS RDS Multi-AZ** in us-east-2. Primary cluster for DeployAI observational derivatives (canonical memory event log, identity graph, solidified-learning library, Action Queue, User Validation Queue, annotations, phase state). Secondary cluster for customer-tenant artifacts (raw ingested events that map to customer's own data — emails, calendar, transcripts, uploaded files metadata). Logical R.O.T. bifurcation V1 per NFR25.

**ORM & Migrations:** **SQLAlchemy 2.x async** (Pydantic-compatible, declarative-2.0 style) + **Alembic** for migrations. Alembic migrations follow expand-contract pattern per NFR74; canonical-memory migrations additive-only (no in-place event-node mutation).

**Tenant Isolation Mechanism (implements NFR23):** Three-layer defense:
1. **Application layer:** Every SQLAlchemy session wraps in `TenantScopedSession` context manager that injects `tenant_id` filter into every `Query`. All repository methods require `tenant_id` parameter; unit-tested to reject missing tenant_id.
2. **Database layer:** Postgres Row-Level Security (RLS) policies on every canonical-memory table with `USING (tenant_id = current_setting('app.current_tenant')::uuid)`. Set via session-level `SET LOCAL app.current_tenant = '...'` inside the tenant-scoped session.
3. **Encryption layer:** Per-tenant Data Encryption Keys (DEKs) stored encrypted under AWS KMS Customer Master Key (CMK). Sensitive fields (evidence_span payload, private-scope annotations, raw transcripts) encrypted with tenant's DEK via pgcrypto + KMS envelope pattern. CI-gate fuzz harness (NFR52-bound) attempts cross-tenant reads and fails CI on any success.

**Vector Retrieval:** **pgvector** extension (HNSW index) on canonical memory for similarity-adjacent queries. **Not used for primary retrieval** (per FR22 retrieval is phase-gated, not similarity-based); used only for secondary lookup when learning cards surface related historical evidence. LlamaIndex wraps pgvector as its vector store backend, ensuring retrieval flows through citation-aware adapter.

**Object Storage:** **AWS S3** (us-east-2) with AES-256 SSE-KMS for:
- FOIA export bundles (time-limited presigned URLs for download)
- Raw uploaded meeting transcripts/recordings (encrypted, time-versioned, deleted per retention contract per NFR33)
- Edge-agent backups and crash-dump artifacts (user-consented telemetry only, DP3/DP12 compliant)
- CI/CD artifact staging (pre-signed, pre-distribution)

**Caching:** **AWS ElastiCache Redis** in a single cluster (multi-AZ) for:
- Phase state cache (read-heavy; invalidated on phase transition)
- Identity graph hot-path lookup cache (read-through with 5-min TTL aligned to NFR5)
- Authorization decision cache (fail-closed; TTL 60s)
- Rate-limit counters (integration backpressure per FR19/NFR12)

**Cache tenancy:** Redis keys prefixed with `tenant:<uuid>:` (enforced via wrapper library). Redis AUTH + TLS 1.3 in transit.

**Secrets:** **AWS Secrets Manager** (90-day auto-rotation for KMS data keys per NFR76; per-integration-provider rotation for OAuth refresh tokens).

**Authentication & Session:** Redis-backed session store with signed-JWT tokens (15-min access TTL, 7-day refresh). SAML/OIDC via Microsoft Entra ID (FR71).

### Authentication & Security

**SSO:** **Microsoft Entra ID primary** via SAML 2.0 or OIDC (FR71). SCIM 2.0 for provisioning (FR71). Library: `python-jose[cryptography]` + `authlib` for OIDC validation; `python3-saml` for SAML assertions.

**Authorization:** **Postgres Row-Level Security + application-layer role checks** at V1. Tenant-scoped role matrix: `deployment_strategist`, `successor_strategist` (V1.5 active), `platform_admin`, `customer_records_officer` (CLI-only), `external_auditor` (JIT, time-boxed), `customer_admin` (V1.5 active). Future migration to OpenFGA / ReBAC deferred to V1.5+; architecture decision documents the migration contract (authorization decisions served through `AuthzResolver` interface that can swap RLS backend for ReBAC without touching service code).

**Crypto Modules:** **FIPS 140-2 validated** OpenSSL FIPS provider on all Linux services (Amazon Linux 2023 with FIPS module enabled); **AWS KMS** for key custody (FIPS 140-2 validated). TLS 1.3+ enforced at ALB + service-to-service mesh.

**Signed Time:** **RFC 3161 TSA** via **FreeTSA + AWS-backed fallback** — implementation uses `rfc3161-client` Python library with primary TSA endpoint FreeTSA.org (independent public trust chain per NFR19) and AWS-native TSA as fallback. Signed timestamps applied on: canonical-memory event-node writes (batched every 5s to amortize TSA cost), audit log entries, FOIA export bundles.

**Tamper Evidence (edge agent, NFR20):** Tauri edge agent produces local transcripts signed with a per-device signing key (hardware-backed via macOS Keychain / Windows DPAPI). Signature + RFC 3161 timestamp verifiable offline using the open-source FOIA CLI, no DeployAI services required.

**Break-Glass Access (FR64/NFR21/NFR22):** Platform Admin privileged-override implemented via **AWS IAM Identity Center session** gated by:
- Dual-approval (two independent authenticated users, both hardware-backed MFA)
- Customer Security-contact notification via pre-registered webhook + email; 15-minute objection window for non-emergency
- Session auto-expiry ≤ 4 hours
- Full session transcript captured (ssm session manager recording to S3) and delivered post-hoc

### API & Communication Patterns

**External API:** **REST + OpenAPI 3.1** (FastAPI auto-generates spec), JSON over HTTPS. Government procurement familiarity with REST > GraphQL; OpenAPI 3.1 spec is first-class deliverable for compliance/audit (Paige flagged documentation-as-product).

**Error Format:** **RFC 7807 Problem Details** for all error responses (`application/problem+json`) — IETF-standard, government-friendly, unambiguous.

**Date/Time:** **ISO 8601 UTC with Z suffix** in all API payloads and database storage. Frontend converts to strategist-local time for display (per NFR2/NFR3). All NFR measurements use calendar month UTC per Measurement Conventions.

**Rate Limiting:** Token-bucket per-tenant-per-endpoint using Redis; returns `429 Too Many Requests` with `Retry-After` header. Integration-pull backpressure separately implemented per FR19/NFR12.

**Service-to-Service Communication:** **HTTPS REST** for synchronous (service mesh via AWS App Mesh or Envoy sidecar — decision deferred to architecture Step 6 implementation). **AWS SQS + EventBridge** for asynchronous.

**Message/Event Bus:**
- **SQS (standard queues, SSE-KMS)** for work queues (ingestion work, Cartographer extraction jobs, evening-synthesis jobs) — dead-letter queues for every work queue.
- **EventBridge** for event fan-out (canonical-memory event-node-appended events, phase-transition events, override-submitted events) — multiple downstream consumers (Oracle, Master Strategist, replay-parity harness, audit log).

**LLM Orchestration:** **LangGraph** for agent workflows — stateful graphs with checkpointing (Postgres-backed checkpoints) enable replay-parity per NFR51. Every Cartographer / Oracle / Master Strategist pipeline is a LangGraph state machine. LangSmith deferred V1 (self-hosted tracing via OpenTelemetry at V1; LangSmith evaluation loop revisit post-StateRAMP).

**LLM Retrieval:** **LlamaIndex** wrapping pgvector + canonical-memory — exposed to LangGraph agents as tools. **Custom citation-aware adapter** wraps LlamaIndex responses so every retrieval output carries `{node_id, graph_epoch, evidence_span, retrieval_phase, confidence_score}` per citation envelope contract (FR27). Contract enforced at the LangGraph-LlamaIndex boundary (rejected outputs bubble up as agent errors, not customer-visible hallucinations).

**LLM Providers (implements NFR70):**
- **Primary:** Anthropic Claude Sonnet 4 class (or current stable) via official `anthropic` SDK.
- **Secondary:** OpenAI GPT-4o class via `openai` SDK.
- Provider abstraction: `LLMProvider` interface with `chat_complete`, `embed`, `capabilities` methods. Agents never import provider SDKs directly. Switchover ≤ 10 min via config flag; capability-parity matrix stored in `services/config/llm-capability-matrix.yaml` and validated in CI.

### Frontend Architecture

**Framework:** **Next.js 16.x (App Router) + React 19**, React Server Components for dashboard shells (reduces client JS bundle, supports NFR28 accessibility by keeping semantic HTML server-rendered).

**Styling:** **Tailwind CSS v4 (Oxide engine)** + **shadcn/ui** (Radix primitives). Radix provides keyboard navigation, focus management, ARIA attributes — direct support for NFR41 (keyboard equivalence) and NFR42 (WAI-ARIA semantic structure).

**Component Library:** shadcn/ui for base UI; **TanStack Table v8** for Phase & Task Tracking tables and Action Queue views (accessible table markup for large datasets); **Recharts** or **Tremor** deferred for V1.5 (Timeline surface).

**State Management:**
- **TanStack Query (React Query v5)** for server state — caching, invalidation, optimistic updates, retry logic. Pairs with NFR5 surface freshness SLOs.
- **Zustand** for local UI state (modal visibility, form drafts, ephemeral selection state). Lighter weight than Redux; no provider wrapping needed.

**Routing:** Next.js App Router (file-system-based). Per-surface routes: `/digest`, `/in-meeting/:meeting_id`, `/phase-tracking`. Citation deep-links: `/evidence/:node_id` with `expand-inline` component default (FR41).

**Performance:**
- Server Components for dashboard shells and static content.
- Client Components only for interactive surfaces.
- Dynamic imports (`next/dynamic`) for heavy components (charts, Timeline V1.5).
- `axios` or `fetch` with Suspense + Error Boundaries.
- Bundle analysis in CI (`@next/bundle-analyzer`) with per-surface budget limits.

**Accessibility enforcement:**
- `eslint-plugin-jsx-a11y` at `error` level in ESLint config (CI blocker).
- Storybook + `@storybook/addon-a11y` for component-level axe-core checks.
- Playwright E2E tests including screen-reader assertions via `axe-playwright`.
- Top-5 V1 journey a11y scripts authored per NFR40 (screen-reader task-completion parity ≤ 1.5× sighted).

### Infrastructure & Deployment

**Cloud Provider:** **AWS** (us-east-2 primary, multi-AZ) at V1. Choice rationale: FedRAMP-authorized regions, StateRAMP familiarity, AWS KMS FIPS 140-2 validation, AWS Marketplace for cooperative purchasing path per NFR69.

**Compute:** **AWS ECS Fargate** for all services (API, ingestion workers, agent runtimes). ECS chosen over EKS because single-founder-to-small-team ops capacity cannot absorb Kubernetes control-plane complexity at V1 (matches Amelia's NFR10 concerns from Party Mode). Each service = Fargate task with autoscaling on CPU/memory. ECS task definitions in Terraform.

**Load Balancer:** **AWS ALB** with TLS 1.3 termination, AWS WAF for common-attack filtering. PrivateLink endpoints offered to enterprise customers per NFR26.

**IaC:** **Terraform (HCL)** managed by **Terragrunt** for environment-specific wiring. State in S3 with DynamoDB lock. Government procurement familiarity; broad gov-adoption.

**CI/CD:** **GitHub Actions** with:
- **Syft** for SBOM (SPDX + CycloneDX output) per NFR62
- **Cosign/Sigstore** for artifact signing per NFR63
- **SLSA Level 2 provenance** via `slsa-github-generator` at V1; SLSA L3 post-StateRAMP per NFR64
- **Grype + Dependabot** for CVE scanning (CI-blocking on critical, review-gate on high) per NFR65
- **pytest + Playwright + Go test** parallelized with per-language matrices
- **Replay-parity harness** as CI job triggered on LLM-model-config change
- **11th-call test** as required CI gate on merge to `main` per NFR50

**Deploy model:** Blue/green via ECS with ALB target-group switchover. Canary ≤ 10% traffic on agent-layer or citation-assembler changes per NFR75. Feature flags via **Unleash OSS** (self-hostable, no SaaS vendor lock-in; Unleash supports per-tenant flag evaluation).

**Observability:**
- **OpenTelemetry SDK** instrumentation in all services (traces + metrics + logs unified).
- **OTel Collector** shipping to:
  - **Grafana Tempo** for distributed traces (30-day retention per NFR58)
  - **Grafana Loki** for structured logs (tenant-scoped label indexing)
  - **Prometheus + Grafana Mimir** for metrics (long-term retention)
- **Grafana OnCall** for incident paging (Sev-1 15-min response per NFR60).
- **AWS CloudWatch** as backup metrics path (redundancy for AWS-native alerts).
- **Structured audit log** emitted to separate immutable S3 bucket with Object Lock (compliance retention per NFR34; 7-year immutable).

**Self-hosted reference build (NFR67/68):** `docker-compose.yml` in `infra/compose/` bringing up:
- Postgres (with pgvector + pgcrypto extensions preinstalled)
- Redis
- MinIO (S3-compatible local object store)
- All DeployAI services
- Optional local FreeTSA stub for air-gapped demos
- Grafana + Prometheus + Loki + Tempo for observability
- Runnable in ≤ 1 engineering-day per NFR68.

### Decision Impact Analysis

**Implementation Sequence (aligned with PRD §Build Sequence weeks 1-24):**

1. **Weeks 1-2:** Monorepo scaffold, pnpm + Turborepo + Terraform root stack, AWS bootstrap (us-east-2 multi-AZ, KMS keys, VPC, Secrets Manager).
2. **Weeks 3-4:** Canonical memory substrate (Postgres + pgvector schema + envelope encryption + RLS policies + tombstone tables + Alembic migrations). **FOIA substrate FIRST** per PRD Winston ordering.
3. **Weeks 5-6:** Citation envelope schema + Pydantic contracts + schema contract tests. Seeded synthetic 11th-call fixture + CI gate.
4. **Weeks 7-8:** M365 Graph API + Teams transcription ingestion (SQS work queues, retry/backoff, tenant-scoped writes).
5. **Weeks 8-10:** **Replay-parity Spike-1** — LangGraph checkpointing + LlamaIndex citation-aware adapter + replay-parity harness against Llama 3→3.1 on HotpotQA public benchmark.
6. **Weeks 10-14:** Cartographer + Oracle LangGraph agents against retrieval contract validated by Spike-1. Chunked-extract + map-reduce for Cartographer per NFR48.
7. **Weeks 14-16:** 7-phase state machine + Master Strategist (internal arbitration, no UI).
8. **Weeks 16-20:** Three V1 surfaces (Next.js web app — Morning Digest, In-Meeting Alert persistent-card, Phase-Tracking) with continuity-of-reference contract tests per NFR52.
9. **Weeks 18-22:** Tauri edge-capture agent (macOS primary V1), Sparkle auto-updater, Sigstore-signed, kill-switch tuple per FR14.
10. **Month 4:** Replay-parity Spike-2 on NYC DOT traces; adjust semantics commitment if needed.
11. **Month 5:** docker-compose reference build + Helm chart deferred; Go FOIA CLI; VPAT scripting.
12. **Month 6:** Section 508 VPAT, Anchor ship readiness, SOC 2 Type I scoping begins.

**Cross-Component Dependencies:**

- Canonical memory substrate is **upstream** of everything — must ship weeks 3-4 or nothing else is testable.
- Citation envelope contract tests are **upstream** of agent runtimes — agents cannot emit without contract validation.
- Replay-parity harness **gates** every LLM upgrade forever (NFR51) — must be operational before the first LLM upgrade cycle in production.
- Edge agent **depends on** citation envelope schema (offline verifier needs same schema).
- Self-hosted reference build **depends on** every service shipping with a well-defined docker-compose entry (no AWS-only dependencies in service images).
- Tenant isolation three-layer defense must be **tested before** multi-tenant data starts flowing (week 4 at latest).

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Database Naming:**
- Tables: `snake_case plural` (e.g., `canonical_memory_events`, `solidified_learnings`, `action_queue_items`).
- Columns: `snake_case` (e.g., `tenant_id`, `created_at`, `evidence_span`).
- Primary keys: `id` (UUID v7) unless cross-table unique (`event_node_id`).
- Foreign keys: `<referenced_table_singular>_id` (e.g., `tenant_id`, `strategist_id`).
- Indexes: `idx_<table>_<columns>` (e.g., `idx_canonical_memory_events_tenant_id_created_at`).
- RLS policies: `tenant_rls_<table>`.

**API Naming (REST endpoints):**
- Resource paths: `plural snake_case` in URL, `/api/v1/<resource>` (e.g., `/api/v1/action_queue_items`, `/api/v1/solidified_learnings`).
- Resource IDs: `{resource_id}` path parameter (e.g., `/api/v1/canonical_events/{event_id}`).
- Action endpoints: verb-based sub-path (e.g., `POST /api/v1/override_events/{override_id}/submit`).
- Query parameters: `snake_case` (e.g., `?phase=integration&sort=-created_at`).

**Code Naming:**
- **Python:** `snake_case` for functions, variables, modules; `PascalCase` for classes; `UPPER_SNAKE` for constants.
- **TypeScript:** `camelCase` for functions, variables; `PascalCase` for types, components; `UPPER_SNAKE` for constants.
- **Rust (Tauri backend):** Rust idiomatic (`snake_case` for functions/modules, `PascalCase` for types).
- **Go (FOIA CLI):** Go idiomatic (`MixedCaps`, exported capitalized).
- **Filenames:** `kebab-case` for TypeScript (`user-card.tsx`, `citation-envelope.ts`); `snake_case.py` for Python; Rust/Go per language convention.
- **React components:** `PascalCase.tsx` file + `PascalCase` export; one component per file.

### Structure Patterns

**Monorepo Organization:**
- Workspaces under `apps/` (deployable user-facing), `services/` (deployable backend), `packages/` (shared libraries, non-deployable), `infra/` (IaC), `tests/` (cross-workspace test harnesses), `docs/` (product documentation).
- Tests co-located with source for unit (`*.test.ts`, `test_*.py`); integration tests in `tests/integration/` within each workspace; E2E tests in top-level `tests/e2e/`.

**File Structure (per service):**
```
services/<service-name>/
├── pyproject.toml                # Python dependency manifest
├── uv.lock                       # Lockfile
├── Dockerfile
├── src/<service_name>/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry
│   ├── api/                      # HTTP routes
│   │   ├── routes/
│   │   └── middleware/
│   ├── domain/                   # Domain logic (pure, no IO)
│   ├── repositories/             # Data-access layer
│   ├── services/                 # Business logic
│   ├── agents/                   # LangGraph state graphs (if agent service)
│   ├── schemas/                  # Pydantic models
│   └── config/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── README.md
```

### Format Patterns

**API Response Format:**
- Success: direct JSON object (no wrapper) for resource GETs: `{ "id": "...", "created_at": "...", ... }`.
- Success list responses: wrapped with pagination: `{ "items": [...], "pagination": { "cursor": "...", "has_more": bool } }`.
- Error: **RFC 7807 Problem Details**: `{ "type": "https://deployai.app/problems/invalid-tenant", "title": "Invalid Tenant", "status": 403, "detail": "...", "instance": "/api/v1/...", "trace_id": "..." }`.
- All responses include `X-Request-Id` and `X-Tenant-Id` headers (latter echoed, not authoritative).

**Data Exchange Format:**
- **JSON everywhere**; no binary-over-REST (binary artifacts via S3 presigned URLs).
- **Field naming: `snake_case` in API JSON** (matches DB; minimizes transform). Frontend does ONE conversion layer (TanStack Query `select` or API client mapper) to `camelCase` for component-level use where desired. Trade-off accepted: gov-procurement JSON consumers prefer `snake_case`; internal FE convenience achieved via single mapper, not everywhere.
- Dates: **ISO 8601 UTC strings with Z suffix**. No epoch timestamps in APIs.
- Booleans: `true` / `false`. Never `0/1` or `"yes"/"no"`.
- Null handling: explicit `null` (not omitted field) for intentionally-absent values; omit for not-yet-queried.
- UUIDs: **UUID v7** (time-ordered, K-sortable) for all entity IDs. Better index performance than v4.

### Communication Patterns

**Event System:**
- Event names: `<domain>.<entity>.<action>` snake_case (e.g., `memory.event.appended`, `action_queue.item.resolved`, `override.event.submitted`, `phase.transition.proposed`).
- Event payload: **canonical event envelope** `{ event_id: UUID, event_name: str, event_version: semver, tenant_id: UUID, occurred_at: ISO8601, trace_id: str, payload: object }`.
- Event versioning: **semver in `event_version`**; consumers handle ≥ 1 prior version; breaking changes bump major + 1-release grace period.
- Async: via SQS (work) + EventBridge (fan-out).
- Retry: exponential backoff per NFR12 (base 2s, max 5 min); DLQ after 5 attempts; DLQ alerting via CloudWatch Alarm.

**State Management (frontend):**
- Server state via **TanStack Query**; queries keyed by `[resource, tenant_id, ...filters]`.
- Mutations with optimistic updates where safe; invalidate-on-success for authoritative data (Digest, Phase-Tracking).
- Local UI state via **Zustand** stores per feature domain.
- No prop-drilling beyond 2 levels; use context or Zustand.

### Process Patterns

**Error Handling:**
- **Backend:** Domain exceptions raised; converted to RFC 7807 Problem Details via FastAPI exception handlers. All exceptions logged with `trace_id`.
- **Frontend:** React Error Boundaries at route level; graceful degradation for agent-outage state per NFR11/FR46 (show memory-only view with explicit agent-error badge).
- **User-facing messages:** Plain English, no stack traces; link to status page for Sev-1 context.

**Loading States:**
- Per-surface skeleton states (not spinners) for dashboard loads.
- Memory-syncing glyph per FR48 when surface staleness exceeds NFR5 thresholds.
- Empty states with guidance text for zero-result views per FR43 (every active surface).

**Citation Envelope Enforcement (critical pattern):**
```
Control Plane receives agent output → validates envelope schema (Pydantic) →
validates node_id resolves in canonical memory at graph_epoch →
validates citation is phase-appropriate →
emits output to surface OR rejects with structured agent-error log.
```
This is **the enforcement point** for DP6 (retrieval-only in-meeting) and NFR50 (zero hallucinated citations). Tested exhaustively in 11th-call CI gate.

**Replay-Parity Harness Pattern:**
```
Golden set (≥ 200 queries, frozen per release) →
Run against candidate model version → capture citation set →
Compare to reference citation set (citation-set-identical semantics at V1) →
Pass: ≥ rule-layer threshold; LLM-judge secondary cascade; human adjudication tertiary.
```

### Enforcement Guidelines

**All AI Agents MUST:**
- Emit outputs through the citation envelope Pydantic model; outputs missing required fields are rejected at the agent boundary by Control Plane (FR27, DP2).
- Never auto-execute customer-visible actions without human confirmation (DP3).
- Operate in retrieval-only mode during in-meeting capture; generation only in Evening Synthesis (DP6).
- Never paraphrase the trigger utterance in learning-card rendering (DP5).
- Surface null-result retrieval explicitly when no phase-appropriate evidence exists (FR24).

**Pattern Enforcement:**
- Pre-commit hooks (husky for TS, pre-commit for Python) run formatters + linters on staged files.
- CI blocks merge on linter/formatter failures.
- Schema contract tests block merge on violations.
- Naming convention violations caught by custom ESLint rules + ruff Python rules.

### Anti-Patterns (Explicitly Forbidden)

- **Raw SQL that bypasses tenant-scoped session.** Tests MUST fail if raw `execute()` is called without `TenantScopedSession` context.
- **LLM SDKs imported outside the provider abstraction.** `import anthropic` or `import openai` outside `services/common/llm_providers/` is a CI-lint failure.
- **Agent output emitted without citation envelope.** Schema contract test is CI-blocking.
- **Cross-tenant reads in production code.** Fuzz harness runs nightly; any success → incident.
- **Prescriptive phrasing in agent-generated text** (DP2). Rule-based linter on agent prompts + outputs flags "say this," "tell them," "you should" patterns.
- **Timeline surface as V1.** Hard-coded as V1.5 feature flag; attempting to render without flag throws.
- **Master Strategist UI at V1.** Internal-only per DP10; rendering attempt throws.
- **Physical R.O.T. separation at V1.** V1 is logical only per NFR25; attempting dual-control-plane deploy fails IaC validation.

## Project Structure & Boundaries

### Complete Project Directory Structure

```
deployai/
├── README.md
├── pnpm-workspace.yaml
├── turbo.json
├── package.json
├── .nvmrc
├── .python-version
├── pre-commit-config.yaml
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                          # Per-workspace test matrix
│   │   ├── release.yml                     # Blue/green deploy with SLSA L2
│   │   ├── replay-parity-gate.yml          # NFR51 gate on LLM config change
│   │   ├── 11th-call-gate.yml              # NFR50 required gate
│   │   ├── sbom-sign.yml                   # SBOM + Sigstore per release
│   │   └── dependency-scan.yml             # Grype + Dependabot per NFR65
│   └── CODEOWNERS
├── apps/
│   ├── web/                                # Next.js 16 frontend (FR34-43)
│   │   ├── src/
│   │   │   ├── app/                        # App Router routes
│   │   │   │   ├── (auth)/                 # Login, SSO callback
│   │   │   │   ├── digest/                 # Morning Digest surface
│   │   │   │   ├── in-meeting/[meeting_id]/# In-Meeting Alert persistent-card
│   │   │   │   ├── phase-tracking/         # Phase & Task Tracking
│   │   │   │   ├── evidence/[node_id]/     # Citation deep-link expand-inline
│   │   │   │   ├── validation-queue/       # User Validation Queue (FR33)
│   │   │   │   ├── review/                 # Solidification review queue
│   │   │   │   ├── overrides/              # Override review history
│   │   │   │   └── layout.tsx
│   │   │   ├── components/
│   │   │   │   ├── ui/                     # shadcn primitives
│   │   │   │   ├── features/
│   │   │   │   │   ├── digest/
│   │   │   │   │   ├── in-meeting-alert/
│   │   │   │   │   ├── phase-tracking/
│   │   │   │   │   ├── citation/           # Envelope, chip, expand-inline
│   │   │   │   │   └── action-queue/
│   │   │   │   └── layouts/
│   │   │   ├── lib/
│   │   │   │   ├── api-client.ts
│   │   │   │   ├── auth.ts
│   │   │   │   ├── tanstack-query-config.ts
│   │   │   │   └── telemetry.ts
│   │   │   ├── hooks/
│   │   │   ├── stores/                     # Zustand
│   │   │   └── types/
│   │   ├── tests/
│   │   │   ├── e2e/                        # Playwright + axe-playwright
│   │   │   └── unit/                       # Vitest
│   │   ├── public/
│   │   ├── next.config.ts
│   │   ├── tailwind.config.ts
│   │   ├── components.json                 # shadcn config
│   │   └── package.json
│   ├── edge-agent/                         # Tauri 2.x desktop agent (FR13, NFR20)
│   │   ├── src/                            # React + TS frontend
│   │   ├── src-tauri/                      # Rust backend
│   │   │   ├── src/
│   │   │   │   ├── main.rs
│   │   │   │   ├── transcription.rs        # Local audio capture
│   │   │   │   ├── signing.rs              # FIPS-compat signing
│   │   │   │   ├── kill_switch.rs          # FR14 remote disable
│   │   │   │   └── updater.rs              # Sparkle/WinSparkle
│   │   │   ├── tauri.conf.json             # Capability allowlist
│   │   │   └── Cargo.toml
│   │   └── package.json
│   └── foia-cli/                           # Go FOIA verification CLI (FR61, NFR29)
│       ├── cmd/foia/main.go
│       ├── pkg/
│       │   ├── verify/                     # Signature + timestamp + chain-of-custody verify
│       │   ├── envelope/                   # Citation envelope schema (Go port)
│       │   └── export/                     # Export bundle format
│       ├── go.mod
│       ├── go.sum
│       └── README.md                       # Verifier instructions (public)
├── services/                               # Python backend services
│   ├── api-gateway/                        # Public REST API (FastAPI)
│   │   ├── src/api_gateway/
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py                 # Entra ID SAML/OIDC
│   │   │   │   ├── tenant_scope.py         # RLS session injector
│   │   │   │   ├── rate_limit.py
│   │   │   │   └── telemetry.py
│   │   │   └── config/
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── canonical-memory/                   # Event log + identity graph + learnings (FR1-8)
│   │   └── src/canonical_memory/
│   │       ├── event_log.py
│   │       ├── identity_graph.py
│   │       ├── learning_library.py
│   │       ├── tombstone.py
│   │       ├── action_queue.py
│   │       ├── validation_queue.py
│   │       └── retention_enforcer.py       # FR8
│   ├── ingest/                             # Ingestion pipeline (FR9-19)
│   │   └── src/ingest/
│   │       ├── m365_graph.py
│   │       ├── teams_transcripts.py
│   │       ├── voice_upload.py
│   │       ├── edge_agent_sync.py
│   │       ├── triage.py                   # Mission-relevance gate (FR15)
│   │       ├── throttling.py               # FR19 backpressure
│   │       └── kill_switch.py              # FR17
│   ├── cartographer/                       # Extraction agent (FR20, NFR48)
│   │   └── src/cartographer/
│   │       ├── graph.py                    # LangGraph state machine
│   │       ├── chunked_extract.py          # NFR48 map-reduce
│   │       ├── identity_resolution.py
│   │       ├── blocker_detection.py
│   │       └── re_extraction.py            # Override-triggered
│   ├── oracle/                             # Retrieval/surface agent (FR21-25)
│   │   └── src/oracle/
│   │       ├── graph.py                    # LangGraph state machine
│   │       ├── phase_gated_retrieval.py    # FR22, NFR53
│   │       ├── digest_composer.py          # FR34
│   │       ├── in_meeting_alert.py         # FR36, NFR1
│   │       ├── evening_synthesis.py        # FR35
│   │       ├── corpus_confidence.py        # FR24
│   │       └── null_result.py              # FR24
│   ├── master-strategist/                  # Integration agent (FR26, DP10)
│   │   └── src/master_strategist/
│   │       ├── graph.py
│   │       ├── arbitration.py
│   │       ├── action_queue_ranking.py
│   │       ├── phase_transition_proposal.py
│   │       └── validation_escalation.py
│   ├── control-plane/                      # Admin, authz, audit, compliance (FR14, FR17, FR64-68)
│   │   └── src/control_plane/
│   │       ├── authz.py                    # RLS + ReBAC-ready abstraction
│   │       ├── audit_log.py                # RFC 3161 signed, immutable
│   │       ├── break_glass.py              # NFR21/22
│   │       ├── kill_switch.py              # FR14/17 (consolidated)
│   │       ├── schema_evolution.py         # FR76
│   │       ├── retention_jobs.py           # FR8
│   │       ├── provisioning.py             # FR70, FR71
│   │       └── observability.py            # NFR57-59 emitters
│   ├── foia-export/                        # FOIA export bundle builder (FR60, NFR29, NFR38)
│   │   └── src/foia_export/
│   │       ├── bundle_builder.py
│   │       ├── tombstone_resolver.py       # FR5, NFR38
│   │       ├── signed_bundle.py            # RFC 3161 + chain-of-custody
│   │       └── cli_interface.py            # Exposes to Go FOIA CLI
│   └── replay-parity-harness/              # NFR51 test infrastructure
│       └── src/replay_parity/
│           ├── golden_set_loader.py
│           ├── citation_set_comparator.py
│           ├── rule_layer.py
│           ├── llm_judge.py
│           └── human_adjudication_queue.py
├── packages/                               # Shared cross-workspace libraries
│   ├── citation-envelope/                  # Pydantic schema + Go + TS ports
│   │   ├── python/
│   │   ├── typescript/
│   │   ├── go/
│   │   └── schema.json                     # Canonical JSON Schema
│   ├── canonical-memory-primitives/        # Python (used by all agents)
│   ├── llm-provider-abstraction/           # Python (anthropic + openai wrappers)
│   ├── tenant-scope/                       # Python (SQLAlchemy session wrapper)
│   ├── shared-ui/                          # Shared React components (shadcn extensions)
│   ├── design-tokens/                      # Tailwind theme tokens (a11y palette)
│   └── event-contracts/                    # Event payload schemas (JSON Schema + generated TS/Py/Go types)
├── infra/
│   ├── terraform/
│   │   ├── modules/
│   │   │   ├── vpc/
│   │   │   ├── rds/                        # Postgres primary + customer-tenant cluster
│   │   │   ├── ecs-fargate/
│   │   │   ├── alb/
│   │   │   ├── kms/
│   │   │   ├── s3-audit-immutable/
│   │   │   ├── sqs-eventbridge/
│   │   │   ├── elasticache-redis/
│   │   │   └── iam-identity-center/
│   │   ├── environments/
│   │   │   ├── dev/
│   │   │   ├── staging/
│   │   │   └── prod-us-east-2/
│   │   └── terragrunt.hcl
│   ├── compose/                            # NFR68 self-hosted reference build
│   │   ├── docker-compose.yml
│   │   ├── .env.example
│   │   ├── init-scripts/
│   │   │   └── postgres-init.sql           # pgvector + pgcrypto + seed RLS
│   │   └── README.md                       # "Up in ≤ 1 eng-day" instructions
│   └── helm/                               # V1.5 deferred
│       └── PLACEHOLDER.md
├── tests/
│   ├── 11th-call/                          # NFR50 CI gate
│   │   ├── golden_set/
│   │   ├── fixtures/
│   │   └── harness.py
│   ├── continuity-of-reference/            # NFR52 contract tests
│   │   ├── same_node_resolution.test.ts
│   │   ├── visual_token_parity.test.ts
│   │   ├── context_neighborhood.test.ts
│   │   └── state_propagation.test.ts
│   ├── phase-retrieval-matrix/             # NFR53 21-cell audit
│   │   └── phase_retrieval_matrix.py
│   ├── tenant-isolation-fuzz/              # NFR23 cross-tenant attempt suite
│   │   └── fuzz_harness.py
│   └── e2e-user-journeys/                  # Playwright + axe-playwright
│       ├── journey-1-morning-digest/
│       ├── journey-2-in-meeting-retrieval/
│       ├── journey-7-trust-repair-override/
│       └── journey-9-offboarding-cascade/
├── docs/                                   # DP7 Documentation-as-Product
│   ├── compliance-architecture-brief.md    # PRD Innovation §2
│   ├── glossary.md                         # PRD Domain §11
│   ├── vpat.md                             # Section 508 VPAT (NFR28)
│   ├── ranking-spec.md                     # Oracle ranking details (FR22)
│   ├── deployment-framework.md             # 7-phase open methodology
│   ├── self-hosted-install.md              # NFR68
│   ├── foia-verifier-guide.md              # For customer verifiers
│   ├── llm-capability-matrix.yaml          # NFR70
│   └── security-architecture.md
└── scripts/
    ├── seed-golden-set.py
    ├── rotate-kms-keys.sh
    └── run-replay-parity.sh
```

### Architectural Boundaries

**API Boundaries:**
- **Public REST API (api-gateway):** sole external ingress for web app + Tauri edge agent + external integrations. All authorization checks terminate here.
- **Internal service mesh:** services behind ALB; service-to-service HTTPS with mTLS via AWS App Mesh. No service directly reachable from public internet.
- **FOIA CLI ↔ foia-export service:** authenticated RPC via presigned URL; CLI never holds DB credentials.

**Component Boundaries:**
- **Frontend ↔ Backend:** REST JSON only. No GraphQL, no WebSockets at V1 (In-Meeting Alert is pull-based polling with ≤ 5s interval during active meetings — lightweight).
- **Agent ↔ Control Plane:** agent outputs pass through Control Plane validator (citation envelope, authorization, phase-appropriateness) before reaching surfaces.
- **Cartographer / Oracle / Master Strategist:** no direct inter-agent calls; all coordination via Master Strategist arbitration and EventBridge events.

**Service Boundaries:**
- **Ingest ↔ Canonical Memory:** ingest writes only via canonical-memory library (never direct DB). Atomicity enforced at library boundary.
- **Agents ↔ LLM Provider:** agents call through `LLMProvider` abstraction (`services/common/llm_providers/`); direct SDK imports anywhere else = CI failure.
- **Retention jobs ↔ Customer data:** retention jobs touch customer-tenant cluster ONLY for destruction; read-path is DeployAI-derivatives-cluster only.

**Data Boundaries:**
- **DeployAI derivatives cluster (primary):** canonical memory event log, identity graph, learning library, Action Queue, overrides, phase state, audit log.
- **Customer-tenant artifacts cluster (secondary):** raw ingested events mapped to customer's originating data (email bodies, transcripts, attachments metadata). Separate encryption domain, separate failure domain, separate backup policy per NFR25.
- **S3 immutable audit bucket:** Object Lock enabled, Legal Hold for 7-year retention per NFR34. No delete path outside AWS console break-glass.
- **S3 FOIA export bucket:** presigned URLs with 72-hour expiry; cleanup job after download confirmation.

### Requirements to Structure Mapping

**Epic/Feature → Component Mapping:**

| PRD FR Category | Primary Component(s) |
|---|---|
| FR1-8 Memory & Canonical Record | `services/canonical-memory/`, `packages/canonical-memory-primitives/` |
| FR9-19 Capture & Ingestion | `services/ingest/`, `apps/edge-agent/` |
| FR20-33 Intelligence / Retrieval / Phase | `services/cartographer/`, `services/oracle/`, `services/master-strategist/` |
| FR34-43 User Surfaces | `apps/web/` |
| FR44-48 Override & Trust | `apps/web/src/app/overrides/`, `services/canonical-memory/src/canonical_memory/overrides.py` |
| FR49-52 Action Queue Lifecycle | `services/canonical-memory/action_queue.py`, `apps/web/src/app/digest/`, `apps/web/src/app/phase-tracking/` |
| FR53-69 Compliance / Evidence / Security / Audit | `services/control-plane/`, `services/foia-export/`, `apps/foia-cli/` |
| FR70-79 Identity / Tenancy / Access | `services/control-plane/provisioning.py`, `services/api-gateway/middleware/auth.py`, `infra/terraform/modules/iam-identity-center/` |

**Cross-Cutting Concerns:**
- **Citation envelope** → `packages/citation-envelope/` (language ports: Python, Go, TypeScript) — referenced by every agent, every surface, every CLI.
- **Tenant scoping** → `packages/tenant-scope/` (Python) — imported by every service repository/query.
- **LLM provider abstraction** → `packages/llm-provider-abstraction/` — imported by every agent.
- **Event contracts** → `packages/event-contracts/` — single source of truth for event schemas; generated types for each language.
- **Observability** → OpenTelemetry SDK configuration in every service's `config/telemetry.py`.

### Integration Points

**Internal Communication:**
- REST HTTPS (public API) + internal HTTPS via service mesh
- SQS for work queues
- EventBridge for event fan-out
- Redis for cache + session + rate-limit

**External Integrations:**
- **Microsoft Graph API** (M365 Calendar + Email, Teams) — OAuth per-user token pools, batched + delta queries per NFR12
- **Microsoft Entra ID** — SAML/OIDC for SSO, SCIM 2.0 for provisioning (FR71)
- **Anthropic Claude / OpenAI GPT-4** — via provider abstraction
- **FreeTSA + AWS-native TSA** — RFC 3161 timestamp signing
- **Sigstore (Fulcio + Rekor + cosign)** — artifact signing and transparency log
- **AWS services** — KMS, Secrets Manager, IAM Identity Center, ECS Fargate, RDS, S3, SQS, EventBridge, ElastiCache, ALB, CloudWatch

**Data Flow (happy path, Morning Digest):**
```
07:00 local TZ → Control Plane scheduler triggers Oracle Digest job per tenant
Oracle (LangGraph graph) → phase-gated retrieval via LlamaIndex + pgvector + canonical-memory
  → citation envelope validator (Control Plane) → envelope rendered in Next.js Digest surface
  → delivered via web push notification + email (SES)
Strategist reads digest → clicks citation → expand-inline component queries
  /api/v1/evidence/:node_id → api-gateway → canonical-memory resolve()
  → as-of-timestamp evidence-set returned → rendered in Digest card.
```

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:** All chosen technologies interoperate via well-known integration paths:
- FastAPI + Pydantic v2 + SQLAlchemy 2.x: first-class support from FastAPI docs; industry-standard combo.
- LangGraph + LlamaIndex: Party Mode pattern documented in LangChain/LlamaIndex integration guides.
- Tauri + Rust FIPS OpenSSL: Tauri permits arbitrary Rust dependencies; FIPS provider selection is Cargo-configurable.
- Next.js 16 + shadcn/ui + Tailwind v4: shadcn/ui officially supports Tailwind v4; Next.js 16 App Router is GA.

**Pattern Consistency:**
- Naming patterns align across Python (snake_case), TypeScript (camelCase code, kebab-case files), Rust (snake_case), Go (MixedCaps). Each language uses its idiomatic style; cross-language boundaries use snake_case JSON.
- Citation envelope schema defined once (JSON Schema) with generated types per language — no manual schema drift possible.
- Tenant scoping enforced at three layers (app, DB RLS, encryption) — redundant by design.

**Structure Alignment:** Service-per-capability-area matches PRD's 8 FR categories; packages/ directory holds truly cross-cutting concerns (citation envelope, tenant scoping, LLM abstraction); no capability is homeless.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

Spot-checked high-risk FRs:
- **FR1 (event log immutable append-only):** canonical-memory service `event_log.py` + Alembic migration-rule (append-only) + S3 immutable audit backup.
- **FR13 (edge agent tamper-evident):** Tauri `src-tauri/signing.rs` + `packages/citation-envelope/go` for CLI-offline verify.
- **FR27 (citation envelope mandatory):** `packages/citation-envelope/python` + Control Plane validator at agent output boundary.
- **FR44 (Section 508 + WCAG 2.1 AA):** Next.js + shadcn/ui (Radix) + `eslint-plugin-jsx-a11y` + Playwright axe + VPAT at launch.
- **FR60 (FOIA export bundle):** `services/foia-export/` + `apps/foia-cli/` + offline verifier.
- **FR72 (tenant isolation):** three-layer defense documented above + fuzz harness in CI.

**Non-Functional Requirements Coverage:**

Spot-checked load-bearing NFRs:
- **NFR1 (≤ 8s In-Meeting Alert p95):** lazy-loaded citation payload after glyph render; Oracle pre-warms phase context in Redis.
- **NFR14 (FIPS 140-2):** OpenSSL FIPS provider on Linux services; AWS KMS FIPS 140-2 validated; Tauri Rust crypto via FIPS OpenSSL.
- **NFR23 (tenant isolation):** three-layer defense tested in fuzz harness.
- **NFR48 (Cartographer ≤ 5 min p95):** chunked-extract + map-reduce enforced in `services/cartographer/chunked_extract.py`.
- **NFR50 (zero hallucinated citations):** rule-layer validator at Control Plane agent-output boundary + 11th-call CI gate with frozen golden set.
- **NFR51 (replay-parity on LLM upgrade):** `services/replay-parity-harness/` + CI gate.
- **NFR62-65 (supply chain):** Syft + cosign + SLSA generator + Grype in GitHub Actions.
- **NFR70 (LLM failover):** `packages/llm-provider-abstraction/` + capability matrix + config-flag switchover.

**Design Philosophy Coverage:**

| DP# | Commitment | Architectural Enforcement |
|---|---|---|
| DP1 | Senior-strategist mindset | Agent prompts + output linter (rule-based phrase detection) |
| DP2 | Surfaces, doesn't script | Agent prompt construction convention + output linter |
| DP3 | Symbiotic posture | No code paths that auto-commit customer-visible actions; architectural audit |
| DP4 | Teammate hand-off | Journey-4 E2E test (inherited-account onboarding) |
| DP5 | Never paraphrase trigger | In-Meeting Alert renderer rejects payloads containing trigger-utterance summaries |
| DP6 | Retrieval-only in-meeting | Architectural separation: in-meeting code path does NOT import generation modules |
| DP7 | Documentation-as-product | `docs/` treated as first-class workspace; CI builds doc validations |
| DP8 | Don't over-engineer | Deferred-to-V1.5 items hardcoded as feature flags |
| DP9 | Third-bin signal retention | Class B review queue is a first-class database entity, not deletion-after-window |
| DP10 | Master Strategist = integration layer | No UI routes for Master Strategist at V1 |
| DP11 | Stable identity + time-versioned attributes | Identity graph schema enforces single canonical identity per person |
| DP12 | Not-to-build (competitive intel, etc.) | Architectural refusal: no data flow patterns for external-threat-mapping exist |

### Implementation Readiness Validation ✅

**Decision Completeness:** All Critical and Important decisions documented with versions (where applicable) and rationale. Deferred decisions explicitly listed with unlock conditions.

**Structure Completeness:** Complete directory tree with all services, packages, apps, infra, tests, and docs. Every PRD FR category has a home.

**Pattern Completeness:** Naming, structure, format, communication, and process patterns defined with enforcement rules and anti-patterns.

### Gap Analysis Results

**Critical Gaps:** None identified at the architectural-decision altitude.

**Important Gaps:**
1. **Founder-stack choice (macOS vs Windows)** for Tauri edge-capture V1 — unresolved at PRD level; architecture assumes macOS-primary default based on common founder stack but MUST be confirmed before week 18 start.
2. **Resource path decision (Option A/B/C) due M2** — several NFRs (NFR10 availability, NFR11 agent-outage comm, NFR21 dual-approval staffing, NFR30 SOC 2 timeline, NFR60 24/7 paging) have staffing prerequisites that change under each option. Architecture is consistent with Option C (solo, honest thresholds); Option A or B unlocks uplift sooner.
3. **TSA vendor selection (FreeTSA vs commercial):** FreeTSA selected for independence + zero cost, but production reliability track record should be verified pre-V1; commercial alternatives (DigiCert TSA, Sectigo TSA) remain options with documented fallback path.
4. **Postgres extension compatibility for self-hosted:** docker-compose reference build needs Postgres 16 + pgvector + pgcrypto; published image must be verified working. Ship a tested Dockerfile, not community-maintained one.

**Nice-to-Have Gaps:**
1. LangGraph checkpoint storage backend choice (SQLite for dev, Postgres for prod — straightforward but not yet fully specified).
2. Exact React Server Components vs Client Components split per surface — will crystallize during UX workflow.
3. Unleash OSS vs self-authored feature flag store — Unleash assumed but not hard-committed.

### Validation Issues Addressed

All critical architectural decisions align with PRD constraints. No contradictions detected between PRD §Design Philosophy, §Functional Requirements, §Non-Functional Requirements, and the architectural choices here.

**Major re-affirmation during validation:** NFR25 bifurcated R.O.T. was interpreted as logical V1 (separate database clusters + separate encryption domains + shared control plane) per PRD Party Mode revision. Architecture honors this: two distinct RDS Postgres clusters (one primary for DeployAI derivatives, one secondary for customer-tenant artifacts) with separate KMS CMKs and separate backup policies but operated by a single shared ECS Fargate control plane. Physical bifurcation (dual control planes) is V1.5+ with a documented migration path.

### Architecture Completeness Checklist

- [x] Project context thoroughly analyzed (79 FR + 78 NFR + 12 DP + 10 Journeys reviewed)
- [x] Scale and complexity assessed (high / compliance-native / polyglot monorepo / ~18 components)
- [x] Technical constraints identified (single US region, FIPS, dual topology, 6-month Anchor ship)
- [x] Cross-cutting concerns mapped (citation envelope, tenant scoping, observability, audit, schema contracts)
- [x] Critical decisions documented with versions (Postgres 16, Next.js 16, Tauri 2.x, FastAPI current, LangGraph current, LlamaIndex current)
- [x] Technology stack fully specified
- [x] Integration patterns defined (REST + SQS + EventBridge + service mesh)
- [x] Performance considerations addressed (phase-gated retrieval, pre-warmed Redis caches, chunked extraction)
- [x] Naming conventions established (per-language idiomatic + API snake_case)
- [x] Structure patterns defined (monorepo with apps/services/packages/infra/tests/docs)
- [x] Communication patterns specified (REST, events, service mesh, LLM abstraction)
- [x] Process patterns documented (error handling, loading states, replay-parity)
- [x] Complete directory structure defined
- [x] Component boundaries established (public API / internal mesh / agent ↔ control plane / data cluster bifurcation)
- [x] Integration points mapped (M365, Entra ID, LLM providers, TSA, Sigstore, AWS)
- [x] Requirements to structure mapping complete (FR category → primary components table)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION (with the 4 Important-tier open confirmations listed in Gap Analysis).

**Confidence Level:** **High.** The PRD's density and Party Mode pre-decisions did most of the architectural altitude work; this document translates those into concrete technology + pattern + structure commitments. The major risks are execution risks (replay-parity semantics, Cartographer throughput, tenant-isolation fuzz robustness) — all identified with explicit M3/M4 calibration spikes per PRD build sequence.

**Key Strengths:**
- Compliance-native foundation (FIPS, RFC 3161, SBOM, Sigstore, SLSA, immutable audit) built in from week 1, not retrofit.
- Polyglot monorepo preserves per-workspace independence while enabling shared contracts.
- Three-layer tenant isolation defense-in-depth.
- LangGraph checkpointing + replay-parity harness is architecturally the right primitive for NFR51.
- Tauri 2.x for edge agent is a clear security/footprint win over Electron for the FIPS-native use case.
- Documentation-as-product (DP7) enshrined in workspace structure (`docs/` as first-class).

**Areas for Future Enhancement:**
- Physical R.O.T. bifurcation (V1.5+).
- Helm chart for self-hosted (V1.5).
- Multi-region deployment (post-StateRAMP).
- OpenFGA/ReBAC migration from RLS (V1.5+).
- LangSmith evaluation integration (post-V1, replaces or supplements in-house OTel traces).
- Expanded edge-agent OS coverage (second OS at V1.5 per FR13).

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented in this section and the referenced PRD sections.
- Use implementation patterns consistently across all workspaces; anti-patterns are CI-enforced.
- Respect workspace boundaries; cross-boundary dependencies go through `packages/*` shared libraries, not direct imports.
- Refer to this document + PRD + this architecture's Gap Analysis for all technical questions.
- When in doubt, re-read the relevant Design Philosophy commitment (DP1–DP12).

**First Implementation Priority:** Monorepo scaffold (week 1-2) — initialize pnpm workspace, Turborepo config, per-workspace `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod`, root Terraform stack, GitHub Actions CI skeleton (with placeholder 11th-call and replay-parity gates), pre-commit hooks, and `docs/` scaffolding. Everything downstream depends on this foundation.
