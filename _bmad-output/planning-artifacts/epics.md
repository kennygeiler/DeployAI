---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/ux-design-specification.md"
  - "_bmad-output/planning-artifacts/product-brief-DeployAI.md"
  - "_bmad-output/planning-artifacts/product-brief-DeployAI-distillate.md"
  - "_bmad-output/brainstorming/brainstorming-session-2026-04-21-150108.md"
workflowType: 'epics-and-stories'
project_name: 'DeployAI — Agentic Deployment System of Record'
user_name: 'Kenny Geiler'
date: '2026-04-21'
---

# DeployAI — Agentic Deployment System of Record - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for **DeployAI — Agentic Deployment System of Record**, decomposing the requirements from the PRD (79 FRs + 78 NFRs + 12 Design Philosophy commitments), the Architecture document (stack, deployment, compliance, monorepo structure), and the UX Design Specification (9 custom components, WCAG 2.1 AA + Section 508, responsive strategy) into implementable stories.

Unit of implementation: each story is scoped for a single Dev-agent session, carries Given/When/Then acceptance criteria, references the requirements it fulfills, and must not depend on any future story within the same epic.

## Requirements Inventory

### Functional Requirements

**Memory & Canonical Record**

- FR1: Data Plane captures every ingested event (email, meeting transcript, calendar entry, voice/meeting upload, field note, agent output, user override) as an immutable append-only event node with a signed timestamp from a trusted authority.
- FR2: Data Plane maintains a time-versioned identity graph where a person retains a stable identity across role or attribute changes, with evolving attributes tracked as history and not overwritten.
- FR3: Data Plane resolves duplicate identity candidates (same person, alternate roles or aliases) to a single canonical identity with supersession-aware citation resolution across time.
- FR4: Data Plane maintains a solidified-learning library where learnings are structured as {Belief, Evidence, Application Trigger} with lifecycle states (candidate, solidified, overridden, tombstoned).
- FR5: Data Plane emits a tombstone record sufficient to preserve citation integrity and auditability when underlying evidence is destroyed under retention contract.
- FR6: Data Plane resolves any citation deep-link to the exact evidence-set available at the time the cited claim was made (as-of-timestamp resolution), not merely current evidence.
- FR7: Data Plane enforces bifurcated record-of-truth across separate failure domains and separate operational control planes — customer-tenant artifacts and DeployAI observational derivatives are never co-resident in the same data-plane instance.
- FR8: Control Plane enforces retention contracts on schedule — scheduled retention jobs execute per-tenant retention policy, emit audit events on destruction, and produce tombstones per FR5.

**Capture & Ingestion**

- FR9: Deployment Strategist can ingest calendar events from Microsoft 365 Calendar via authenticated OAuth.
- FR10: Deployment Strategist can ingest email from Exchange / M365 via authenticated OAuth.
- FR11: Deployment Strategist can import Microsoft Teams meeting transcripts.
- FR12: Deployment Strategist can upload voice or meeting recording files directly; capture occurs at the endpoint with no server-side meeting-join, no bot-join capture, and no cloud-hosted recording intermediary in the data path.
- FR13: Deployment Strategist can capture on-device via a signed Edge Agent binary (one OS at V1, second at V1.5) that produces tamper-evident local transcripts verifiable without the authoring agent.
- FR14: Platform Admin can remotely disable any deployed Edge Agent binary via a kill-switch that revokes trust and halts capture.
- FR15: Cartographer performs mission-relevance triage before extraction, where "mission" is defined as the account's active deployment phase plus declared objectives; relevance is computed by Cartographer, not declared by user.
- FR16: Cartographer treats the email thread or meeting session as the unit of extraction, not individual messages.
- FR17: Deployment Strategist or Platform Admin can toggle any integration's kill-switch, revoking the integration's access token, purging in-flight queue, and emitting an audit event.
- FR18: Data Plane tolerates transient upstream failures on integration pulls with bounded-retry and idempotent-write semantics; duplicate deliveries produce at-most-once canonical events.
- FR19: Data Plane applies throttling-aware backpressure on upstream integration pulls, batching and respecting provider rate limits (e.g., Microsoft Graph throttling) without data loss.

**Intelligence, Retrieval & Phase Management**

- FR20: Cartographer extracts entities, relationships, blockers, and candidate learnings from captured events, grounded exclusively in canonical memory with no external inference.
- FR21: Oracle surfaces phase-appropriate suggestions via proactive Morning Digest, reactive In-Meeting Alert, and reflective Evening Synthesis.
- FR22: Oracle ranks candidate surface items by contextual fit to the account's current deployment phase and available evidence, enforcing a 3-item hard budget on In-Meeting Alerts.
- FR23: Oracle suppresses phase-inappropriate suggestions; at phase-ambiguity, Oracle returns a union of phase-eligible results with phase labels attached rather than guessing.
- FR24: Oracle renders a Corpus-Confidence Marker, displays Null-Result Retrieval explicitly when no phase-appropriate learnings exist, and appends a "What I Ranked Out" footer naming suppressed candidates.
- FR25: Oracle surfaces named patterns as suggestions only; no action is auto-executed on the user's behalf without explicit confirmation.
- FR26: Master Strategist arbitrates agent proposals, ranks the Action Queue, escalates low-confidence items to the User Validation Queue, and proposes phase transitions (V1: internal-only, no user-facing UI).
- FR27: Each agent output carries a citation envelope with {node_id, graph_epoch, evidence_span, retrieval_phase, confidence_score, signed_timestamp}; outputs lacking required envelope fields are rejected at the agent boundary.
- FR28: Control Plane enforces a tiered solidification classifier — V1: two tiers (Class A auto-solidify for high-confidence structured-source extractions; Class B weekly review queue for medium-confidence pattern extractions).
- FR29: Deployment Strategist can manually promote or demote learnings between solidification classes.
- FR30: Control Plane tracks each account's current deployment phase across the seven phases of the DeployAI Deployment Framework.
- FR31: Cartographer or Oracle proposes phase transitions with evidence; Deployment Strategist confirms or rejects with reason.
- FR32: Control Plane modulates retrieval ranking, digest priorities, and alert confidence thresholds based on current phase context.
- FR33: Deployment Strategist reviews items in the User Validation Queue and confirms, modifies, or rejects each with a reason string that feeds agent re-ranking.

**User Surfaces**

- FR34: Deployment Strategist receives a Morning Digest at start-of-day containing phase-contextualized priorities, delivered with emotional pacing (signal-dense without cognitive overload) and a hard-capped 3-item top-of-digest format with a "What I Ranked Out" footer.
- FR35: Deployment Strategist receives an Evening Synthesis surface at end-of-day, parallel to Morning Digest.
- FR36: Deployment Strategist receives an In-Meeting Alert as a persistent-card notification rendered within 8 seconds of agent trigger, with lazy-loaded citation payload that loads asynchronously after glyph render.
- FR37: In-Meeting Alert architecturally separates correction from dismissal as non-confusable actions; 0 silent-mislearning events on the validation protocol.
- FR38: Alert items not attended during a meeting persist as Action Queue items post-meeting rather than silently expiring.
- FR39: Deployment Strategist views Phase & Task Tracking showing current deployment phase, phase-required tasks, outstanding blockers, pending Action Queue items, and (V1.5) inheritance status per account.
- FR40: [V1.5] Deployment Strategist views a Timeline surface showing account history at week-level zoom with landmark-bloom annotations and presenter-mode.
- FR41: Any citation clicked in any surface resolves to the same canonical-memory node across all active surfaces (continuity-of-reference guarantee); default is expand-inline with an explicit "navigate to source" option.
- FR42: All active surfaces preserve context-neighborhood continuity — relationship context is the same set on each surface minus documented zoom-level collapses.
- FR43: All active surfaces present node chips, confidence affordances, evidence icons, and resolved/overridden state markers using a shared visual token set.
- FR44: All active surfaces support keyboard and screen-reader navigation with task-completion parity; WCAG 2.1 AA as a floor; screen-reader-primary is a first-class design target.
- FR45: All active surfaces present an explicit empty state with a clear next-step affordance.
- FR46: All active surfaces degrade gracefully when Cartographer, Oracle, or Master Strategist fails — agent-error state is explicit (not silent), with retry affordance and canonical-memory-only fallback.
- FR47: All active surfaces indicate ingestion-in-progress state during long extraction with progress signaling.
- FR48: All active surfaces render a memory-syncing glyph when staleness exceeds the per-surface SLO, rather than showing stale state as current.

**Override & Trust Management**

- FR49: Deployment Strategist can retrospectively override a solidified learning by attaching new evidence and a reason string.
- FR50: Override events are recorded as first-class entries in the canonical memory event log carrying {override_id, user_id, learning_id, override_evidence_event_ids, reason_string, timestamp}.
- FR51: Future agent reasoning trails that cite an overridden learning surface an override-applied sub-citation linking to the override event.
- FR52: Deployment Strategist can attach private-scope annotations to their own overrides; private annotations are not visible to Successor Strategists inheriting the account.
- FR53: Deployment Strategist can reject or defer an Action Queue item; rejection and deferral with reason are both captured and feed Oracle re-ranking.
- FR54: Deployment Strategist views an override review-history surface showing their own overrides and non-private overrides by others on accessible accounts — distinct from personal-audit view.
- FR55: Oracle surfaces a trust-earn-back confidence cue on subsequent surfaces citing a corrected learning.

**Action Queue Lifecycle**

- FR56: Deployment Strategist can claim an Action Queue item (assign-to-self).
- FR57: Deployment Strategist can mark an Action Queue item in-progress.
- FR58: Deployment Strategist can resolve an Action Queue item with a resolution state from {resolved, deferred, rejected_with_reason} and can link resolution evidence.
- FR59: Deployment Strategist views the User Validation Queue and the Solidification Review Queue as dedicated surfaces with promote/demote/defer actions; distinct from the Action Queue and Digest.

**Compliance, Evidence, Security & Audit**

- FR60: Customer Records Officer produces a timestamped, cryptographically-verifiable FOIA export of all customer-tenant records for a specified account and date range via an open-source signed CLI, without engineering support.
- FR61: Any third-party verifier can validate the signature and chain-of-custody of a FOIA export bundle using only the open-source CLI and public trust-authority keys.
- FR62: CI Pipeline enforces a replay-parity suite on every LLM model-version upgrade, adjudicating divergent citation sets via a rule-based → LLM-judge → human cascade.
- FR63: Control Plane produces a quarterly customer-visible Replay-Parity Gate Report naming false-regression-rate, false-acceptance-rate, and human-disagreement-rate.
- FR64: Platform Admin tenant-data access exists as a privileged override capability that is multi-party-authorized, fully audited, time-boxed, and customer-notified before session opens with an explicit objection window.
- FR65: External Auditor (3PAO / SOC 2) is granted just-in-time, time-bounded, read-only access to audit log and controls evidence bucket only, with watermarked exports and no canonical memory access.
- FR66: Deployment Strategist views a personal audit surface showing their own overrides, actions, corrections, and integration kill-switch toggles on accessible accounts — distinct from admin audit-log access.
- FR67: [List tier, V1.5] Customer IT/Security consumes customer-owned SIEM egress from DeployAI (syslog/CEF/OCSF push + pull-API fallback with 72-hour replay buffer).
- FR68: Control Plane emits operational metrics, distributed traces, and structured audit logs sufficient for internal incident response, third-party audit, and customer transparency requirements.
- FR69: Data Plane supports backup and disaster-recovery operations meeting RPO ≤ 5 min and RTO ≤ 4 hr for shared-tenant canonical memory.

**Identity, Tenancy, Access & Provisioning**

- FR70: Platform Admin provisions a new account, assigns the initial Deployment Strategist, and establishes an empty canonical memory baseline with tenant-scoped encryption context.
- FR71: Customer can provision DeployAI users via SAML/OIDC single sign-on (Entra ID primary at V1) and SCIM provisioning.
- FR72: Data Plane enforces tenant isolation via a per-tenant-keyed datastore with no shared canonical-memory instance at V1 — cross-tenant canonical-memory reads are architecturally impossible.
- FR73: Deployment Strategist's authorization is tenant-scoped; same role type governs Anchor, Design-Partner, Successor, and future List-tier strategists across respective tenants.
- FR74: [V1.5] Successor Strategist inherits an account's canonical memory, Action Queue, and public-scope annotations on assignment but cannot read predecessor's private-scope annotations (data model ships V1; active role V1.5).
- FR75: [V1.5] Platform Admin assigns a Successor Strategist to an inherited account, triggering the Inherited Account Onboarding flow.
- FR76: Platform Admin approves or rejects Cartographer-proposed schema evolutions; Cartographer writes proposed new fields to a staging area until Platform Admin promotes them.
- FR77: [V1.5] Customer Admin can manage their own organization's DeployAI users — placeholder capability acknowledged at V1 so the tenancy model supports it.
- FR78: Data Plane supports a reference self-hosted deployment topology with customer-owned key management (BYOK/HSM) for enterprise customers at the List tier.
- FR79: Control Plane produces a procurement-package artifact set on demand (line-item pricing breakdown, standards-conformance summary, vendor-security documentation, data-sharing contract shape draft) supporting Sourcewell cooperative-purchasing primary path.

### NonFunctional Requirements

**Performance & Responsiveness**

- NFR1: In-Meeting Alert glyph renders ≤ 8 s p95 from agent decision-to-surface under nominal load. [Binds FR36]
- NFR2: Morning Digest delivered ≤ 15 min p95 from scheduled job start; targeted ≤ 07:00 strategist-local. [Binds FR34]
- NFR3: Evening Synthesis delivered by 19:00 strategist-local p95. [Binds FR35]
- NFR4: Citation expand-inline completes ≤ 1.5 s p95 from user-click. [Binds FR41]
- NFR5: Surface freshness SLOs — Digest ≤ 30 min; In-Meeting Alert ≤ 60 s; Phase & Task Tracking ≤ 5 min; Timeline (V1.5) ≤ 5 min. [Binds FR48]
- NFR6: Sustain ≥ 500 events/account/day; absorb ≥ 2,500 events/account/hour without violating NFR5 In-Meeting Alert. [Binds FR1, FR9–FR12]
- NFR7: FOIA export ≤ 10 GB bundle within ≤ 4 hours at V1 (≤ 30 min post-StateRAMP). [Binds FR60]

**Availability, Reliability & Disaster Recovery**

- NFR8: Shared-tenant canonical memory RPO ≤ 5 min (internal target). [Binds Domain §5, FR69]
- NFR9: Shared-tenant canonical memory RTO ≤ 4 hr single-AZ; ≤ 24 hr cross-region V1. [Binds Domain §5, FR69]
- NFR10: Platform availability ≥ 99.0% monthly at V1; ≥ 99.5% at StateRAMP Ready; ≥ 99.9% post-StateRAMP.
- NFR11: Agent failure graceful degradation with explicit agent-error state. Max agent-outage before customer Security-contact communication: 2 hr V1 / 1 hr post-StateRAMP. [Binds FR46]
- NFR12: Integration pulls retry transient failures with exponential backoff (base 2 s, max 5 min); no ingest data loss on upstream outages ≤ 72 hr. [Binds FR18, FR19]
- NFR13: [List tier, V1.5] SIEM push retains ≥ 72 hr of events for replay. [Binds FR67]

**Security & Data Protection**

- NFR14: All cryptographic operations use FIPS 140-2 validated modules.
- NFR15: Canonical memory, audit logs, evidence artifacts encrypted at rest with AES-256.
- NFR16: All network traffic uses TLS 1.3+.
- NFR17: Shared-tenant KMS: cloud-provider-managed, FIPS-validated, US region.
- NFR18: Self-hosted topology supports BYOK/HSM. [Binds FR78]
- NFR19: Signed timestamps on canonical memory, audit log, FOIA exports use RFC 3161 TSA with independent public trust chain.
- NFR20: Edge Agent transcripts tamper-evident; offline-verifiable without authoring agent. [Binds FR13]
- NFR21: Platform Admin privileged-override requires two independent hardware-backed authenticated users. [Binds FR64]
- NFR22: Platform Admin privileged-override notifies customer Security contact; 15-min objection window non-emergency; session auto-expires ≤ 4 hr; transcript post-hoc. [Binds FR64]
- NFR23: Tenant isolation V1 — shared-instance Postgres + tenant-scoped envelope encryption + Row-Level Security + mandatory tenant_id on every row; cross-tenant reads architecturally forbidden; CI fuzz gate. [Binds FR72]
- NFR24: Integration kill-switch ≤ 30 s end-to-end (revoke + purge + audit event). [Binds FR14, FR17]
- NFR25: V1 — logical bifurcation: separate DB clusters with separate encryption domains and backup policies, shared control plane. [Binds FR7]
- NFR26: PrivateLink/VPC-endpoint connectivity available for enterprise shared-tenant.
- NFR27: VPC-peering or equivalent private connectivity required for self-hosted.

**Compliance & Privacy**

- NFR28: All V1 active surfaces conform to Section 508 + WCAG 2.1 AA; VPAT published at launch. [Binds FR44]
- NFR29: FOIA exports validated by open-source CLI and public trust-authority keys only. [Binds FR60, FR61]
- NFR30: SOC 2 Type II audit kickoff by M12; Type II report target M15–18.
- NFR31: StateRAMP Ready — 3PAO engagement letter signed ≤ 6 months before Ready-designation target.
- NFR32: NIST AI RMF controls mapped — citation envelope → MEASURE; replay-parity → MANAGE; override-in-reasoning-trail → GOVERN.
- NFR33: Retention defaults per canonical-memory class (Event log / Solidified-learning / Annotations / Action Queue: 7-year; Edge raw transcripts: 90 days). [Binds FR8]
- NFR34: Audit logs retained 7 years minimum, immutable, independently attestable.
- NFR35: V1 single US AWS region (us-east-2 primary, multi-AZ); no cross-border transfer.
- NFR36: V1 English only, US locale; i18n deferred.
- NFR37: Private-scope annotations enforced by authorization-layer check preceding every query; logically-separate store with distinct encryption key. [Binds FR52]
- NFR38: FOIA exports include tombstone records with attestation of destruction authority and timestamp. [Binds FR5, FR60]
- NFR39: Voice/meeting capture enforces two-party consent where required by jurisdiction. [Binds FR12]

**Accessibility**

- NFR40: Screen-reader-primary completes top-5 V1 journeys ≤ 1.5× sighted completion time. [Binds FR44]
- NFR41: Every interactive capability is keyboard-reachable and operable — drag, context-menus, state changes included; no mouse-exclusive capability.
- NFR42: Every surface exposes canonical memory node/citation/relationship model as WAI-ARIA semantic structure.
- NFR43: Design artifacts demonstrate screen-reader walk-throughs pre-implementation. [Binds FR44]
- NFR44: Pre-V1 usability study at minimum n = 5 (≥ 1 screen-reader-primary); post-ship n ≥ 8 within 6 months.

**Scalability & Capacity**

- NFR45: Shared-tenant SaaS supports ≥ 50 provisioned-and-active accounts per instance at V1.
- NFR46: Single account canonical memory scales to ≥ 10 GB over 7-year retention without degrading NFR1/NFR4/NFR5.
- NFR47: Single strategist session supports ≥ 10 concurrent open accounts; ≥ 25 concurrent strategists platform-wide.
- NFR48: Cartographer processes 40-message email thread OR 60-min meeting transcript end-to-end ≤ 5 min p95, via chunked-extract + map-reduce.
- NFR49: Post-StateRAMP scales to ≥ 500 concurrent accounts and ≥ 50 concurrent strategists; multi-region.

**Verification & Release Quality**

- NFR50: CI runs 11th-call test on every merge to `main`. Release blocked unless per-release-candidate: 100% citation-presence, ≥ 95% citation-correctness on frozen golden set (≥ 200 queries), and zero hallucinated citations. [Binds FR50]
- NFR51: CI runs replay-parity suite on every LLM model-version upgrade. [Binds FR62, FR63]
- NFR52: Four continuity-of-reference contract tests (same-node-resolution, visual-token parity, context-neighborhood, state-propagation) pass on every release; cross-tenant-isolation fuzz harness runs within this gate. [Binds FR41, FR42, FR43, NFR23]
- NFR53: 21-cell phase-retrieval audit matrix (7 phases × 3 stakeholder-topology variants) passes on every release. [Binds FR23]
- NFR54: Deterministic-path branch coverage ≥ 85% at V1; ≥ 95% + ≥ 80% mutation at StateRAMP Ready.
- NFR55: Citation envelope schema, event-node schema, tombstone schema, Action Queue schema, override-event schema enforced by CI contract tests.
- NFR56: Replay-parity semantics choice reviewed quarterly; report published. [Binds FR63]

**Observability & Operability**

- NFR57: Control Plane emits ingestion rates, agent latency (p50/p95/p99), surface freshness, integration-pull health, error rates, authz-check rates. [Binds FR68]
- NFR58: Every user request and inter-agent call traced end-to-end; traces retained ≥ 30 days.
- NFR59: All authz decisions, override events, schema-evolution, break-glass, FOIA exports, kill-switch toggles emit structured audit entries with RFC 3161 signed time. [Binds FR68]
- NFR60: Sev-1 response-start ≤ 15 min; customer communication ≤ 1 hr.
- NFR61: Sev-2 citation-accuracy regression triggers customer notification + next quarterly compliance packet.

**Supply Chain Integrity**

- NFR62: Every release ships SBOM in SPDX and CycloneDX.
- NFR63: All release binaries signed via Sigstore/cosign with reproducible-build verification.
- NFR64: SLSA Level 2 provenance V1; L3 post-StateRAMP.
- NFR65: CI blocks any release with known critical CVE in runtime deps; high CVE triggers compensating-control review.

**Deployment & Operational Constraints**

- NFR66: V1 single US AWS region (us-east-2, multi-AZ).
- NFR67: Every V1 capability on shared-tenant also operates on self-hosted OR has explicit parity declaration (🟢/🟡/🔴). [Binds FR78]
- NFR68: V1 docker-compose reference build, ≤ 1 eng-day setup; Helm deferred to V1.5. [Binds FR78]
- NFR69: Control Plane produces procurement-package artifact set on demand for Sourcewell path. [Binds FR79]

**LLM-Dependency, Cost & Runtime Reliability**

- NFR70: Primary LLM provider with documented secondary; switchover ≤ 10 min; capability-parity matrix per agent; LLM outage does NOT count against NFR10.
- NFR71: Infra + LLM cost ≤ $400/account/month at V1 (rolling 30-day mean).
- NFR72: Post-provisioning, first useful Morning Digest (≥ 3 citations from ≥ 2 threads) within ≤ 48 hr. [Binds FR15–FR22]
- NFR73: Each agent maintains MTBF ≥ 30 days; MTTR ≤ 4 hr V1 / ≤ 1 hr post-StateRAMP.

**Engineering Operability**

- NFR74: Schema migrations expand-contract, backward-compat ≥ 1 release; canonical-memory migrations append-only verified; dry-run required.
- NFR75: ≤ 2 prod deploys/day; rollback ≤ 5 min via feature-flag toggle or image revert; canary ≤ 10% traffic for agent-layer or citation-assembler changes.
- NFR76: KMS data keys rotate ≤ 90 days; OAuth refresh rotate per-provider; API keys ≤ 180 days; break-glass admin creds rotated after every use and ≤ 30 days minimum.
- NFR77: New engineer stands up full canonical-memory + 3-agent stack via `docker-compose up` (single command) in ≤ 30 min, with seeded fixtures enabling E2E Digest generation.
- NFR78: Monthly fault-injection drills (pod kill, DB failover, LLM API timeout, upstream integration rate-limit storm) with documented runbooks.

### Additional Requirements

_Technical and infrastructure requirements derived from `architecture.md` that shape epic and story implementation but are not directly expressed as FRs/NFRs._

- AR1: **Monorepo scaffold** — `pnpm` workspaces + Turborepo task-graph caching; `apps/` (web, edge-agent, foia-cli), `services/` (ingest, cartographer, oracle, master-strategist, control-plane, replay-parity-harness), `packages/` (shared-ui, design-tokens, citation-schema, llm-provider), `infra/` (Terraform+Terragrunt, compose), `tests/` (integration, E2E), `docs/`.
- AR2: **Per-workspace starters** — Next.js 16.x + React 19 + Tailwind v4 + shadcn/ui for `apps/web`; Tauri 2.x + React-TS for `apps/edge-agent`; Go `mod init` for `apps/foia-cli`; FastAPI + Pydantic v2 + SQLAlchemy 2.x async + Alembic + `uv` lockfile for each `services/*`.
- AR3: **PostgreSQL 16.x on AWS RDS Multi-AZ (us-east-2)** with two logical clusters — DeployAI observational derivatives vs customer-tenant artifacts — each with `pgvector` (HNSW) and `pgcrypto` extensions.
- AR4: **Three-layer tenant isolation** — `TenantScopedSession` context manager (app layer) + Postgres Row-Level Security policies (`USING (tenant_id = current_setting('app.current_tenant')::uuid)`) + per-tenant Data Encryption Keys wrapped by AWS KMS CMK (envelope encryption via pgcrypto).
- AR5: **Cross-tenant-isolation CI fuzz harness** that attempts unauthorized cross-tenant reads and fails CI on any success (binds NFR23, NFR52).
- AR6: **LangGraph agent orchestration** with Postgres-backed checkpointing for replay-parity (NFR51); every Cartographer / Oracle / Master Strategist pipeline is a LangGraph state machine.
- AR7: **LlamaIndex** wrapping `pgvector` exposed to LangGraph agents as tools; **custom citation-aware adapter** enforces citation envelope contract at the LangGraph-LlamaIndex boundary.
- AR8: **LLM provider abstraction** — `LLMProvider` interface (`chat_complete`, `embed`, `capabilities`); Anthropic Claude Sonnet 4 primary + OpenAI GPT-4o secondary; switchover via config flag; capability-parity matrix in `services/config/llm-capability-matrix.yaml` validated in CI.
- AR9: **Redis-backed session store** with signed-JWT tokens (15-min access, 7-day refresh); tenant-scoped key prefix (`tenant:<uuid>:`); TLS 1.3 in transit.
- AR10: **AWS Secrets Manager** with 90-day auto-rotation for KMS data keys; per-integration-provider rotation for OAuth refresh.
- AR11: **AWS S3** (SSE-KMS, us-east-2) for FOIA export bundles, raw uploaded transcripts, edge-agent artifacts, CI/CD artifact staging; **Object Lock** on audit log bucket (7-year immutable).
- AR12: **AWS SQS** (SSE-KMS) for ingestion/extraction/synthesis work queues with dead-letter queues; **AWS EventBridge** for event fan-out.
- AR13: **Canonical event envelope** `{ event_id: UUID v7, event_name: str, event_version: semver, tenant_id: UUID, occurred_at: ISO8601, trace_id: str, payload: object }`; event name format `<domain>.<entity>.<action>` snake_case.
- AR14: **Microsoft Entra ID SAML/OIDC** SSO via `python-jose[cryptography]` + `authlib`; `python3-saml` for SAML; SCIM 2.0 provisioning endpoint.
- AR15: **Authorization via Postgres RLS + application-layer role checks** at V1, served through `AuthzResolver` interface to permit future OpenFGA/ReBAC swap without touching service code.
- AR16: **FIPS 140-2 cryptographic posture** — OpenSSL FIPS provider on Amazon Linux 2023 + AWS KMS; TLS 1.3+ at ALB and service-to-service mesh; **RFC 3161 TSA** via FreeTSA primary + AWS-native fallback (`rfc3161-client`), batched every 5 s.
- AR17: **Tauri 2.x edge agent** — Rust backend for FIPS-compat crypto and local audio; capability-based permissions in `tauri.conf.json`; per-device signing key hardware-backed (macOS Keychain / Windows DPAPI); Sparkle-compatible auto-updater.
- AR18: **Go FOIA CLI** — single static binary, cross-platform, Sigstore cosign signed, offline verifier using public trust-authority keys.
- AR19: **AWS ECS Fargate** + **AWS ALB** (TLS 1.3 termination) + **AWS WAF**; blue/green deploy via ECS target-group switchover with canary ≤ 10% traffic for agent-layer or citation-assembler changes.
- AR20: **Terraform (HCL) + Terragrunt** IaC; state in S3 with DynamoDB lock; VPC + KMS + Secrets Manager bootstrap.
- AR21: **GitHub Actions CI/CD** — Syft SBOM (SPDX + CycloneDX), Cosign/Sigstore signing, `slsa-github-generator` (L2 V1, L3 post-StateRAMP), Grype + Dependabot CVE scanning, `pytest` + Playwright + `go test` matrix, replay-parity harness job, 11th-call test gate.
- AR22: **OpenTelemetry SDK** in all services shipping to Grafana Tempo (traces, 30-day) / Loki (logs, tenant-scoped labels) / Prometheus + Mimir (metrics); AWS CloudWatch backup; Grafana OnCall paging.
- AR23: **`docker-compose` reference self-hosted build** (`infra/compose/docker-compose.yml`) — Postgres (pgvector + pgcrypto) + Redis + MinIO + all services + optional FreeTSA stub + Grafana stack; stands up in ≤ 1 eng-day (NFR68) and supports the dev-env-parity NFR77 flow.
- AR24: **REST + OpenAPI 3.1** external API (FastAPI-generated spec as first-class deliverable); **RFC 7807 Problem Details** for errors (`application/problem+json`); **ISO 8601 UTC with Z**; **snake_case JSON**; **UUID v7** IDs; pagination wrapper `{ items, pagination: { cursor, has_more } }`.
- AR25: **TanStack Query v5** for server state (caching/invalidation/optimistic updates/retry) + **Zustand** for local UI state + **TanStack Table v8** for Phase Tracking / Action Queue / Validation Queue dense tables; `eslint-plugin-jsx-a11y` at error level.
- AR26: **Next.js App Router deep-links** — `/digest`, `/in-meeting/:meeting_id`, `/phase-tracking`, `/evidence/:node_id`, `/overrides`, `/onboarding`, `/auditor` (JIT).
- AR27: **Alembic migrations** — expand-contract pattern, append-only for canonical-memory, mandatory dry-run, backward-compat ≥ 1 release (NFR74).
- AR28: **Feature flags via Unleash OSS** (self-hostable, per-tenant flag evaluation) enabling NFR75 rollback ≤ 5 min.

### UX Design Requirements

_Actionable UX work items derived from `ux-design-specification.md`. Each UX-DR must be specific enough to generate at least one story with testable acceptance criteria._

**Design Foundation**

- UX-DR1: Implement `packages/design-tokens/` with 4px spacing scale, neutral-dominant palette (ink/paper/stone + evidence-blue + signal-amber), shadow scale, border-radius scale, elevation scale. No hardcoded colors/spacing outside token references.
- UX-DR2: Typography tokens — Inter for body/UI + IBM Plex Mono for citations/IDs — with explicit type-scale (display/heading/body/small/micro) and line-height ramps; 60–72 character reading measure enforced on prose surfaces.
- UX-DR3: `shadcn/ui` initialization in `apps/web` — Button, Input/Textarea/Label/Form, Dialog, DropdownMenu, ContextMenu, Command (cmdk), Popover, HoverCard, Tooltip, Tabs, Separator, Card, Sheet, Table (TanStack wrapper), Badge, Avatar, Progress, ScrollArea, Accordion/Collapsible, Toast (sonner); theme-tokens bridged to `packages/design-tokens/`.

**Custom Composite Components (`packages/shared-ui/`)**

- UX-DR4: **`CitationChip`** — inline pill (24 px height, 12 px padding, monospace), `aria-expanded`, 5 states (default/hover/focus-visible/expanded/overridden/tombstoned), variants (inline/standalone/compact-mode), HoverCard preview, ContextMenu (View evidence / Override / Copy link / Cite in override).
- UX-DR5: **`EvidencePanel`** — bordered inline-expand panel (24 px padding, 680 px max reading measure) with `<article>` landmark, metadata row, evidence-span `<mark>` highlights, loading/degraded/tombstoned variants, live-region announcement.
- UX-DR6: **`PhaseIndicator`** — persistent 32 px top-left chrome chip with `aria-live="polite"` phase-change announcement, PhaseStepper popover, states (default/hover/pending-transition/locked).
- UX-DR7: **`FreshnessChip`** — top-right 24 px "memory synced Ns ago" altimeter; color + text (never color alone); states (fresh/stale/very-stale/unavailable) mapped to NFR5 thresholds.
- UX-DR8: **`OverrideComposer`** — inline 3-field form (what-changed / why / evidence picker) with propagation preview sidecar, Cmd+Enter submit; form landmark, each field labeled, live-region.
- UX-DR9: **`InMeetingAlertCard`** — persistent draggable card (360×240 default; bottom-right dock; position persists per-tenant), `role="complementary"`, focus-trappable via Cmd+\\ and Esc-collapse; states active/idle/degraded/collapsed/archived.
- UX-DR10: **`ValidationQueueCard`** — single-item render (proposed fact + supporting evidence + confidence + action row); states unresolved/in-review/resolved/escalated.
- UX-DR11: **`TombstoneCard`** — plain-language removal reason + timestamp + optional appeal action; reachable via expired citation chip and direct `/evidence/:node_id` navigation.
- UX-DR12: **`AgentOutageBanner`** — neutral-amber full-width banner (signal-700 border); plain-language explanation + status-page link; `role="status"` informational / `role="alert"` hard outage.

**Surfaces (V1 Active)**

- UX-DR13: **Morning Digest surface** — three-column desktop / two-column laptop / stacked tablet/mobile; hard 3-item top; "What I Ranked Out" footer; emotional pacing (no shimmer on agent content).
- UX-DR14: **Evening Synthesis surface** — parallel surface to Morning Digest; candidate learnings + cross-account patterns + Class B review entry point.
- UX-DR15: **Phase & Task Tracking surface** — two-pane (table left + detail pane right); TanStack Table v8 with filter chips (phase/status/assignee/date range) + default sort + `aria-sort`.
- UX-DR16: **In-Meeting Alert surface** — meeting detection + `InMeetingAlertCard` + Action Queue persistence of unattended items + draggable-position persistence per-tenant.
- UX-DR17: **Override history surface** (`/overrides`) + **Personal audit surface** — distinct surfaces, scoped to override events vs full personal audit (overrides/actions/corrections/kill-switch toggles).
- UX-DR18: **User Validation Queue surface** + **Solidification Review Queue surface** — dedicated surfaces with promote/demote/defer actions; distinct from Action Queue and Digest.
- UX-DR19: **Cmd+K command palette** — universal; verb-based actions, surface navigation, global search with category filters; keyboard-only path to every user workflow.
- UX-DR20: **Left-rail + top-rail chrome** — fixed 240 px rail (Digest / Phase Tracking / Validation Queue + secondary); collapsible to 56 px on small viewports; top rail 56 px (phase indicator left, freshness + Cmd+K + user menu right); breadcrumbs only on nested records.
- UX-DR21: **External Auditor read-only shell** (`/auditor`) — JIT, time-boxed, audit log + controls evidence only; persistent session banner with countdown (per UX-DR28).

**Empty / Loading / Feedback Patterns**

- UX-DR22: Every surface implements an **explicit empty state** (plain-language explanation + suggested next action + docs link) per FR45.
- UX-DR23: **Loading pattern** — "loading from memory" chip + progressive render of first-available items; shimmer skeletons permitted only on static chrome, never on agent-generated content.
- UX-DR24: **Feedback pattern catalog** — Sonner toast (4 s auto-dismiss) reserved for non-consequential only; persistent confirmation chips for consequential state (override submitted, break-glass acknowledged) that do NOT auto-dismiss.
- UX-DR25: **Memory-syncing glyph** rendered when per-surface staleness exceeds NFR5 thresholds (FR48).

**Accessibility (WCAG 2.1 AA + Section 508, NFR28/40/41/42/43)**

- UX-DR26: **Keyboard equivalence** — every interactive element reachable+operable via keyboard alone; drag has a keyboard move-alternative; context-menus keyboard-triggered; no `<div onClick>`; focus order verified by `axe-playwright` in CI.
- UX-DR27: **WAI-ARIA semantic structure** — semantic HTML5 landmarks (`<main>`, `<nav>`, `<complementary>`, `<article>`); ARIA supplements only where semantic HTML insufficient; node chips announce identity + confidence + state; zoom transitions announce as state changes.
- UX-DR28: **Color independence** — every color-bearing element (status, confidence, freshness, override) also carries glyph + text label; Storybook color-blindness simulator verification (protanopia/deuteranopia/tritanopia).
- UX-DR29: **Focus indicators** — 2 px solid evidence-color outline + 2 px offset; visible against all backgrounds; `prefers-reduced-motion` honored (no focus-ring motion).
- UX-DR30: **Reduced motion** — `prefers-reduced-motion: reduce` wrapper in Tailwind motion utilities; essential expand/collapse reduced to 50 ms cross-fade.
- UX-DR31: **Font scaling & touch targets** — layout functional at 200% zoom without horizontal scroll on primary content; touch targets ≥ 44×44 px via padding.
- UX-DR32: **High-contrast mode** — CSS `forced-colors: active` support verified.
- UX-DR33: **Screen-reader task-completion parity** — top-5 V1 journeys (Digest review, In-Meeting Alert review, Phase Tracking, Override-with-Evidence, FOIA) scripted and benchmarked via VoiceOver / NVDA / JAWS; target ≤ 1.5× sighted time.
- UX-DR34: **CI a11y gates** — `eslint-plugin-jsx-a11y` at `error`, `@storybook/addon-a11y` axe-core per story, `@axe-core/react` dev runtime, `axe-playwright` per E2E journey, `pa11y` contrast check on critical surfaces; any new violation fails CI.
- UX-DR35: **VPAT authoring and publication** per release (NFR28).
- UX-DR36: **Pre-V1 usability study harness** — n ≥ 5 users (≥ 1 screen-reader-primary) pre-ship; n ≥ 8 within 6 months post-ship per NFR44.

**Responsive Design**

- UX-DR37: **Breakpoint strategy** — Mobile 360–767 (`default`), Tablet 768–1023 (`md:`), Laptop 1024–1279 (`lg:`), Desktop 1280–1535 (`xl:`; primary target), Wide ≥ 1536 (`2xl:`; content max 1440 centered); mobile-first media queries in ascending order.
- UX-DR38: **Mobile V1 read-only gate** — write workflows (Override, annotation, SCIM config) redirect to "please use a larger screen" on viewports < 768 px; In-Meeting Alert renders view-only on mobile.

**Consistency Patterns**

- UX-DR39: **Button hierarchy** — primary (one per surface; evidence-700 fill), secondary (ghost-outlined ink-800), tertiary (hover-background only), destructive (destructive-700 fill, never pre-selected); 36 px min height, 44×44 hit area, icon-only buttons carry `aria-label`.
- UX-DR40: **Form patterns** — labels above inputs (never floating/placeholder-as-label); required-field asterisk + explicit text; on-blur format + on-submit completeness validation; inline errors with `aria-invalid` + `aria-describedby`; Cmd+Enter submits forms; no multi-step forms at V1.
- UX-DR41: **Modal/sheet/popover patterns** — `Dialog` (`role="alertdialog"`) reserved for destructive confirmation only, max one deep, focus-trapped, Esc closes; `Sheet` for heavy settings (SCIM, integration provisioning); `Popover` non-trapping for metadata hovers.
- UX-DR42: **Break-glass / auditor session banner** — always-visible persistent banner during break-glass or external-auditor session with session-ID + countdown to expiration; every action within the session annotated in audit log with session ID.

**Storybook / Component Governance**

- UX-DR43: **Storybook-driven development** — every custom component has a Storybook story + axe-core check + Chromatic visual regression; keyboard-only flow demo + screen-reader flow demo required for acceptance; Storybook is CI-gated.

### FR Coverage Map

| FR | Epic | Notes |
|---|---|---|
| FR1 | Epic 1 | Canonical event log (immutable, signed-timestamp) |
| FR2 | Epic 1 | Time-versioned identity graph |
| FR3 | Epic 1 | Duplicate identity resolution with supersession-aware citation |
| FR4 | Epic 1 | Solidified-learning library schema; lifecycle wire-up in Epic 6 (classifier) and Epic 10 (override state) |
| FR5 | Epic 1 | Tombstone schema; FOIA integration in Epic 12 |
| FR6 | Epic 1 | As-of-timestamp citation resolution |
| FR7 | Epic 1 | Bifurcated R.O.T. (logical V1: two DB clusters, separate encryption domains) |
| FR8 | Epic 1 | Retention-contract job scheduling + tombstone emission |
| FR9 | Epic 3 | M365 Calendar OAuth ingestion |
| FR10 | Epic 3 | Exchange/M365 Email OAuth ingestion |
| FR11 | Epic 3 | Teams meeting transcript import |
| FR12 | Epic 3 | Voice/meeting upload (no server-side join) |
| FR13 | Epic 11 | Edge Agent binary (Tauri spike in Epic 1; full build Epic 11) |
| FR14 | Epic 2 (plumbing) + Epic 11 (edge kill-switch activation) | Remote kill-switch |
| FR15 | Epic 6 | Cartographer mission-relevance triage |
| FR16 | Epic 3 | Thread-level extraction unit |
| FR17 | Epic 2 | Integration kill-switch toggle + audit event |
| FR18 | Epic 3 | Transient-failure tolerance + idempotent writes |
| FR19 | Epic 3 | Throttling-aware backpressure |
| FR20 | Epic 6 | Cartographer extraction (entities/relationships/blockers/candidate learnings) |
| FR21 | Epic 6 | Oracle surface modes (Morning Digest, In-Meeting Alert, Evening Synthesis) |
| FR22 | Epic 6 | Oracle contextual-fit ranking + 3-item In-Meeting budget |
| FR23 | Epic 6 | Phase-appropriateness suppression + union-at-ambiguity |
| FR24 | Epic 6 | Corpus-Confidence Marker + Null-Result + "What I Ranked Out" |
| FR25 | Epic 6 | Suggestions-only posture (no auto-execute) |
| FR26 | Epic 6 | Master Strategist internal arbitration + Action Queue ranking |
| FR27 | Epic 1 | Citation envelope contract (schema + CI enforcement) |
| FR28 | Epic 5 | Tiered solidification classifier (Class A auto / Class B weekly review) |
| FR29 | Epic 9 | Manual promote/demote in Solidification Review Queue |
| FR30 | Epic 5 | 7-phase state machine |
| FR31 | Epic 6 | Phase-transition proposal flow (Cartographer/Oracle → user confirm) |
| FR32 | Epic 5 | Phase-context modulation of retrieval ranking + confidence thresholds |
| FR33 | Epic 9 | User Validation Queue review flow |
| FR34 | Epic 8 | Morning Digest surface (Walking Skeleton defining loop) |
| FR35 | Epic 8 | Evening Synthesis surface |
| FR36 | Epic 9 | In-Meeting Alert persistent-card (≤ 8 s render, lazy-loaded citation) |
| FR37 | Epic 9 | Correction-vs-dismissal non-confusable |
| FR38 | Epic 9 | Alert items persist as Action Queue items post-meeting |
| FR39 | Epic 8 | Phase & Task Tracking surface |
| FR40 | Epic 14 | [V1.5] Timeline surface |
| FR41 | Epic 1 (contract) + Epic 7 (CitationChip component) + Epic 8 (surface integration) | Continuity-of-reference; citation deep-link resolves identically across surfaces |
| FR42 | Epic 1 (contract) + Epic 8 (surface) | Context-neighborhood continuity across surfaces |
| FR43 | Epic 7 | Shared visual token set across all surfaces |
| FR44 | Epic 1 (a11y CI) + Epic 8 (keyboard + SR task-completion parity) | WCAG 2.1 AA floor; a11y-first |
| FR45 | Epic 7 | Empty-state primitive; Epic 8+ consume |
| FR46 | Epic 7 | AgentOutageBanner primitive; Epic 8/9/10 consume |
| FR47 | Epic 8 | Ingestion-in-progress indicator |
| FR48 | Epic 7 | Memory-syncing glyph primitive; Epic 8+ consume |
| FR49 | Epic 10 | Override solidified learning with new evidence + reason |
| FR50 | Epic 10 | Override events as first-class canonical-memory log entries |
| FR51 | Epic 10 | Override-applied sub-citation in reasoning trails |
| FR52 | Epic 10 | Private-scope annotations (separate encryption key) |
| FR53 | Epic 9 | Reject/defer Action Queue items with reason |
| FR54 | Epic 10 | Override review-history surface |
| FR55 | Epic 10 | Trust-earn-back confidence cue on subsequent surfaces |
| FR56 | Epic 9 | Claim Action Queue item |
| FR57 | Epic 9 | Mark Action Queue item in-progress |
| FR58 | Epic 9 | Resolve Action Queue item with resolution state + evidence link |
| FR59 | Epic 9 | User Validation Queue + Solidification Review Queue surfaces |
| FR60 | Epic 12 | FOIA CLI bundle generation |
| FR61 | Epic 12 | Third-party verifier using only open-source CLI + public keys |
| FR62 | Epic 4 | Replay-parity CI suite (rule → LLM-judge → human cascade) |
| FR63 | Epic 4 | Quarterly Replay-Parity Gate Report |
| FR64 | Epic 12 | Break-glass multi-party authorization + customer notification |
| FR65 | Epic 12 | External Auditor JIT read-only access + watermarked exports |
| FR66 | Epic 10 | Personal audit surface |
| FR67 | Epic 14 | [V1.5 List tier] SIEM egress |
| FR68 | Epic 12 | Operational metrics + distributed traces + structured audit log emission |
| FR69 | Epic 12 | Backup + DR meeting RPO ≤ 5 min, RTO ≤ 4 hr |
| FR70 | Epic 2 | Account provisioning + canonical memory baseline |
| FR71 | Epic 2 | Entra ID SAML/OIDC + SCIM 2.0 |
| FR72 | Epic 1 | Three-layer tenant isolation; cross-tenant fuzz gate |
| FR73 | Epic 2 | Tenant-scoped strategist authorization |
| FR74 | Epic 14 | [V1.5 active] Successor inheritance (data-model hooks ship in Epic 1/10) |
| FR75 | Epic 14 | [V1.5] Successor assignment + onboarding flow |
| FR76 | Epic 1 | Cartographer schema-evolution staging + Platform Admin promote/reject |
| FR77 | Epic 14 | [V1.5] Customer Admin self-service user management |
| FR78 | Epic 12 | Self-hosted reference build with BYOK/HSM (docker-compose parity declaration) |
| FR79 | Epic 12 | Procurement-package artifact set on demand |

**UX Design Requirements coverage:** UX-DR1–2 (tokens) → Epic 1; UX-DR3 (shadcn init) → Epic 1; UX-DR4–12 (9 custom components) + UX-DR22–25 (patterns/primitives) + UX-DR39–43 (consistency patterns, Storybook governance) → Epic 7 (Design System Component Library); UX-DR13–14 (Digest, Evening Synthesis), UX-DR15 (Phase Tracking), UX-DR19–20 (nav chrome + Cmd+K) → Epic 8; UX-DR9 (InMeetingAlertCard refinement), UX-DR10 (ValidationQueueCard refinement), UX-DR16 (In-Meeting surface), UX-DR18 (Validation/Solidification Queue surfaces) → Epic 9; UX-DR8 (OverrideComposer), UX-DR17 (Override history + Personal audit) → Epic 10; UX-DR21 (`/auditor`) + UX-DR42 (break-glass banner wire-up) → Epic 12; UX-DR26–34 (a11y CI gates — pulled LEFT into Epic 1); UX-DR35 (VPAT automation pipeline) → Epic 7; UX-DR35 (VPAT authoring & publication) + UX-DR36 (usability study harness) → Epic 13.

**NFR coverage:** Mapped per-epic in each epic's header. Cross-cutting NFRs (NFR10 availability, NFR57–58 observability, NFR60–61 incident response, NFR62–65 supply chain, NFR67 parity, NFR71 cost envelope, NFR74–78 engineering operability) are distributed as DoD obligations on every relevant epic (per Party Mode guidance — "operability is a rule, not an epic").

## Epic List

### Epic 1: Foundations, Canonical Memory & Citation Envelope
Scaffold the polyglot monorepo (pnpm + Turborepo with Next.js, Tauri, Go, FastAPI workspaces), stand up CI/CD with supply-chain signing (Syft SBOM, Cosign, SLSA L2, Grype), publish `packages/design-tokens/`, initialize shadcn/ui, wire the full accessibility CI stack (eslint-plugin-jsx-a11y, @axe-core/react, axe-playwright, pa11y, @storybook/addon-a11y), validate the docker-compose dev environment with a CI-timed 30-min bring-up, build the canonical memory substrate (event log, identity graph, solidified-learning library, tombstones, continuity-of-reference contracts, schema-evolution staging area), implement the three-layer tenant isolation (TenantScopedSession + Postgres RLS + per-tenant KMS envelope encryption), freeze the citation envelope contract v0.1, add RFC 3161 signed timestamps via FreeTSA + AWS fallback, ship the cross-tenant fuzz CI gate, freeze the LLM provider abstraction interface (concrete implementations deferred to Epic 5), and complete the Tauri signed-Hello-World spike to retire edge-platform risk.
**Epic goal:** Platform Admin provisions a tenant; canonical memory records events with verified citation integrity, continuity-of-reference guarantees, three-layer tenant isolation enforced by CI fuzz, and every future UI surface has a ready-to-go design system + a11y gate + admin shell.
**FRs covered:** FR1, FR2, FR3, FR4 (schema), FR5 (schema), FR6, FR7, FR8, FR27, FR41 (contract), FR42 (contract), FR44 (a11y CI floor), FR72, FR76
**NFRs covered:** NFR8, NFR9, NFR14, NFR15, NFR16, NFR19, NFR23, NFR25, NFR33, NFR34, NFR35, NFR37 (infrastructure), NFR46, NFR52 (cross-tenant fuzz), NFR54, NFR55, NFR62, NFR63, NFR64, NFR65, NFR66, NFR74, NFR77
**ARs covered:** AR1, AR2, AR3, AR4, AR5, AR11 (S3 Object Lock scaffold), AR13, AR15, AR16, AR20, AR21, AR22, AR23 (dev compose), AR24 (REST baseline), AR27
**UX-DRs covered:** UX-DR1, UX-DR2, UX-DR3, UX-DR26–34 (a11y CI stack pulled LEFT per Party Mode)

### Epic 2: Identity, Tenancy & SSO
Wire Microsoft Entra ID SAML/OIDC single sign-on and SCIM 2.0 provisioning, implement the tenant-scoped role matrix (`deployment_strategist`, `successor_strategist` placeholder, `platform_admin`, `customer_records_officer`, `external_auditor`, `customer_admin` placeholder) through the `AuthzResolver` interface, stand up the Redis-backed session store with signed-JWT refresh, build integration kill-switch plumbing with audit event schema, and scaffold break-glass infrastructure (dual-approval session flag + IAM Identity Center hook + audit event schema — end-to-end operability completes in Epic 12).
**Epic goal:** Customers provision DeployAI users via SSO/SCIM; Platform Admin provisions accounts with empty canonical-memory baseline; every user request carries an authenticated tenant-scoped context.
**FRs covered:** FR14 (plumbing), FR17, FR70, FR71, FR73, FR78 (auth hook)
**NFRs covered:** NFR17, NFR18 (BYOK interface), NFR21 (plumbing), NFR22 (plumbing), NFR24, NFR26, NFR27, NFR76
**ARs covered:** AR9, AR10, AR14, AR15

### Epic 3: Ingestion Pipelines
Ship the V1 ingestion surface area — M365 Calendar + Exchange email OAuth pulls, Teams transcript import, direct voice/meeting file upload (no server-side bot-join), thread-level extraction unit, integration kill-switch audit events, backpressure + retry + idempotency, two-party consent enforcement — and wire the admin ingestion surface (`/admin/runs`) so the engineering team has a cockpit to watch evidence land.
**Epic goal:** Evidence starts flowing into canonical memory for every active account; engineering team has visibility into ingestion health.
**FRs covered:** FR9, FR10, FR11, FR12, FR16, FR17 (audit event wire-up), FR18, FR19
**NFRs covered:** NFR6, NFR12, NFR39
**ARs covered:** AR11 (ingestion S3), AR12
**UX-DRs covered:** (engineer cockpit consumes Epic 1 shadcn init)

### Epic 4: Agent Runtime Contracts & Replay-Parity Harness
Build the agent substrate contracts and the replay-parity CI gate ahead of real agent work. Implement LangGraph Postgres-checkpointing against a stub agent that emits canned citation envelopes, ship the custom citation-aware LlamaIndex adapter enforcing the Epic 1 envelope contract, author the ≥ 200-query golden fixture set spanning the 21-cell phase-retrieval audit matrix, build the rule-based evaluator → LLM-judge → human adjudication surface (`/adjudication` internal-only, consuming Epic 1's shadcn), wire the quarterly Replay-Parity Gate Report generator, and turn on the 11th-call CI gate (100% presence, ≥ 95% correctness, zero hallucinated citations) + continuity-of-reference contract tests + cross-tenant-isolation fuzz in every release.
**Epic goal:** Every future agent output is verified against a frozen citation envelope, every LLM upgrade is adjudicated, every release is 11th-call-gated — the correctness contract is operable before agents exist.
**FRs covered:** FR62, FR63
**NFRs covered:** NFR50, NFR51, NFR52, NFR53, NFR54, NFR55, NFR56
**ARs covered:** AR6 (LangGraph checkpointing), AR7 (LlamaIndex adapter)

### Epic 5: Agent Runtime Foundation
With the contract locked (Epic 4), build the agent runtime chassis: concrete LLM provider implementations (Anthropic Claude Sonnet 4 primary + OpenAI GPT-4o secondary behind Epic 1's `LLMProvider` interface) with config-flag switchover ≤ 10 min and capability-parity matrix CI validation, prompt/tool infrastructure, 7-phase state machine, and tiered solidification classifier (Class A auto / Class B weekly review) with phase-context modulation of retrieval + confidence thresholds.
**Epic goal:** A stub agent navigates phases, classifies events, and replay-parity passes — proving the foundation works before the three real agents are built on top.
**FRs covered:** FR28, FR30, FR32
**NFRs covered:** NFR70, NFR71 (cost telemetry), NFR73 (agent-layer MTBF/MTTR targets)
**ARs covered:** AR8

### Epic 6: Cartographer, Oracle & Master Strategist
Build the three real agents on Epic 5's foundation. Cartographer: mission-relevance triage + entity/relationship/blocker/candidate-learning extraction grounded exclusively in canonical memory, chunked-extract + map-reduce per NFR48 (40-message email thread OR 60-min meeting transcript ≤ 5 min p95). Oracle: phase-gated retrieval with Corpus-Confidence Marker + Null-Result handling + "What I Ranked Out" footer + 3-item hard budget on In-Meeting Alerts + suggestions-only posture (no auto-execute). Master Strategist: internal arbitration + Action Queue ranking + phase-transition proposals (V1 internal-only, no user-facing UI per DP10). Every agent output validated against the citation envelope at the LangGraph-LlamaIndex boundary.
**Epic goal:** Evidence becomes insight — agents propose, humans authorize. The first useful Morning Digest (≥ 3 citations from ≥ 2 distinct source threads) is generatable within 48 hr of integration activation (NFR72).
**FRs covered:** FR15, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR31
**NFRs covered:** NFR48, NFR72, NFR73 (per-agent MTBF/MTTR)
**ARs covered:** AR8 (multi-agent orchestration)

### Epic 7: Design System Component Library
Ship **all nine custom composite components + primitives** as a cohesive design-system release BEFORE any surface epic consumes them — protecting the 07:00→10:03 identical-citation handshake by ensuring `CitationChip`, `EvidencePanel`, `FreshnessChip`, `PhaseIndicator`, `OverrideComposer`, `InMeetingAlertCard`, `ValidationQueueCard`, `TombstoneCard`, `AgentOutageBanner` are born in the same sprint, reviewed in the same Storybook story, and a11y-tested side-by-side. Also ship shared primitives: empty-state component, loading "loading from memory" chip, memory-syncing glyph, `SessionBanner` (break-glass variant), button-hierarchy/form/modal-pattern standards. Tablet + mobile-read-only variants baked into each component's acceptance (per UX-DR37/38).
**Epic goal:** Surface epics (8, 9, 10, 12) become pure *composition* work — engineers compose an existing vocabulary, not bootstrap one under deadline pressure.
**Status: shipped 2026-04-26** — see [`epic-7-design-system-completion.md`](../implementation-artifacts/epic-7-design-system-completion.md) and [`epic-7-retrospective-2026-04-26.md`](../implementation-artifacts/epic-7-retrospective-2026-04-26.md). **Next in sequence: Epic 8.**
**FRs covered:** FR41 (CitationChip component), FR43 (shared visual token set), FR45 (empty-state primitive), FR46 (AgentOutageBanner primitive), FR48 (memory-syncing glyph)
**NFRs covered:** NFR28 (WCAG 2.1 AA component-level), NFR41 (keyboard equivalence in primitives), NFR42 (WAI-ARIA semantic structure in primitives), NFR43 (a11y-first design artifacts)
**UX-DRs covered:** UX-DR4, UX-DR5, UX-DR6, UX-DR7, UX-DR8, UX-DR9, UX-DR10, UX-DR11, UX-DR12, UX-DR22, UX-DR23, UX-DR24, UX-DR25, UX-DR39, UX-DR40, UX-DR41, UX-DR43 (Storybook governance), plus VPAT automation pipeline (UX-DR35 partial)

### Epic 8: Morning Digest, Phase Tracking & Evening Synthesis Surfaces
Compose Epic 7's primitives into the three V1 "reflective/proactive" surfaces — Morning Digest (hard 3-item top + "What I Ranked Out" footer + emotional pacing), Phase & Task Tracking (TanStack Table two-pane with filter chips + default sort + aria-sort), Evening Synthesis (backward-looking reconciliation + Class B review entry point). Wire nav chrome (240 px left rail / 56 px top rail collapsible) and Cmd+K command palette with verb-based access to every user workflow. Keyboard-equivalence + screen-reader task-completion parity on the top-5 journeys scripted via axe-playwright (VoiceOver, NVDA, JAWS).
**Epic goal:** Strategist walks in prepared (Journey 1); Phase Tracking is operational; the calm-authority aesthetic ships on day one.
**Status: V1 walking skeleton on `main` (2026-04)** — surfaces + chrome + activity BFF + mocks; full Story 8.x ACs in `epics.md` (Oracle-backed digest, NFR2/NFR4 gates, integration tests, SessionBanner slot, global Cmd+K search) are **not** all satisfied. See [`epic-8-implementation-status.md`](../implementation-artifacts/epic-8-implementation-status.md) and [`epic-8-retrospective-2026-04-26.md`](../implementation-artifacts/epic-8-retrospective-2026-04-26.md). **Hardening** continues; **next epic in sequence: Epic 9.**
**FRs covered:** FR34, FR35, FR39, FR41 (surface integration), FR42 (surface integration), FR44 (surface keyboard/SR), FR47 (ingestion-in-progress indicator)
**NFRs covered:** NFR1 (Morning Digest delivery), NFR2 (digest latency), NFR3 (Evening Synthesis delivery), NFR4 (citation expand-inline), NFR5 (surface freshness SLOs), NFR28 (surface-level VPAT scope), NFR40 (screen-reader parity top-5), NFR45, NFR46, NFR47
**ARs covered:** AR24 (REST consumption), AR25, AR26
**UX-DRs covered:** UX-DR13, UX-DR14, UX-DR15, UX-DR19, UX-DR20, UX-DR37, UX-DR38

### Epic 9: In-Meeting Alert, Action Queue & Validation Queues
Compose Epic 7's `InMeetingAlertCard` into the full reactive surface — real meeting detection (not dev-button), persistent-card notification rendered ≤ 8 s from agent decision-to-surface with lazy-loaded citation payload (NFR1), 3-item hard budget, architecturally-separated correction-vs-dismissal (0 silent-mislearning on validation protocol per FR37), alert items persist as Action Queue items post-meeting rather than silently expiring. Ship the Action Queue lifecycle (claim → in-progress → resolve with resolution state ∈ {resolved, deferred, rejected_with_reason} + evidence link). Ship the User Validation Queue and Solidification Review Queue surfaces with promote/demote/defer actions (distinct from Action Queue and Digest).
**Epic goal:** Live-meeting retrieval under social pressure (Journey 2) — the defining 10:03 moment with an identical `CitationChip` to the 07:00 digest. Queue lifecycle operational.
**FRs covered:** FR29, FR33, FR36, FR37, FR38, FR53, FR56, FR57, FR58, FR59
**NFRs covered:** NFR1 (8-s render), NFR5 (60-s In-Meeting staleness), NFR72 partial
**UX-DRs covered:** UX-DR9 (refinement), UX-DR10 (refinement), UX-DR16, UX-DR18

### Epic 10: Override, Trust Repair & Personal Audit
Ship the full override capability — `OverrideComposer` (inline 3-field: what-changed / why / evidence picker + Cmd+Enter submit + propagation preview sidecar), override events as first-class canonical-memory log entries (`{override_id, user_id, learning_id, override_evidence_event_ids, reason_string, timestamp}`), private-scope annotations stored in logically-separate encrypted store (NFR37), Override history surface (`/overrides`) distinct from Personal audit surface, override-applied sub-citation appended to future reasoning trails (FR51 full — no "hook"), trust-earn-back confidence cue on subsequent surfaces citing a corrected learning (FR55 full).
**Epic goal:** Trust repair loop (Journey 7) — strategist can defensibly override any solidified learning with evidence, and the system visibly credits the correction on every subsequent surface.
**FRs covered:** FR49, FR50, FR51, FR52, FR54, FR55, FR66
**NFRs covered:** NFR37 (private-scope enforcement verified end-to-end)
**UX-DRs covered:** UX-DR8 (composition), UX-DR17

### Epic 11: Edge Capture Agent (Tauri macOS V1)
Build on Epic 1's Tauri Hello-World spike to ship the production edge agent — capability-based permissions (`tauri.conf.json`), signed binary + notarization + Sparkle auto-updater, local tamper-evident transcript signed with per-device hardware-backed key (macOS Keychain), offline verification via the Epic 12 FOIA CLI (no DeployAI services required), two-party consent UX, Edge Agent kill-switch activation wired into Epic 2's plumbing. Edge-agent-specific subset of Epic 7's shared-ui (`FreshnessChip`, `AgentOutageBanner` minimal variant).
**Epic goal:** On-device capture with no server-side bot-join; transcripts verifiable offline without DeployAI; Platform Admin can kill any deployed binary in ≤ 30 s.
**FRs covered:** FR13, FR14 (edge activation)
**NFRs covered:** NFR20, NFR24 (edge kill-switch)
**ARs covered:** AR17

### Epic 12: FOIA Export, Compliance, Operability & External Auditor
The compliance- and operability-delivery epic — distributed from old Epic 11 per Party Mode. Ship the Go FOIA CLI (single static binary, Sigstore cosign-signed, offline verifier using public trust-authority keys), bundle construction with tombstone inclusion + chain-of-custody within ≤ 4 hr for ≤ 10 GB (NFR7), External Auditor JIT read-only shell (`/auditor`) with watermarked exports, break-glass end-to-end operability (customer Security-contact notification webhook + 15-min objection window for non-emergency + SessionBanner + ≤ 4 hr session auto-expiry + post-hoc transcript), immutable audit log emitted to separate S3 bucket with Object Lock (7-year retention per NFR34), quarterly compliance packet generator (Sev-2 citation-accuracy regression path), procurement package artifact set (line-item pricing, standards-conformance, vendor-security, data-sharing contract shape), NIST AI RMF mapping doc, self-hosted reference build fresh-laptop drill (NFR67/68 acceptance), SLOs + Grafana dashboards + Grafana OnCall paging (NFR10/57/58/60/61), Unleash feature-flag infrastructure + canary deploys ≤ 10% traffic for agent/citation-assembler changes (NFR75), monthly chaos drills (NFR78), backup + DR verification (NFR69), cost-per-account telemetry (NFR71).
**Epic goal:** Customer Records Officer produces verifiable FOIA exports without engineering; SOC 2 / StateRAMP audit evidence ready; V1 is operable, observable, recoverable; enterprise procurement-ready.
**FRs covered:** FR60, FR61, FR64, FR65, FR66 (audit log integration), FR68, FR69, FR78 (self-hosted validation), FR79
**NFRs covered:** NFR7, NFR10 (SLO tooling), NFR11, NFR21 (full), NFR22 (full), NFR29, NFR30 (audit hooks), NFR31, NFR32, NFR34, NFR38, NFR45, NFR46, NFR47, NFR49, NFR57, NFR58, NFR59, NFR60, NFR61, NFR67, NFR68, NFR69, NFR71, NFR75, NFR78
**ARs covered:** AR11 (Object Lock), AR18, AR19 (canary + blue/green), AR22 (observability), AR23 (compose validation), AR28
**UX-DRs covered:** UX-DR21 (`/auditor`), UX-DR42 (break-glass session banner wire-up via Epic 7 `SessionBanner`)

### Epic 13: Usability Validation & VPAT Authoring
Stand up the calendar-committed validation + compliance-authoring epic — recruitment begins week 16 for n ≥ 5 including ≥ 1 screen-reader-primary user (NFR44), usability study execution on the top-5 V1 journeys (Morning Digest review, In-Meeting Alert review, Phase & Task Tracking, Override-with-Evidence, FOIA as Records Officer) with screen-reader task-completion parity benchmarking (NFR40), triaged findings with ship/no-ship gate, VPAT authoring and publication using Epic 7's automated evidence pipeline (NFR28), post-ship n ≥ 8 second-pass study within 6 months.
**Epic goal:** V1 ships with VPAT published at launch (NFR28) and credible accessibility/usability evidence — no retrofit.
**NFRs covered:** NFR28 (VPAT publication), NFR40 (SR task-completion parity verified), NFR43 (a11y-first artifacts verified), NFR44 (usability study executed)
**UX-DRs covered:** UX-DR35 (VPAT authoring), UX-DR36 (usability study harness)

### Epic 14: V1.5 Scaffolding & Successor Inheritance
Explicitly post-Anchor-ship. Activate the V1.5 capabilities whose data model ships in V1: Successor Strategist inheritance (FR74/FR75) on top of Epic 1's time-versioned identity graph and Epic 10's private-scope annotations, Timeline surface (FR40), Customer Admin self-service user management (FR77), [List tier] SIEM egress with 72-hour replay buffer (FR67/NFR13), Edge Agent second OS (FR13 V1.5), Helm chart (NFR68 uplift).
**Epic goal:** Path to List tier + post-Anchor growth features; supports FR74's "data model ships V1, active role V1.5" commitment.
**FRs covered:** FR40, FR67, FR74, FR75, FR77
**NFRs covered:** NFR13, NFR30 (SOC 2 Type II observation window), NFR49 (post-StateRAMP scale), NFR68 (Helm)

---

## Dependency Flow Verification

Each epic is standalone (does not require any FUTURE epic to function):

- **Epic 1** → standalone foundation
- **Epic 2** → uses Epic 1 (tenant_id context, RLS, audit event schema)
- **Epic 3** → uses Epic 1 (canonical memory, citation envelope) + Epic 2 (tenant context)
- **Epic 4** → uses Epic 1 (citation envelope, LLM abstraction interface, shadcn admin shell, LangGraph checkpointing substrate)
- **Epic 5** → uses Epic 1 (LLM interface) + Epic 4 (contracts, harness) + Epic 3 (events to reason over)
- **Epic 6** → uses Epics 1/4/5 (agents run on foundation, all output gated by Epic 4 harness)
- **Epic 7** → uses Epic 1 (shadcn + tokens + a11y CI) — standalone; does NOT depend on agent epics
- **Epic 8** → uses Epics 1/6/7 (consumes agent outputs through design system primitives)
- **Epic 9** → uses Epics 1/6/7 (In-Meeting needs Oracle; consumes InMeetingAlertCard from Epic 7)
- **Epic 10** → uses Epics 1/6/7/8 (override events, OverrideComposer, override history surface)
- **Epic 11** → uses Epic 1 (Tauri spike foundation) + Epic 2 (kill-switch) + Epic 7 (edge-ui subset) + Epic 12 (FOIA CLI for offline verification) — *Note: Epic 11 has a Epic 12 FOIA CLI dependency; Epic 11 can ship without Epic 12 by deferring the offline-verification acceptance criterion to Epic 12 completion, or by scheduling Epic 12's FOIA CLI story as Epic 11's first dependency. Both approaches valid; the plan schedules Epic 12 in parallel.*
- **Epic 12** → uses Epics 1/2/6/7 (canonical memory + break-glass infra + Oracle output + SessionBanner)
- **Epic 13** → uses Epics 7/8/9/10 (study validates the composed surfaces); runs in parallel w18–23
- **Epic 14** → explicitly post-V1; uses all preceding epics

## Build-Sequence Alignment with Architecture §Decision Impact Analysis

- **Weeks 1–2:** Epic 1 scaffold + CI + design tokens + shadcn init + a11y CI gates
- **Weeks 3–4:** Epic 1 canonical memory substrate + three-layer isolation + Tauri spike
- **Weeks 4–6:** Epic 1 citation envelope + RFC 3161 + continuity-of-reference contracts + cross-tenant fuzz gate + LLM abstraction interface + admin shell; Epic 2 identity/SSO/SCIM/kill-switch/break-glass plumbing (parallel)
- **Weeks 7–9:** Epic 3 ingestion
- **Weeks 8–11:** Epic 4 replay-parity harness + 11th-call gate + adjudication surface (Spike-1)
- **Weeks 10–12:** Epic 5 agent runtime foundation (LLM concrete, state machine, classifier)
- **Weeks 12–16:** Epic 6 Cartographer + Oracle + Master Strategist
- **Weeks 14–16:** Epic 7 Design System Component Library (starts late-Epic-6, parallel)
- **Weeks 16–19:** Epic 8 Morning Digest + Phase Tracking + Evening Synthesis
- **Weeks 16–22:** Epic 11 Edge Agent production build (starts early, parallel)
- **Weeks 16–23:** Epic 13 Usability Validation (recruiting kicks off w16)
- **Weeks 19–22:** Epic 9 In-Meeting Alert full + Action Queue + Validation Queues
- **Weeks 20–22:** Epic 10 Override + Trust Repair + Personal Audit
- **Weeks 17–23:** Epic 12 FOIA + Compliance + Operability (parallel; SLOs/paging continuous from w4)
- **Post-V1:** Epic 14

**First defining-experience demo:** end of Epic 8 (Morning Digest walking-skeleton + dev-triggered In-Meeting Alert with identical `CitationChip`), approximately **week 18** — ~5 weeks earlier than original Epic 6/7 serial path. Full defining-loop completeness at **end of Epic 9 (~week 22)**.


---

## Epic 1: Foundations, Canonical Memory & Citation Envelope

Scaffold the polyglot monorepo, stand up CI/CD with supply-chain signing, publish the design system foundation, wire the full accessibility CI stack, build the canonical memory substrate with three-layer tenant isolation, freeze the citation envelope contract, and retire edge-platform risk via a Tauri spike.

### Story 1.1: Initialize pnpm + Turborepo monorepo scaffold

As a **platform engineer**,
I want a pnpm + Turborepo monorepo initialized with empty workspaces for every planned app, service, and package,
So that every subsequent story has a canonical location for its code and shared tooling is in place from day one.

**Acceptance Criteria:**

**Given** a fresh clone of the repository
**When** I run `pnpm install && pnpm turbo run build --filter=...`
**Then** the command completes with zero errors and emits a build cache under `.turbo/`
**And** `pnpm-workspace.yaml` declares workspaces for `apps/*`, `services/*`, `packages/*`, `infra/*`, `tests/*`
**And** `turbo.json` declares `build`, `lint`, `test`, `typecheck`, `dev` pipelines with correct `dependsOn` topology
**And** the root `package.json` pins `turbo`, `typescript`, `prettier`, `eslint` to current stable versions
**And** `docs/repo-layout.md` documents the workspace layout and lists which starter command each workspace uses
**And** a `CODEOWNERS` file is present (initially assigning everything to the founding engineer)

### Story 1.2: Baseline CI/CD with supply-chain signing

As a **platform engineer**,
I want GitHub Actions CI/CD running on every PR with SBOM generation, artifact signing, SLSA L2 provenance, and CVE scanning,
So that supply-chain integrity (NFR62–NFR65) is enforced from the first commit forward.

**Acceptance Criteria:**

**Given** a pull request is opened against `main`
**When** the CI pipeline runs
**Then** `syft` emits SPDX + CycloneDX SBOMs for every workspace that produces an artifact
**And** `cosign` signs all release candidate artifacts using Sigstore keyless signing
**And** `slsa-github-generator` produces a SLSA L2 provenance attestation attached to the artifacts
**And** `grype` scans for CVEs and fails the build on any known Critical CVE; High CVEs emit a review-required annotation
**And** `dependabot.yml` is configured for weekly dependency updates across npm, pip, Go modules, and Cargo
**And** the pipeline status is green on a no-op PR and visible in `.github/workflows/ci.yml`

### Story 1.3: Per-workspace starter initialization (Next.js, Tauri, Go, FastAPI)

As a **platform engineer**,
I want each `apps/` and `services/*` workspace initialized from its canonical starter with shared tooling wired,
So that feature stories across Python, TypeScript, Rust, and Go can begin immediately without bootstrapping delays.

**Acceptance Criteria:**

**Given** the monorepo scaffold from Story 1.1
**When** per-workspace starters are initialized
**Then** `apps/web` is a Next.js 16 App Router project with React 19, Tailwind v4, ESLint, TypeScript, Turbopack
**And** `apps/edge-agent` is a Tauri 2.x project with a React-TS frontend and Rust backend, building to a signed binary
**And** `apps/foia-cli` is a Go module (`go 1.23+`) with a `main.go` producing a static binary via `CGO_ENABLED=0`
**And** at least one service under `services/` (e.g., `services/control-plane`) is a FastAPI + Pydantic v2 + SQLAlchemy 2.x async + Alembic + `uv` managed project with a `pyproject.toml` and locked `uv.lock`
**And** every workspace produces a Docker image via a per-workspace `Dockerfile` buildable by `pnpm turbo run docker:build --filter=<workspace>`
**And** `pnpm turbo run lint` passes across all workspaces with zero violations

### Story 1.4: Design tokens package (`packages/design-tokens/`)

As a **UX designer**,
I want a single `packages/design-tokens/` package exposing colors, spacing, typography, shadows, radii, and elevation tokens consumable from both TypeScript and CSS,
So that no surface is ever built with hardcoded values and the calm-authority aesthetic is enforced via tooling.

**Acceptance Criteria:**

**Given** the need for a single design-token source of truth
**When** the package is published
**Then** `packages/design-tokens/src/tokens.ts` exports `colors` (neutral/ink/paper/stone scales + evidence-blue + signal-amber + destructive — no primary green), `spacing` (4px-base scale 0/0.5/1/1.5/2/3/4/6/8/12/16/24), `typography` (Inter + IBM Plex Mono families with display/heading/body/small/micro scale), `shadows`, `radii`, `elevation`
**And** the package emits `dist/tokens.css` with matching CSS custom properties (`--color-ink-900`, `--space-4`, etc.)
**And** `packages/design-tokens/src/tokens.test.ts` verifies every color pair used in body text meets WCAG AA contrast (≥ 4.5:1) via `wcag-contrast`
**And** `apps/web`'s Tailwind config extends from tokens via `@import "@deployai/design-tokens/tailwind"` — no hardcoded colors/spacing in `tailwind.config.ts`
**And** a Storybook story `Foundations/Tokens.stories.tsx` renders the palette, type ramp, and spacing scale for design review
**And** `UX-DR1` and `UX-DR2` are satisfied and referenced in the story file header

### Story 1.5: shadcn/ui initialization and theme bridging

As a **frontend engineer**,
I want shadcn/ui initialized in `apps/web` with its theme tokens wired to `packages/design-tokens/`,
So that every shadcn primitive renders with the DeployAI palette and subsequent component stories can compose without re-theming.

**Acceptance Criteria:**

**Given** design tokens from Story 1.4
**When** shadcn/ui is initialized
**Then** `apps/web/components.json` is present with `style: "new-york"`, `tailwind.baseColor: "neutral"`, CSS variables enabled
**And** the core shadcn set is installed: Button, Input, Textarea, Label, Form, Dialog, DropdownMenu, ContextMenu, Command, Popover, HoverCard, Tooltip, Tabs, Separator, Card, Sheet, Badge, Avatar, Progress, ScrollArea, Accordion, Collapsible, Sonner
**And** `apps/web/src/styles/globals.css` defines `--primary`, `--destructive`, `--muted`, etc. sourced from `@deployai/design-tokens`
**And** a Storybook story `Foundations/ButtonVariants.stories.tsx` renders primary/secondary/ghost/destructive variants matching `UX-DR39` button hierarchy
**And** `react-hook-form` + `zod` are installed and a reference `ExampleForm.tsx` using shadcn Form + zod resolver passes type-check

### Story 1.6: Accessibility CI gate stack (CI-blocking from day one)

As a **UX designer and a developer**,
I want a full axe-core + ESLint a11y + pa11y CI stack running and blocking every PR,
So that the product is accessible by construction, not audit (NFR43, UX-DR34) — no fifteen-week accessibility-debt window.

**Acceptance Criteria:**

**Given** any React or Storybook code lands in `apps/web`
**When** a PR is opened
**Then** `eslint-plugin-jsx-a11y` runs at `error` severity with zero violations tolerated (CI-blocking)
**And** `@storybook/addon-a11y` runs axe-core against every Storybook story; any new `axe-core` violation fails CI
**And** `@axe-core/react` is wired in dev mode to log runtime violations to console
**And** `axe-playwright` is integrated into Playwright E2E tests with a baseline assertion on the homepage
**And** `pa11y-ci` runs contrast + landmark checks against a list of critical routes (initially just `/`) and fails CI on regression
**And** `.github/workflows/a11y.yml` documents the gate and is branch-protected on `main`
**And** `docs/a11y-gates.md` explains each gate's scope and appeal process

### Story 1.7: docker-compose reference dev environment (NFR77)

As a **new engineer**,
I want a single `docker-compose up` command that brings up the complete DeployAI local stack with seeded fixtures in ≤ 30 minutes,
So that onboarding does not bottleneck on tribal knowledge and NFR77 dev-env-parity is verified in CI.

**Acceptance Criteria:**

**Given** a fresh clone of the repository on reference hardware (16 GB RAM, Docker Desktop)
**When** an engineer runs `make dev` (which invokes `docker compose -f infra/compose/docker-compose.yml up`)
**Then** Postgres 16 (with `pgvector` and `pgcrypto` extensions preinstalled), Redis 7, MinIO, a FreeTSA stub, and all DeployAI services come up healthy within ≤ 30 minutes wall-clock
**And** a seed script (`infra/compose/seed/seed.sh`) populates a synthetic tenant with ≥ 20 canonical events, ≥ 5 stakeholders, and a sample phase state
**And** `make dev-verify` runs a smoke test asserting every service returns healthy on its `/health` endpoint
**And** a GitHub Actions job `compose-smoke.yml` runs `make dev && make dev-verify` on a clean Ubuntu runner on every PR and fails if wall-clock exceeds 30 min
**And** `docs/dev-environment.md` documents prerequisites and troubleshooting
**And** `apps/web` at `http://localhost:3000` and the admin shell at `/admin/runs` render without error

### Story 1.8: Canonical memory schema — event log + identity graph + solidified-learning library + tombstones

As a **Data Plane engineer**,
I want a complete Alembic-managed canonical memory schema including the immutable event log, time-versioned identity graph, solidified-learning library with lifecycle states, and tombstone table,
So that every ingested event from Epic 3 has a canonical home and every downstream agent (Epic 6) reads from a stable contract.

**Acceptance Criteria:**

**Given** a fresh Postgres 16 database on the "derivatives" cluster
**When** `alembic upgrade head` runs
**Then** tables are created: `canonical_memory_events`, `identity_nodes`, `identity_attribute_history`, `solidified_learnings`, `learning_lifecycle_states`, `tombstones`, `schema_proposals`
**And** every table has `tenant_id UUID NOT NULL`, `created_at TIMESTAMPTZ NOT NULL`, and a UUID v7 primary key
**And** `canonical_memory_events` is append-only — a database trigger raises an exception on any `UPDATE` or `DELETE`
**And** `solidified_learnings` carries `{belief TEXT, evidence_event_ids UUID[], application_trigger JSONB, state ENUM('candidate','solidified','overridden','tombstoned')}`
**And** `tombstones` carries `{original_node_id, retention_reason, authority_actor_id, destroyed_at, signature, tsa_timestamp}`
**And** an `identity_nodes` row represents one canonical person; `identity_attribute_history` tracks time-versioned role/title/email changes (FR2, DP11)
**And** a `supersession_link` pattern allows duplicate-identity resolution to a single canonical (FR3)
**And** migrations follow the expand-contract pattern (NFR74); a CI check rejects any in-place `ALTER COLUMN` of a canonical-memory table without a corresponding expand-then-contract sequence
**And** `services/control-plane/tests/integration/test_canonical_memory_schema.py` covers happy-path inserts, append-only enforcement, and attribute-history versioning

### Story 1.9: Three-layer tenant isolation (RLS + envelope encryption + TenantScopedSession)

As a **security engineer**,
I want every canonical-memory table protected by Postgres RLS, every sensitive field envelope-encrypted under a per-tenant KMS-wrapped DEK, and every SQLAlchemy session injected with a tenant scope,
So that cross-tenant reads are architecturally impossible and NFR23 is enforced at three independent layers.

**Acceptance Criteria:**

**Given** multiple tenants provisioned in Postgres
**When** a service opens a session via `TenantScopedSession(tenant_id=X)`
**Then** every SQLAlchemy `Query` automatically filters by `tenant_id = X`
**And** the session issues `SET LOCAL app.current_tenant = 'X'` before any query
**And** every canonical-memory table has an RLS policy `tenant_rls_<table> USING (tenant_id = current_setting('app.current_tenant')::uuid)`
**And** sensitive fields (`evidence_span` payload, `private_annotation` body, `raw_transcript_content`) are stored encrypted under a per-tenant DEK via `pgcrypto` `pgp_sym_encrypt` with the DEK fetched through an AWS KMS envelope decrypt
**And** unit tests assert `TenantScopedSession` raises on missing `tenant_id`
**And** integration tests attempt a cross-tenant read without the session context and assert an exception is raised
**And** `services/_shared/tenancy.py` is the single source of truth for `TenantScopedSession` and exports a `@requires_tenant_scope` decorator

### Story 1.10: Cross-tenant isolation fuzz CI gate (NFR52)

As a **security engineer**,
I want a CI-gated fuzz harness that actively attempts unauthorized cross-tenant reads across every canonical-memory table and fails the build on any success,
So that the isolation contract from Story 1.9 cannot silently regress (NFR52).

**Acceptance Criteria:**

**Given** the three-layer isolation from Story 1.9
**When** `pnpm turbo run fuzz:cross-tenant` runs in CI
**Then** the harness provisions ≥ 3 synthetic tenants with ≥ 50 rows each in every canonical-memory table
**And** ≥ 500 fuzzed queries per table attempt cross-tenant reads via SQL injection vectors, RLS bypasses (`SET ROLE`, `SET SESSION AUTHORIZATION`), and ORM escape hatches
**And** every attempt fails with either an RLS permission denial or an `IsolationViolation` exception; any successful cross-tenant read fails the CI job
**And** the harness emits a structured JSON report to `artifacts/fuzz/cross-tenant-report.json` for audit
**And** `.github/workflows/fuzz.yml` runs the harness on every PR touching `services/*`, `packages/tenancy/*`, or Alembic migrations
**And** `docs/security/cross-tenant-fuzz.md` documents the attack surface and interpretation of the report

### Story 1.11: Citation envelope contract v0.1 with versioning policy

As a **platform engineer**,
I want the citation envelope contract frozen at v0.1 with a formal versioning policy enforced by CI,
So that every agent output across Epics 4–12 conforms to a stable, evolvable contract (FR27, NFR55).

**Acceptance Criteria:**

**Given** the need for a single citation contract
**When** the contract is published
**Then** `packages/contracts/src/citation-envelope.ts` exports a Zod + Pydantic-compatible schema requiring `{node_id: UUID, graph_epoch: int, evidence_span: {start: int, end: int, source_ref: str}, retrieval_phase: enum, confidence_score: float in [0,1], signed_timestamp: ISO8601}`
**And** the schema declares `schema_version: "0.1.0"` (semver) with an explicit changelog at `packages/contracts/CHANGELOG.md`
**And** `pnpm run contract:check` validates that additions are expand (new optional field) and rejects breaking changes without a migration artifact at `migrations/contracts/<semver>.md`
**And** contract tests under `packages/contracts/tests/envelope.contract.test.ts` cover required-field rejection, malformed `evidence_span`, out-of-range `confidence_score`, and unknown `retrieval_phase`
**And** `services/_shared/citation.py` exports the equivalent Pydantic model auto-generated from the Zod schema via a shared JSON Schema intermediate
**And** `docs/contracts/citation-envelope.md` documents each field's semantics

### Story 1.12: Continuity-of-reference contract tests (NFR52)

As a **platform engineer**,
I want four contract tests (same-node-resolution, visual-token parity, context-neighborhood, state-propagation) runnable against any surface and gating every release,
So that FR41–43's continuity-of-reference guarantee is verifiable from day one rather than retrofitted after surfaces exist.

**Acceptance Criteria:**

**Given** the citation envelope contract from Story 1.11
**When** `pnpm turbo run contract:continuity` runs
**Then** the `same-node-resolution` test asserts that a given `node_id` resolves to identical canonical data regardless of which surface invokes the resolver
**And** the `visual-token parity` test asserts that a fixture `CitationChip` render uses only tokens declared in `@deployai/design-tokens` (no ad-hoc styles)
**And** the `context-neighborhood` test asserts that the relationship context (stakeholder peers, active blockers, recent events) of a cited node is stable across surface invocations minus documented zoom-level collapses
**And** the `state-propagation` test asserts that overriding a node's state (`overridden`, `tombstoned`) propagates to every surface's render within one refresh cycle
**And** all four tests run against a fixture set of ≥ 10 nodes spanning 3 tenants and 5 phase contexts
**And** the tests are wired to `.github/workflows/release-gate.yml` and block any release candidate that fails

### Story 1.13: RFC 3161 signed timestamps (FreeTSA primary + AWS fallback, batched)

As a **compliance engineer**,
I want every canonical-memory event node, audit log entry, and FOIA artifact signed with an RFC 3161 timestamp rooted in an independent public trust chain,
So that NFR19 is satisfied and FOIA export chain-of-custody (FR61) is verifiable offline by any third party.

**Acceptance Criteria:**

**Given** a canonical-memory event is appended
**When** the signing service runs
**Then** `services/_shared/tsa.py` requests an RFC 3161 timestamp from FreeTSA (`https://freetsa.org/tsr`) using `rfc3161-client`
**And** FreeTSA failure falls back to an AWS-native TSA with an independent trust chain
**And** event-node writes are batched every 5 s to amortize TSA cost (ingest rate ≥ 500 events/account/day per NFR6)
**And** every event has `signed_timestamp` (RFC 3161 TSR bytes) persisted; a verifier can validate the signature against FreeTSA's public key without calling DeployAI services
**And** `packages/foia-verifier/` (stub used by Epic 12 Go CLI) includes the FreeTSA public cert and a verification routine
**And** integration test `test_tsa_batch_sign.py` asserts ≥ 100 events/batch are signed and verifiable

### Story 1.14: LLM provider abstraction interface

As a **platform engineer**,
I want an `LLMProvider` interface frozen in `packages/llm-provider/` with a stub implementation,
So that Epic 4's replay-parity harness and Epic 5's real agents both consume the same contract, and provider failover (NFR70) is a config flag rather than a refactor.

**Acceptance Criteria:**

**Given** the need for dual-provider failover (NFR70)
**When** the interface is frozen
**Then** `packages/llm-provider/src/provider.ts` exports `LLMProvider` with methods `chat_complete(messages, options)`, `embed(text)`, `capabilities() -> CapabilityMatrix`
**And** a Python equivalent lives at `packages/llm-provider-py/src/provider.py` with the same method signatures
**And** a `StubProvider` implementation returns deterministic canned responses for test fixtures
**And** `services/config/llm-capability-matrix.yaml` declares per-agent capability expectations (Cartographer: extraction, Oracle: retrieval, Master Strategist: arbitration) and a CI job validates every concrete provider meets the matrix
**And** the interface supports a config-flag switchover targeting ≤ 10 min failover (NFR70) — tested via a unit test that swaps providers and asserts equivalent capability coverage
**And** Epic 5 provides concrete Anthropic and OpenAI implementations

### Story 1.15: Tauri signed Hello-World spike (macOS)

As a **platform engineer**,
I want a minimal Tauri 2.x Hello-World app signed, notarized, and verified on a clean macOS VM,
So that edge-agent platform risk (Apple Developer cert setup, hardened-runtime notarization, Sparkle feed signing, Keychain I/O) is retired at week 3–4 rather than discovered at week 19 (Epic 11).

**Acceptance Criteria:**

**Given** a Tauri scaffold in `apps/edge-agent`
**When** the signed Hello-World spike is complete
**Then** `apps/edge-agent` builds a signed `.app` bundle via `pnpm tauri build` on macOS
**And** the binary is notarized against an Apple Developer ID and passes `spctl --assess` on a clean macOS VM
**And** a minimal Rust sidecar in `apps/edge-agent/src-tauri/src/crypto.rs` performs a round-trip Keychain write + read of a test string
**And** a minimal audio-permission prompt appears on first launch and is documented in `apps/edge-agent/docs/permissions.md`
**And** a Sparkle-compatible auto-update feed stub lives at `apps/edge-agent/dist/appcast.xml` signed with an ed25519 key
**And** the CI job `.github/workflows/edge-agent-spike.yml` runs the signed build on a macOS runner and uploads the artifact
**And** `docs/edge-agent/platform-assessment.md` documents any platform pain discovered (permissions, entitlements, signing quirks) — output informs Epic 11 scoping

### Story 1.16: Minimal admin shell (`/admin/runs`)

As an **engineer**,
I want a minimal admin shell at `/admin/runs` rendered with shadcn primitives and behind a Platform Admin role check,
So that weeks 7–15 of ingestion and agent work have a visible cockpit rather than flying blind for 10 weeks (per Party Mode Sally).

**Acceptance Criteria:**

**Given** the shadcn/ui init from Story 1.5 and the `AuthzResolver` interface from Story 1.14 via Epic 2's role matrix
**When** an authenticated Platform Admin navigates to `/admin/runs`
**Then** a shadcn `Table` renders a list of recent ingestion runs with columns (tenant, source, started_at, status, event_count)
**And** a shadcn `Sheet` opens a detail pane on row click, showing raw run metadata
**And** unauthorized users receive a 403 with a plain-language error
**And** `apps/web/src/app/(internal)/admin/runs/page.tsx` exists with React Server Components for the shell and a Client Component for the filterable table
**And** the page is excluded from the public sitemap and from the marketing nav
**And** `axe-playwright` passes on the rendered page with zero violations

### Story 1.17: Cartographer schema-evolution staging + Platform Admin promotion flow (FR76)

As a **Platform Admin**,
I want Cartographer-proposed new fields written to a staging area that I explicitly promote to the canonical schema,
So that V1 substrate evolves under explicit human review rather than silent schema drift (FR76, DP7/DP8).

**Acceptance Criteria:**

**Given** Cartographer (stub at Epic 1, real at Epic 6) proposes a new entity field
**When** the proposal is written
**Then** the proposal lands in the `schema_proposals` table (tenant-scoped) with `{proposer_agent, proposed_field_path, proposed_type, sample_evidence, status: 'pending'}`
**And** a Platform Admin surface at `/admin/schema-proposals` lists pending proposals with promote/reject actions
**And** `Promote` triggers an Alembic migration scaffold emitted to `migrations/schema-proposals/<proposal_id>.py` (expand step) and updates the staging row to `status: 'promoted'`
**And** `Reject` records a reason string; the proposal is retained for audit
**And** promoted fields only become queryable after the migration lands in `main` via CI
**And** integration test covers the full propose → admin-review → promote → migration flow


---

## Epic 2: Identity, Tenancy & SSO

Wire Microsoft Entra ID SAML/OIDC and SCIM 2.0 provisioning, implement the tenant-scoped role matrix through the `AuthzResolver` interface, stand up Redis-backed sessions, and scaffold kill-switch + break-glass plumbing (end-to-end operability completes in Epic 12).

### Story 2.1: Role matrix and `AuthzResolver` interface

As a **platform engineer**,
I want a frozen `AuthzResolver` interface and a documented role matrix enforcing tenant-scoped authorization,
So that every Epic 3–12 story can call a single, swappable authorization abstraction (future OpenFGA/ReBAC migration path per AR15).

**Acceptance Criteria:**

**Given** the need for a single authorization contract
**When** the resolver is published
**Then** `packages/authz/src/resolver.ts` exports `AuthzResolver.canAccess(actor, action, resource) -> Decision` and `services/_shared/authz.py` exports its Python equivalent
**And** `packages/authz/src/roles.ts` enumerates V1 roles: `deployment_strategist`, `successor_strategist` (V1.5 active), `platform_admin`, `customer_records_officer`, `external_auditor`, `customer_admin` (V1.5 active)
**And** `docs/authz/role-matrix.md` maps each role × capability (ingest, view-canonical, override, solidification-promote, FOIA-export, break-glass, SCIM-manage) with V1 / V1.5 markers
**And** RLS policies from Story 1.9 are extended with per-role predicates where needed
**And** every `AuthzResolver` decision emits a structured audit log entry (NFR59)
**And** contract tests cover each role's allowed and denied capability set

### Story 2.2: Microsoft Entra ID SAML + OIDC SSO (FR71)

As a **customer IT admin**,
I want to provision DeployAI users via Microsoft Entra ID SAML or OIDC,
So that FR71 is satisfied and the NYC DOT anchor does not require custom identity integration.

**Acceptance Criteria:**

**Given** an Entra ID tenant with a DeployAI enterprise application configured
**When** a user completes SSO via the `/auth/login` route
**Then** the SAML assertion is verified via `python3-saml` against the configured IdP metadata
**And** the OIDC alternative path is verified via `authlib` with PKCE
**And** on first successful login, the user is JIT-provisioned into the DeployAI user table with role defaulting to `pending_assignment` until a Platform Admin assigns a tenant and role
**And** a signed JWT (15-min access + 7-day refresh, Redis-backed) is issued and cookie-stored with `HttpOnly; Secure; SameSite=Lax`
**And** token refresh is handled via `/auth/refresh` and tenant-scoped Redis keys are prefixed `tenant:<uuid>:session:`
**And** integration tests cover SAML happy-path, OIDC happy-path, expired token refresh, and replay-attack rejection
**And** `docs/auth/sso-setup.md` documents the Entra ID configuration steps

### Story 2.3: SCIM 2.0 provisioning endpoint (FR71)

As a **customer IT admin**,
I want to provision and deprovision DeployAI users from Entra ID via SCIM 2.0,
So that user lifecycle is managed centrally and departures trigger automatic access revocation.

**Acceptance Criteria:**

**Given** an Entra ID SCIM provisioning app configured against DeployAI
**When** a user is added, modified, or removed in Entra
**Then** DeployAI exposes `POST /scim/v2/Users`, `PATCH /scim/v2/Users/:id`, `DELETE /scim/v2/Users/:id`, `GET /scim/v2/Users`, `GET /scim/v2/Users/:id` conforming to RFC 7644
**And** authentication uses a SCIM bearer token scoped to the customer tenant
**And** user deprovision via `DELETE` sets the user's status to `deactivated`, revokes all sessions in Redis, and emits an audit event
**And** attributes supported: `userName`, `name.givenName`, `name.familyName`, `emails`, `active`, `roles`
**And** integration tests exercise each endpoint with Entra SCIM request fixtures
**And** `docs/auth/scim-setup.md` documents setup

### Story 2.4: Tenant-scoped session store (AR9)

As a **platform engineer**,
I want signed-JWT session issuance and Redis-backed refresh with tenant-prefixed keys and TLS 1.3 in transit,
So that sessions scale across services, are revocable on kill-switch, and never leak cross-tenant (AR9).

**Acceptance Criteria:**

**Given** authenticated users from Story 2.2
**When** sessions are issued
**Then** every JWT payload includes `{sub: user_id, tid: tenant_id, roles: [...], iat, exp, jti}` signed with RS256
**And** refresh tokens are stored in Redis under `tenant:<tid>:session:<jti>` with TTL matching the 7-day refresh window
**And** all Redis connections use TLS 1.3 with mutual cert verification (ACM-managed)
**And** a `POST /auth/logout` invalidates the refresh token immediately
**And** a `POST /auth/sessions/revoke-all/:user_id` (Platform Admin only) deletes every session key under that user's tenant prefix and emits an audit event
**And** NFR76 (OAuth refresh rotation per-provider + JWT signing keys ≤ 180 days) is satisfied via KMS-backed key rotation

### Story 2.5: Account provisioning flow (FR70)

As a **Platform Admin**,
I want to provision a new account, assign the initial Deployment Strategist, and establish an empty canonical memory baseline with tenant-scoped encryption context,
So that FR70 is satisfied and each new NYC DOT-style anchor goes live with isolation verified.

**Acceptance Criteria:**

**Given** a Platform Admin authenticated via Story 2.2
**When** the admin invokes `POST /platform/accounts` with `{organization_name, initial_strategist_email}`
**Then** a new tenant UUID is minted
**And** a per-tenant KMS DEK is generated and wrapped with the CMK via AWS KMS envelope encryption (AR4)
**And** an empty canonical memory baseline is created (event log, identity graph, solidified-learning library all empty but schema-present)
**And** the initial strategist is created (or matched if already provisioned via SSO) and assigned role `deployment_strategist` scoped to this tenant
**And** an audit event `account.provisioned` is emitted with RFC 3161 timestamp
**And** a cross-tenant-fuzz regression test confirms the new tenant cannot read any other tenant's data
**And** integration test covers the full flow end-to-end

### Story 2.6: Integration kill-switch plumbing (FR14, FR17, NFR24)

As a **Deployment Strategist or Platform Admin**,
I want a kill-switch that revokes any integration's access token, purges its in-flight queue, and emits an audit event within 30 s,
So that FR14/FR17 are satisfied and compromised integrations can be contained quickly (NFR24).

**Acceptance Criteria:**

**Given** an active integration (M365 Calendar, Email, Teams — all from Epic 3)
**When** the strategist or admin toggles the kill-switch via `POST /integrations/:id/disable`
**Then** the integration's OAuth refresh token is revoked against the provider
**And** the in-flight SQS queue for that integration is purged
**And** all credentials are deleted from AWS Secrets Manager
**And** an audit event `integration.killswitch_triggered` is emitted with RFC 3161 signed timestamp within ≤ 30 s end-to-end (p95)
**And** the integration state transitions to `disabled` and is not resumable without re-consent
**And** a test asserts wall-clock end-to-end ≤ 30 s on the reference compose stack

### Story 2.7: Break-glass plumbing (FR64 infrastructure only; end-to-end in Epic 12)

As a **platform engineer**,
I want the break-glass infrastructure (dual-approval session flag + IAM Identity Center hook + audit event schema) in place,
So that Epic 12 can wire the end-to-end customer-notification + session banner without building infrastructure at the last minute.

**Acceptance Criteria:**

**Given** the need for multi-party authorized Platform Admin tenant-data access (FR64, NFR21)
**When** break-glass plumbing lands
**Then** the schema `break_glass_sessions {session_id UUID, initiator_user_id, approver_user_id, tenant_id, requested_scope, status ENUM('requested','approved','active','expired','denied'), requested_at, approved_at, expires_at (≤ 4hr), revoked_at, audit_transcript_ref}` is migrated (AR4-isolated)
**And** `POST /break-glass/request`, `POST /break-glass/approve/:session_id`, `DELETE /break-glass/:session_id` endpoints exist and are `platform_admin`-gated requiring hardware-backed authentication (WebAuthn)
**And** the approval requires a second `platform_admin` different from the initiator (dual-approval enforced)
**And** an audit event schema `audit_events.break_glass.*` is published in `packages/contracts/audit-events.schema.json`
**And** the session flag is readable by Epic 12's SessionBanner wire-up
**And** end-to-end customer notification + banner UI + transcript delivery is NOT implemented here (Epic 12)
**And** unit + integration tests cover dual-approval enforcement, 4-hr auto-expiry, WebAuthn requirement

---

## Epic 3: Ingestion Pipelines

Ship the V1 ingestion surface area — M365 Calendar + Email OAuth pulls, Teams transcript import, direct voice/meeting upload, thread-level extraction, backpressure, and an admin `/admin/runs` wire-up.

### Story 3.1: M365 Calendar OAuth ingestion (FR9)

As a **Deployment Strategist**,
I want to ingest calendar events from Microsoft 365 Calendar via authenticated OAuth,
So that every meeting becomes a canonical event with no manual data entry (FR9).

**Acceptance Criteria:**

**Given** a strategist with M365 Calendar configured
**When** they authorize DeployAI via the OAuth flow at `/integrations/m365-calendar/connect`
**Then** DeployAI uses Microsoft Graph to pull calendar events
**And** every event is written as a canonical event node with `event_type = 'calendar.event'`, `payload = <Graph event subset>`, and an RFC 3161 signed timestamp
**And** incremental sync is handled via Microsoft Graph's delta query; no duplicate events produced on repeated sync (idempotent per FR18)
**And** the SQS ingestion queue handles the Graph payload and persists on success; failure with exponential backoff (base 2 s, max 5 min, 72-hr retention per NFR12)
**And** integration tests cover: happy-path sync of 20 events, delta sync, Graph 429 throttling with backoff, 72-hr outage recovery

### Story 3.2: Exchange / M365 Email OAuth ingestion (FR10)

As a **Deployment Strategist**,
I want to ingest email from Exchange / M365 via authenticated OAuth,
So that email threads become canonical events at the thread-level unit of extraction (FR10, FR16).

**Acceptance Criteria:**

**Given** a strategist's M365 mailbox is authorized
**When** new email arrives in a monitored folder
**Then** DeployAI pulls the thread via Microsoft Graph and writes it as a single canonical event node `event_type = 'email.thread'` (not per-message, per FR16)
**And** the thread payload includes `{subject, participants: [...], messages: [{from, to, sent_at, body_ref}], thread_id}`
**And** message bodies are stored in S3 under tenant-scoped prefix (AR11) with the canonical event storing `body_ref`
**And** incremental sync via Graph delta; idempotent on retry (FR18)
**And** throttling-aware backpressure respects Graph rate limits (NFR19)
**And** integration tests cover: new-thread sync, thread-update append, throttled retry

### Story 3.3: Microsoft Teams transcript import (FR11)

As a **Deployment Strategist**,
I want to import Microsoft Teams meeting transcripts,
So that meeting content becomes canonical events at the session-level unit of extraction (FR11, FR16).

**Acceptance Criteria:**

**Given** a Teams-authorized tenant
**When** a meeting ends and its transcript becomes available via Graph
**Then** DeployAI pulls the transcript and writes it as a canonical event `event_type = 'meeting.transcript'`
**And** the payload structure mirrors FR16's session-unit extraction
**And** participants are matched against the identity graph; unmatched participants create identity-node candidates for later disambiguation (FR3)
**And** transcripts ≥ 60 min are chunked at ingest for Epic 6's Cartographer map-reduce boundary
**And** integration tests cover: happy-path import, participant match, unmatched-participant candidate creation

### Story 3.4: Voice / meeting file upload (FR12, NFR39)

As a **Deployment Strategist**,
I want to upload voice or meeting recording files directly through the web app,
So that off-platform meetings become canonical events without bot-join or cloud-hosted recording intermediaries in the data path (FR12, NFR39).

**Acceptance Criteria:**

**Given** a strategist on the `/upload` surface
**When** they upload an audio/video file (mp3/mp4/m4a/wav ≤ 500 MB)
**Then** the file is uploaded directly to tenant-scoped S3 via a signed presigned POST URL (no intermediate server buffer)
**And** a two-party consent attestation checkbox is required; jurisdiction metadata captured for NFR39
**And** an SQS job triggers transcription via the configured provider (self-hosted Whisper or AWS Transcribe per config)
**And** the resulting transcript is written as canonical event `event_type = 'upload.transcript'`
**And** the original audio file retention follows the 90-day edge-raw-transcript retention contract (NFR33)
**And** integration test covers: upload → transcribe → canonical event with valid citation envelope

### Story 3.5: Thread-level / session-level extraction unit enforcement (FR16)

As a **platform engineer**,
I want the ingestion contract to enforce thread- or session-unit extraction before Cartographer touches it,
So that FR16 is guaranteed architecturally, not merely by Cartographer's good behavior.

**Acceptance Criteria:**

**Given** any canonical event
**When** it is published to the extraction queue (consumed by Cartographer in Epic 6)
**Then** a contract validator in `services/ingest/validators.py` asserts the event is thread-unit or session-unit (never per-message)
**And** messages-as-individual-units are rejected at the boundary with an audit event
**And** unit tests cover: reject per-message event, accept thread-unit event, accept session-unit event

### Story 3.6: Transient-failure tolerance + idempotent writes (FR18, NFR12)

As a **platform engineer**,
I want ingestion to tolerate transient upstream failures with bounded-retry and idempotent-write semantics so duplicate deliveries produce at-most-once canonical events,
So that FR18 and NFR12 are satisfied under real-world provider flakiness.

**Acceptance Criteria:**

**Given** any ingestion SQS job
**When** the upstream pull fails with a 5xx or timeout
**Then** the job retries with exponential backoff (base 2 s, max 5 min) for up to 72 hr
**And** after 72 hr, the job moves to a DLQ with an alert
**And** every canonical-event write is idempotent: the ingestion key `<provider>:<source_id>:<version>` is unique, and duplicate deliveries UPSERT the existing canonical event (no duplicate nodes)
**And** integration tests simulate: intermittent 5xx (recovery), sustained 5xx → DLQ, duplicate delivery → single canonical event

### Story 3.7: Throttling-aware backpressure (FR19, NFR19)

As a **platform engineer**,
I want ingestion to respect provider rate limits (Microsoft Graph 429s primarily) via token-bucket batching without data loss,
So that FR19 is satisfied and the platform sustains ≥ 500 events/account/day and ≥ 2,500 events/account/hour (NFR6).

**Acceptance Criteria:**

**Given** Microsoft Graph issues a 429 with `Retry-After`
**When** the ingestion worker receives it
**Then** the worker respects `Retry-After` and applies a per-tenant + per-provider token-bucket rate limiter (default 1000 req/s, configurable)
**And** batch size auto-tunes to p95 throttle avoidance
**And** no event is lost during a throttle storm; all eventually written
**And** load test `tests/load/ingest-throttle.py` drives 2500 events/hour with 10% 429 injection and asserts zero loss + SLA adherence

### Story 3.8: Ingestion run telemetry + admin `/admin/runs` surface wire-up

As an **engineer**,
I want every ingestion run to emit structured telemetry visible at `/admin/runs`,
So that the cockpit from Story 1.16 is alive once ingestion exists and the team can debug without ssh.

**Acceptance Criteria:**

**Given** the admin shell from Story 1.16 and ingestion from Stories 3.1–3.4
**When** an ingestion run starts, progresses, and completes
**Then** a row in `ingestion_runs {run_id, tenant_id, integration, started_at, status, events_written, errors}` persists
**And** the `/admin/runs` table renders live run data with live status via SSE or polling
**And** clicking a run opens a Sheet with full event count, error breakdown, and a link to CloudWatch/Loki traces
**And** `axe-playwright` passes on the `/admin/runs` surface

---

## Epic 4: Agent Runtime Contracts & Replay-Parity Harness

Build the agent substrate contracts and the replay-parity CI gate ahead of real agent work. LangGraph Postgres-checkpointing against a stub agent, citation-aware LlamaIndex adapter, ≥ 200-query golden fixture set, rule-based → LLM-judge → human adjudication cascade, and the 11th-call CI gate turned on.

### Story 4.1: LangGraph Postgres checkpointing against stub agent (AR6)

As a **platform engineer**,
I want LangGraph checkpointing wired to Postgres against a stub agent that emits canned citation envelopes,
So that replay-parity can validate agent behavior before real agents exist (per Party Mode Winston: "you can't validate replay-parity after you build the agent; the harness must exist as acceptance").

**Acceptance Criteria:**

**Given** LangGraph and the Epic 1 LLM abstraction interface
**When** a stub agent runs
**Then** `services/cartographer/stub_graph.py` defines a simple 3-node LangGraph state machine
**And** state checkpoints persist to `services/cartographer/migrations/checkpoints.sql` Postgres tables
**And** `services/_shared/checkpointer.py` wraps LangGraph's `PostgresSaver` with tenant-scoped session injection
**And** every state transition emits a canned citation envelope matching the Epic 1 v0.1 contract
**And** a replay test re-runs the stub from checkpoint and asserts bit-identical output
**And** integration test covers: fresh run, checkpoint dump, replay from checkpoint

### Story 4.2: Citation-aware LlamaIndex adapter (AR7)

As a **platform engineer**,
I want a custom LlamaIndex adapter enforcing the citation envelope contract at the LangGraph-LlamaIndex boundary,
So that agent outputs carrying malformed envelopes are rejected at the boundary (FR27) rather than leaking into surfaces.

**Acceptance Criteria:**

**Given** LlamaIndex retrievers over `pgvector` HNSW indices
**When** a retriever returns nodes to a LangGraph agent
**Then** `packages/llama-citation-adapter/src/adapter.py` wraps `BaseRetriever` and validates every returned node carries a complete citation envelope per Epic 1 contract
**And** nodes failing validation are dropped with a structured log entry + metric `citation_envelope_rejections`
**And** integration test: a malformed node (missing `graph_epoch`) is injected; adapter rejects it; test asserts zero rejected nodes reach the agent
**And** contract test re-validates the envelope schema version on every retrieval call

### Story 4.3: Golden fixture authoring tool + schema

As a **QA engineer**,
I want a fixture authoring tool that produces versioned golden query/expected-citation pairs spanning the 21-cell phase-retrieval audit matrix,
So that the 11th-call gate and replay-parity suites have a stable evaluation corpus (per Party Mode Amelia: "some story needs to produce these").

**Acceptance Criteria:**

**Given** the need for ≥ 200 golden queries (NFR50)
**When** the fixture tool is published
**Then** `tests/golden/` defines `queries/*.yaml` and `expected/*.json` with schema `{query_id, phase, stakeholder_topology, query_text, expected_citations: [{node_id, must_appear, rank_floor}]}`
**And** `pnpm run golden:validate` asserts every query has a phase ∈ {7 phases}, a topology ∈ {3 variants}, and at least one `expected_citation`
**And** the tool `pnpm run golden:author` produces a YAML scaffold for a new query
**And** the fixture covers every cell of the 21-cell matrix (7 phases × 3 topologies) with ≥ 1 query per cell
**And** `docs/testing/golden-fixtures.md` documents the authoring protocol

### Story 4.4: Golden query corpus authoring (≥ 200 queries)

As a **QA engineer collaborating with domain experts**,
I want ≥ 200 golden queries authored covering the 21-cell audit matrix and 5 canonical tenant scenarios,
So that NFR50's 11th-call gate is operable and NFR53's 21-cell phase-retrieval audit runs.

**Acceptance Criteria:**

**Given** the fixture tool from Story 4.3
**When** the corpus is authored
**Then** ≥ 200 queries exist across `tests/golden/queries/*.yaml`
**And** every cell of the 21-cell matrix is covered ≥ 1 query
**And** ≥ 50 queries carry `expected_citations` with high-confidence expected node IDs (authored against the seeded tenant in Story 1.7)
**And** the remaining ≤ 150 queries are marked `judge_only: true` (LLM-judge evaluation, no hard-coded expected)
**And** a CI job emits a dashboard at `artifacts/golden/coverage.html` showing matrix coverage per release
**And** domain research referenced in `docs/testing/golden-corpus-derivation.md` — Note: authoring this corpus requires SME input; allocate 1.5–2 weeks calendar time

### Story 4.5: Rule-based evaluator (tier 1 of replay-parity cascade)

As a **platform engineer**,
I want a rule-based evaluator that exact-matches expected citations in golden queries,
So that tier 1 of the cascade (cheap, deterministic) handles the majority of replay-parity comparisons.

**Acceptance Criteria:**

**Given** the golden corpus from Story 4.4
**When** `pnpm run replay-parity:rules` executes
**Then** `apps/eval/rules/evaluator.py` compares agent output citations against `expected_citations` using exact node-ID matching + rank-floor checks
**And** mismatches are categorized: `missing`, `extra`, `wrong_rank`
**And** results emit to `artifacts/replay-parity/rules-report.json`
**And** unit test covers: exact match (pass), missing citation (fail-missing), extra citation (flag), rank violation (fail-rank)

### Story 4.6: LLM-judge evaluator (tier 2 of replay-parity cascade)

As a **platform engineer**,
I want an LLM-judge evaluator for queries marked `judge_only`,
So that tier 2 handles semantically-equivalent but non-identical citation sets (per FR62's rule → LLM-judge → human cascade).

**Acceptance Criteria:**

**Given** the Epic 1 `LLMProvider` interface with a concrete provider available
**When** `pnpm run replay-parity:judge` executes
**Then** `apps/eval/judge/evaluator.py` prompts the judge LLM with `{query, expected_context, actual_citations}` to evaluate equivalence
**And** judge prompts live in `apps/eval/judge/prompts/*.md` and are version-pinned; any prompt change requires a replay-parity full-suite re-run
**And** the judge emits structured JSON `{decision: 'equivalent'|'divergent'|'uncertain', reasoning, confidence}`
**And** `uncertain` decisions are automatically escalated to tier 3 (human)
**And** integration test: 10 queries with known equivalence labels; judge accuracy ≥ 85% on the labeled set

### Story 4.7: Human adjudication surface `/adjudication` (tier 3 of replay-parity cascade)

As a **QA engineer**,
I want a `/adjudication` internal surface to review judge-uncertain cases and decide final replay-parity outcomes,
So that FR62's human tier is operable and the cascade has a closed loop (per Party Mode Amelia: "missing from the plan; add adjudication surface").

**Acceptance Criteria:**

**Given** judge-uncertain cases from Story 4.6
**When** a QA engineer navigates to `/adjudication`
**Then** a queue of uncertain cases renders via shadcn Table with `{query_text, expected_citations, actual_citations, judge_reasoning, confidence}`
**And** the engineer can choose `equivalent | divergent | blocker` per case with a reason string
**And** decisions persist to `adjudication_decisions` table with `{case_id, adjudicator_user_id, decision, reason, decided_at}`
**And** the surface is `platform_admin` or `qa_engineer` role-gated
**And** `axe-playwright` passes with zero violations
**And** integration test covers: uncertain case appears, adjudicator decides, decision persisted, case removed from queue

### Story 4.8: 11th-call CI gate + quarterly report generator

As a **release engineer**,
I want the 11th-call CI gate turned on blocking any release missing 100% citation-presence, ≥ 95% correctness, or any hallucinated citation,
So that NFR50 is enforced on every merge to `main` and FR63's quarterly Replay-Parity Gate Report is generatable.

**Acceptance Criteria:**

**Given** the cascade from Stories 4.5–4.7
**When** a PR is opened against `main`
**Then** `.github/workflows/release-gate.yml` runs the full cascade on the golden corpus
**And** the gate blocks merge if: any citation is hallucinated (node_id not in canonical memory), or presence < 100%, or correctness < 95%
**And** the gate runs the continuity-of-reference contract suite from Story 1.12 and the cross-tenant fuzz from Story 1.10
**And** the 21-cell phase-retrieval audit matrix runs (NFR53) and blocks on any cell regression
**And** `apps/eval/reports/quarterly.py` emits a PDF-ready Markdown report `artifacts/quarterly-gate-report.md` covering false-regression-rate, false-acceptance-rate, human-disagreement-rate per FR63/NFR56
**And** integration test: a seeded hallucinated citation fails the gate; a clean run passes


---

## Epic 5: Agent Runtime Foundation

Build the agent runtime chassis: concrete LLM provider implementations (Anthropic primary + OpenAI secondary), prompt/tool infrastructure, 7-phase state machine, and tiered solidification classifier.

### Story 5.1: Concrete Anthropic Claude Sonnet 4 provider (AR8)

As a **platform engineer**,
I want a concrete `AnthropicProvider` implementing the Epic 1 `LLMProvider` interface,
So that real agents can invoke Claude Sonnet 4 for extraction, retrieval, and arbitration.

**Acceptance Criteria:**

**Given** the Epic 1 `LLMProvider` interface
**When** the Anthropic provider is published
**Then** `packages/llm-provider-py/providers/anthropic_provider.py` implements `chat_complete` and `embed` against the Anthropic API
**And** streaming responses are supported via async iterators
**And** token usage + cost is emitted as OpenTelemetry metrics tagged with `tenant_id`, `agent_name`, `model`
**And** API keys are fetched from AWS Secrets Manager per-environment (AR10) with 90-day rotation
**And** rate-limit 429s trigger exponential backoff + graceful degradation
**And** unit + integration tests cover happy-path, 429 backoff, 5xx retry, stream cancellation

### Story 5.2: Concrete OpenAI GPT-4o provider with failover (NFR70)

As a **platform engineer**,
I want a concrete `OpenAIProvider` and a `FailoverProvider` that flips from Anthropic to OpenAI via config flag in ≤ 10 min,
So that NFR70 is satisfied when primary provider has an outage.

**Acceptance Criteria:**

**Given** the Anthropic provider from Story 5.1 and the capability-parity matrix `services/config/llm-capability-matrix.yaml`
**When** the OpenAI provider is published
**Then** `packages/llm-provider-py/providers/openai_provider.py` mirrors the `AnthropicProvider` surface against GPT-4o
**And** a `FailoverProvider` wrapper reads the `LLM_PRIMARY_PROVIDER` config flag and routes accordingly
**And** a CI job validates every concrete provider implements all capabilities declared in `llm-capability-matrix.yaml`
**And** a unit test flips the flag and asserts the failover produces capability-equivalent output on a canned prompt
**And** switchover wall-clock is measured ≤ 10 min (inclusive of Unleash flag propagation) in a staging drill

### Story 5.3: Prompt infrastructure + tool-calling scaffolding

As a **platform engineer**,
I want versioned prompt templates and tool-calling scaffolding shared across Cartographer, Oracle, and Master Strategist,
So that Epic 6 agents compose reusable prompt primitives rather than reinventing them.

**Acceptance Criteria:**

**Given** the need for prompt reuse
**When** the prompt infrastructure lands
**Then** `services/_shared/prompts/` hosts versioned Markdown prompt templates with Jinja2-style variable injection
**And** a `PromptRegistry` resolves `prompt_name` + `version` to a rendered template
**And** version bumps require an entry in `docs/prompts/CHANGELOG.md` and trigger a full replay-parity run (per Story 4.6's prompt-change rule)
**And** tool definitions for agents are declared in `services/_shared/tools/` as JSON Schema + Python handlers
**And** unit tests cover: template rendering, version resolution, tool invocation mock

### Story 5.4: 7-phase deployment framework state machine

As a **Deployment Strategist**,
I want the 7-phase deployment framework encoded as a state machine with transition rules and guard conditions,
So that FR30's phase tracking has a canonical source of truth used by Cartographer, Oracle, and Master Strategist.

**Acceptance Criteria:**

**Given** the 7-phase DeployAI Deployment Framework (documented in PRD Domain section)
**When** the state machine lands
**Then** `services/control-plane/phases/state_machine.py` declares phases `{P1_pre_engagement, P2_discovery, P3_ecosystem_mapping, P4_design, P5_pilot, P6_scale, P7_inheritance}` (or canonical labels per PRD)
**And** transitions require a `PhaseTransitionProposal` with `{from_phase, to_phase, evidence_event_ids, proposer_agent, reason}`
**And** only a Deployment Strategist can confirm/reject a proposal (FR31)
**And** the machine emits events `phase.transition_proposed` and `phase.transition_confirmed` to the audit log with RFC 3161 timestamps
**And** unit tests cover: valid transition, invalid transition rejection, concurrent proposal handling
**And** integration test: propose → strategist confirms → phase updates atomically

### Story 5.5: Tiered solidification classifier (FR28)

As a **platform engineer**,
I want a tiered solidification classifier (Class A auto-solidify / Class B weekly review queue),
So that FR28 is satisfied and high-confidence structured-source extractions solidify while medium-confidence pattern extractions queue for human review.

**Acceptance Criteria:**

**Given** candidate learnings produced by Cartographer (Epic 6 stub)
**When** the classifier runs
**Then** `services/control-plane/classifier.py` computes `classification ∈ {'class_A_auto_solidify', 'class_B_weekly_review'}` per learning
**And** Class A: structured sources (calendar metadata, SCIM-synced roles) with confidence ≥ 0.9
**And** Class B: pattern extractions (inferred blockers, relationship strength signals) with confidence ∈ [0.6, 0.9)
**And** Class A auto-transitions `solidified_learnings.state` to `solidified` with audit event
**And** Class B inserts into `solidification_review_queue` for Epic 9's UI
**And** learnings below 0.6 remain `candidate` and do not surface
**And** unit tests cover: structured high-conf → A, pattern mid-conf → B, low-conf → stays candidate

### Story 5.6: Phase-context modulation of retrieval + confidence thresholds (FR32)

As a **platform engineer**,
I want retrieval ranking, digest priorities, and alert confidence thresholds modulated by the current phase context,
So that FR32 is satisfied — what's surfaced in P2 Discovery differs from what's surfaced in P5 Pilot.

**Acceptance Criteria:**

**Given** a tenant's current phase from Story 5.4
**When** any retrieval query runs
**Then** `services/_shared/retrieval/phase_modulator.py` applies a per-phase weight profile to ranked candidates
**And** In-Meeting Alert confidence thresholds tighten in P5/P6 (high-stakes) vs P2 (exploratory)
**And** Digest priorities include phase-specific content buckets
**And** an A/B contract test asserts identical inputs + different phase produce different-but-valid ranked outputs
**And** integration test covers: same query in P2 vs P5 produces per-phase-appropriate ranking

---

## Epic 6: Cartographer, Oracle & Master Strategist

Build the three real agents on Epic 5's foundation.

### Story 6.1: Cartographer — mission-relevance triage (FR15)

As a **Cartographer agent**,
I want to perform mission-relevance triage BEFORE extraction on every event,
So that FR15 is satisfied: irrelevant events never consume extraction budget, and "mission" is computed from phase + declared objectives rather than user-declared per-event.

**Acceptance Criteria:**

**Given** a canonical event from Epic 3 and the tenant's current phase from Story 5.4
**When** Cartographer receives the event
**Then** `services/cartographer/triage.py` scores relevance ∈ [0, 1] based on `{phase, declared_objectives, event_participants, event_keywords}`
**And** events below `relevance_threshold` (default 0.3, configurable) are marked `triaged_out` with reason and skipped
**And** triage decisions are logged but do not consume LLM tokens for extraction
**And** triage emits metric `cartographer_triage_rate` tagged by tenant + phase
**And** integration test: 100 mixed events → triage correctly filters irrelevant

### Story 6.2: Cartographer — entity / relationship / blocker / candidate-learning extraction (FR20)

As a **Cartographer agent**,
I want to extract entities, relationships, blockers, and candidate learnings from triaged events grounded exclusively in canonical memory,
So that FR20 is satisfied and DP1 (no external inference) is enforced.

**Acceptance Criteria:**

**Given** a triage-passed event
**When** Cartographer extracts
**Then** `services/cartographer/extract.py` uses chunked-extract + map-reduce (NFR48: 40-message thread OR 60-min transcript ≤ 5 min p95)
**And** extracted entities, relationships, blockers, candidate learnings are written to canonical memory with citation envelopes pointing back to the source event
**And** extraction prompts forbid external inference (DP1) — the prompt includes only canonical-memory context, no open-web
**And** a replay-parity contract test asserts bit-identical output on re-extraction of the same event
**And** integration test: email thread → entities + relationships + blockers correctly extracted with valid envelopes
**And** load test: 60-min transcript completes ≤ 5 min p95

### Story 6.3: Oracle — phase-gated retrieval + Corpus-Confidence Marker + Null-Result (FR22, FR23, FR24)

As an **Oracle agent**,
I want to retrieve phase-appropriate learnings with a Corpus-Confidence Marker, explicit Null-Result, and phase-suppression,
So that FR22/23/24 are satisfied: no phase-inappropriate surfaces, confidence always visible, null results explicit rather than hallucinated.

**Acceptance Criteria:**

**Given** a retrieval request with a tenant + phase context
**When** Oracle runs
**Then** `services/oracle/retrieve.py` queries `pgvector` HNSW filtered by phase + tenant via the citation-aware LlamaIndex adapter (Story 4.2)
**And** results are ranked by `contextual_fit_score` considering phase, evidence recency, and confidence
**And** every response carries a `corpus_confidence_marker ∈ {high, medium, low, null}` computed from the distribution of result scores
**And** when zero phase-appropriate results exist, Oracle returns an explicit Null-Result with a reason string rather than substituting phase-inappropriate content
**And** at phase-ambiguity, Oracle returns a union of phase-eligible results with phase labels attached (FR23)
**And** integration test covers: high-conf retrieval, null-result, phase-ambiguity union

### Story 6.4: Oracle — 3-item hard budget + "What I Ranked Out" (FR22, FR24)

As an **Oracle agent**,
I want to enforce a 3-item hard budget on In-Meeting Alerts and append a "What I Ranked Out" footer naming suppressed candidates,
So that FR22's budget and FR24's footer are enforced at the agent boundary (not surface-level discretion).

**Acceptance Criteria:**

**Given** a ranked candidate list for an In-Meeting Alert
**When** Oracle emits the response
**Then** at most 3 items appear in the primary response
**And** the response includes a `ranked_out` array naming suppressed candidates with 1-line reasons
**And** Morning Digest enforces the same 3-item top (FR34) with a footer
**And** contract test asserts `len(response.primary) ≤ 3` for every Alert emission
**And** integration test: 20 candidates → 3 primary + 17 ranked_out

### Story 6.5: Oracle — suggestions-only posture (FR25)

As an **Oracle agent**,
I want every surface item to be a suggestion explicitly awaiting user confirmation — never auto-executed,
So that FR25 and DP10 are preserved.

**Acceptance Criteria:**

**Given** any Oracle output
**When** the output is published
**Then** every item carries `action_posture: 'suggestion'` and no auto-execute field
**And** a contract test asserts no Oracle output carries `action_posture: 'executed'` without a companion override-event (which is user-driven anyway)
**And** code review checklist in `docs/standards/agent-posture.md` flags any PR that introduces auto-execute paths

### Story 6.6: Master Strategist — internal arbitration + Action Queue ranking (FR26)

As a **Master Strategist agent**,
I want to arbitrate proposals from Cartographer and Oracle, rank the Action Queue, and escalate low-confidence items to the User Validation Queue,
So that FR26 is satisfied (V1 internal-only, no user-facing UI per DP10).

**Acceptance Criteria:**

**Given** proposals from Cartographer + Oracle
**When** Master Strategist runs
**Then** `services/master_strategist/arbitrate.py` scores each proposal by `{confidence, phase_fit, user_override_history}`
**And** proposals above `queue_threshold` enter the Action Queue with a ranked score
**And** proposals with confidence ∈ [low_threshold, queue_threshold] route to the User Validation Queue (for Epic 9)
**And** proposals below `low_threshold` are suppressed with audit event
**And** no user-facing Master Strategist UI exists in V1 (DP10)
**And** integration test covers: 50 mixed proposals → correct routing across queues

### Story 6.7: Master Strategist — phase-transition proposals (FR31)

As a **Master Strategist agent**,
I want to propose phase transitions with evidence citations,
So that FR31 is satisfied — Cartographer or Oracle may propose, Master Strategist aggregates, strategist confirms/rejects.

**Acceptance Criteria:**

**Given** accumulated evidence suggesting phase readiness
**When** Master Strategist's phase-transition heuristic fires
**Then** a `PhaseTransitionProposal` is created with citation envelopes linking to triggering evidence
**And** the proposal appears in the strategist's Action Queue with category `phase_transition`
**And** confirm/reject flows through the FR31 endpoint from Story 5.4
**And** integration test: evidence accumulates → Strategist proposes → surfaces to strategist

### Story 6.8: Agent graceful-degradation contract (FR46, NFR11, NFR73)

As a **platform engineer**,
I want every agent's LangGraph state machine to degrade gracefully with an explicit `agent_error` state exposing a retry affordance,
So that FR46 is satisfied and no surface displays silent-failure state.

**Acceptance Criteria:**

**Given** an agent encounters an upstream error (LLM timeout, retrieval failure, extraction exception)
**When** the failure occurs
**Then** the LangGraph state transitions to a terminal `agent_error` state with `{error_code, retry_possible: bool, user_message}`
**And** the error state propagates to consuming surfaces via the canonical memory event log
**And** an OpenTelemetry trace captures the failure root cause
**And** NFR73 per-agent MTBF ≥ 30 days is tracked via metric `agent_failure_rate`
**And** integration test: LLM timeout → agent_error state → surface can render explicit error (Epic 8 consumes)


---

## Epic 7: Design System Component Library

> **Status: complete (shipped 2026-04-26).** Implementation summary: [`epic-7-design-system-completion.md`](../implementation-artifacts/epic-7-design-system-completion.md). Retrospective: [`epic-7-retrospective-2026-04-26.md`](../implementation-artifacts/epic-7-retrospective-2026-04-26.md). **Next:** [Epic 8](#epic-8-morning-digest-phase-tracking--evening-synthesis-surfaces) (surfaces).

Ship all nine custom composite components + shared primitives as a cohesive design-system release BEFORE any surface epic consumes them — protecting the 07:00 → 10:03 identical-citation handshake.

### Story 7.1: `CitationChip` component (UX-DR4)

As a **frontend engineer**,
I want a `CitationChip` component with 5 states, variant sizes, HoverCard preview, and ContextMenu actions,
So that every surface (Digest, In-Meeting Alert, Override, Evidence Panel) renders an identical, a11y-compliant citation primitive (FR41, FR43).

**Acceptance Criteria:**

**Given** the shadcn primitives from Story 1.5
**When** `packages/shared-ui/src/CitationChip.tsx` is published
**Then** the component renders as 24 px inline pill, 12 px padding, monospace (IBM Plex Mono per UX-DR2)
**And** states supported: `default`, `hover`, `focus-visible`, `expanded`, `overridden`, `tombstoned` — each with glyph + text (UX-DR28 color-independence)
**And** variants: `inline`, `standalone`, `compact` (InMeetingAlertCard density)
**And** HoverCard shows a preview with `{citation_id, retrieval_phase, confidence, signed_timestamp}`
**And** ContextMenu exposes View evidence / Override / Copy link / Cite in override
**And** `aria-expanded` toggles when the chip opens an EvidencePanel
**And** Storybook story covers every state + variant with axe-core passing
**And** keyboard-only usage demo + SR-only usage demo included in Storybook
**And** Chromatic visual regression baseline captured

### Story 7.2: `EvidencePanel` component (UX-DR5)

As a **frontend engineer**,
I want an `EvidencePanel` component that expands inline with metadata, highlighted evidence spans, and live-region announcements,
So that citation deep-links resolve to an a11y-compliant evidence display (FR41, NFR40).

**Acceptance Criteria:**

**Given** design tokens + shadcn + the Epic 1 citation envelope contract
**When** `packages/shared-ui/src/EvidencePanel.tsx` is published
**Then** the panel renders as a bordered inline-expand region, 24 px padding, 680 px max reading measure
**And** uses `<article>` semantic landmark with `aria-labelledby`
**And** a metadata row shows source type, timestamp, phase, confidence, supersession state
**And** evidence spans from the citation envelope are `<mark>`-highlighted with tokenized evidence-blue
**And** loading state, degraded state (Cartographer error), tombstoned state each render explicitly (FR46)
**And** expansion announces via `aria-live="polite"`
**And** Storybook story covers all states + keyboard/SR flow demos
**And** lazy-loading supports FR36's In-Meeting Alert ≤ 8 s render + async evidence payload

### Story 7.3: `PhaseIndicator` component (UX-DR6)

As a **frontend engineer**,
I want a `PhaseIndicator` chrome chip with PhaseStepper popover and `aria-live` phase-change announcement,
So that strategists always know current phase and the phase-transition proposal surface (FR31) has a canonical control.

**Acceptance Criteria:**

**Given** the 7-phase machine from Story 5.4
**When** `packages/shared-ui/src/PhaseIndicator.tsx` is published
**Then** the chip renders 32 px tall in the top-left chrome
**And** `aria-live="polite"` announces phase changes ("Now in P5 Pilot")
**And** click opens a shadcn Popover with the full PhaseStepper showing current + prior + next
**And** states: `default`, `hover`, `pending-transition`, `locked` (read-only context)
**And** Storybook covers all states
**And** keyboard-only navigation through PhaseStepper verified

### Story 7.4: `FreshnessChip` component (UX-DR7)

As a **frontend engineer**,
I want a `FreshnessChip` "memory synced Ns ago" altimeter with color + text + glyph states mapped to NFR5 thresholds,
So that strategists can trust data freshness at a glance and FR48's memory-syncing glyph is a reusable primitive.

**Acceptance Criteria:**

**Given** NFR5 freshness SLOs (Digest ≤ 30 min, In-Meeting ≤ 60 s, Phase Tracking ≤ 5 min)
**When** `packages/shared-ui/src/FreshnessChip.tsx` is published
**Then** the chip renders 24 px in the top-right chrome with color + glyph + text
**And** states `fresh | stale | very-stale | unavailable` mapped to per-surface SLO thresholds passed as a prop
**And** color-blindness simulator verified in Storybook (UX-DR28)
**And** `prefers-reduced-motion` honored on state transitions (UX-DR30)
**And** consumed by every surface in Epic 8+ with surface-specific SLO props

### Story 7.5: `OverrideComposer` component (UX-DR8)

As a **frontend engineer**,
I want an `OverrideComposer` inline 3-field form (what-changed / why / evidence picker) with propagation preview,
So that FR49's override capability has an ergonomic, a11y-compliant composition surface.

**Acceptance Criteria:**

**Given** shadcn Form primitives
**When** `packages/shared-ui/src/OverrideComposer.tsx` is published
**Then** three fields render with labels above inputs (UX-DR40 — never placeholder-as-label)
**And** each field has `aria-invalid`, `aria-describedby`, and on-blur + on-submit validation
**And** the propagation preview sidecar shows affected surfaces (dependency-resolution via canonical memory graph traversal stub)
**And** Cmd+Enter submits the form (UX-DR40)
**And** form uses semantic `<form>` landmark; error summary announced via live region
**And** Storybook covers empty, filled, submitting, success, error states

### Story 7.6: `InMeetingAlertCard` component (UX-DR9)

As a **frontend engineer**,
I want an `InMeetingAlertCard` persistent draggable card with focus-trap and Cmd+\\ summon,
So that FR36's In-Meeting Alert surface has a non-modal, keyboard-accessible, per-tenant-positioned primitive.

**Acceptance Criteria:**

**Given** shadcn Card + focus-trap utilities
**When** `packages/shared-ui/src/InMeetingAlertCard.tsx` is published
**Then** default size 360 × 240 px, bottom-right dock, position persists per-tenant via localStorage keyed by `tenant:<uuid>:alert:position`
**And** `role="complementary"` with `aria-label="In-meeting alert"`
**And** Cmd+\\ summons and traps focus; Esc collapses without closing
**And** states `active | idle | degraded | collapsed | archived`
**And** draggable via keyboard (arrow keys with modifier) per UX-DR26
**And** Storybook covers all states + draggable-by-keyboard demo

### Story 7.7: `ValidationQueueCard` component (UX-DR10)

As a **frontend engineer**,
I want a `ValidationQueueCard` single-item primitive showing proposed fact + evidence + confidence + action row,
So that Epic 9's User Validation Queue and Solidification Review Queue surfaces share one primitive.

**Acceptance Criteria:**

**Given** the proposal structure from Master Strategist (Story 6.6)
**When** `packages/shared-ui/src/ValidationQueueCard.tsx` is published
**Then** renders one proposal with `{proposed_fact, supporting_evidence (as CitationChip[]), confidence, action_row: {confirm, modify, reject, defer}}`
**And** states `unresolved | in-review | resolved | escalated`
**And** every action button has `aria-label` and is keyboard-reachable
**And** modify + reject require a reason string (feeds Oracle re-ranking per FR33)
**And** Storybook covers all states + full keyboard flow

### Story 7.8: `TombstoneCard` component (UX-DR11)

As a **frontend engineer**,
I want a `TombstoneCard` primitive showing plain-language removal reason, timestamp, and optional appeal affordance,
So that FR5 tombstones have a consistent human-readable surface reachable from expired citation chips.

**Acceptance Criteria:**

**Given** the tombstone schema from Story 1.8
**When** `packages/shared-ui/src/TombstoneCard.tsx` is published
**Then** the card shows retention reason, destroyed_at timestamp (RFC 3161-verified), original node_id, authority_actor
**And** reachable from `CitationChip` in `tombstoned` state and from direct `/evidence/:node_id` route with a 410-like response
**And** optional appeal action routes to an audit-log-reviewer surface
**And** Storybook covers tombstone-with-appeal and tombstone-final states

### Story 7.9: `AgentOutageBanner` component (UX-DR12)

As a **frontend engineer**,
I want an `AgentOutageBanner` neutral-amber full-width banner with plain-language explanation and status-page link,
So that FR46 agent-error state is explicit across all surfaces and NFR11 customer communication has a UI primitive.

**Acceptance Criteria:**

**Given** the graceful-degradation contract from Story 6.8
**When** `packages/shared-ui/src/AgentOutageBanner.tsx` is published
**Then** the banner renders full-width with signal-700 border + signal-100 background, not red (no alarm-without-fire per DP principles)
**And** `role="status"` for informational; `role="alert"` for hard outage (escalated)
**And** shows affected agent name, plain-language explanation, retry-available or ETA, status-page link
**And** surfaces subscribe to the agent-outage event bus and render the banner when applicable
**And** Storybook covers informational, alert, and resolved states

### Story 7.10: `SessionBanner` primitive (break-glass + external-auditor variants, UX-DR42)

As a **frontend engineer**,
I want a `SessionBanner` primitive supporting break-glass and external-auditor variants with session-ID + countdown,
So that UX-DR42 ships as a shared primitive in Epic 7, and Epic 12's break-glass end-to-end can wire it into every surface without retrofit (per Party Mode Sally).

**Acceptance Criteria:**

**Given** the break-glass schema from Story 2.7
**When** `packages/shared-ui/src/SessionBanner.tsx` is published
**Then** the banner renders persistently above the nav chrome with `{session_id, variant: 'break-glass'|'external-auditor', expires_at}`
**And** live countdown to expiration ticks every second with `aria-live="polite"` announcements every 5 min
**And** variant styling: break-glass uses signal-amber urgency; external-auditor uses evidence-blue (observational)
**And** the banner is slot-integrated into the nav chrome from Epic 8 Story 8.5
**And** Storybook covers both variants + countdown flow

### Story 7.11: Empty-state, loading, and memory-syncing glyph primitives (UX-DR22, UX-DR23, UX-DR25)

As a **frontend engineer**,
I want `EmptyState`, `LoadingFromMemory`, and `MemorySyncingGlyph` primitives shipped together,
So that every surface consumes a canonical primitive rather than reinventing (per Party Mode Sally: "seven different flavors of 'no data yet'").

**Acceptance Criteria:**

**Given** design tokens + shadcn
**When** the primitives are published
**Then** `packages/shared-ui/src/EmptyState.tsx` renders plain-language explanation + suggested next action + docs link
**And** `packages/shared-ui/src/LoadingFromMemory.tsx` renders the "loading from memory" chip with progressive-render support (shimmer ONLY on static chrome per UX-DR23)
**And** `packages/shared-ui/src/MemorySyncingGlyph.tsx` renders the freshness-exceeded glyph per FR48
**And** Storybook covers each primitive with usage examples in Digest, Phase Tracking, Validation Queue contexts
**And** consumer contract enforced: Story 8.x ACs reference the primitives by name

### Story 7.12: Button / Form / Modal / Sheet / Popover consistency patterns (UX-DR39, UX-DR40, UX-DR41)

As a **frontend engineer**,
I want documented, Storybook-covered button hierarchy, form patterns, and modal/sheet/popover conventions,
So that every surface composes to the same muscle-memory (UX-DR39–41) and consistency tests can enforce.

**Acceptance Criteria:**

**Given** shadcn primitives
**When** patterns are published
**Then** `packages/shared-ui/src/patterns/ButtonHierarchy.stories.tsx` documents primary (one-per-surface, evidence-700), secondary (ghost ink-800), tertiary (hover-bg), destructive (destructive-700, never pre-selected); 36 px min, 44×44 hit area, icon-only buttons carry `aria-label`
**And** form-pattern story documents label-above-input, required-asterisk + explicit "required" text, `aria-invalid` + `aria-describedby`, Cmd+Enter submit
**And** modal/sheet/popover story documents `Dialog` (`role="alertdialog"`) for destructive only, `Sheet` for heavy settings, `Popover` for metadata
**And** a lint rule fails any raw `<button>` usage in `apps/web` (must use shadcn Button)
**And** all pattern stories pass axe-core

### Story 7.13: Tablet + mobile read-only responsive tokens (UX-DR37, UX-DR38)

As a **frontend engineer**,
I want breakpoint tokens and a mobile-read-only gate baked into component defaults,
So that every component ships responsive from day one (per Party Mode Sally: no deferred "tablet epic").

**Acceptance Criteria:**

**Given** design tokens from Story 1.4
**When** responsive tokens are published
**Then** breakpoints declared: Mobile 360–767 (default), Tablet `md:` 768–1023, Laptop `lg:` 1024–1279, Desktop `xl:` 1280–1535 (primary), Wide `2xl:` ≥ 1536 (content max 1440 centered)
**And** a `useMobileReadOnlyGate` hook returns true for write workflows (Override, SCIM config) on viewports < 768 px — consumed by Epic 10's Override and Epic 9's In-Meeting Alert to render view-only
**And** every component Storybook has Mobile + Tablet + Desktop render variants
**And** Chromatic visual regression captures all breakpoints

### Story 7.14: Storybook governance + axe-core per-story + Chromatic visual regression (UX-DR43)

As a **UX designer**,
I want every custom component to have a Storybook story, axe-core check, keyboard-only demo, screen-reader demo, and Chromatic visual regression,
So that component quality is CI-gated and design system changes cannot silently regress.

**Acceptance Criteria:**

**Given** all components from Stories 7.1–7.13
**When** CI runs
**Then** every `.stories.tsx` file has ≥ 1 axe-core check via `@storybook/addon-a11y`
**And** every custom composite component has a keyboard-only demo story and a screen-reader demo note
**And** Chromatic runs on every PR and blocks on any visual regression that is not explicitly approved
**And** `.github/workflows/storybook.yml` publishes the Storybook to a review URL on PRs
**And** `docs/design-system/governance.md` documents the acceptance bar

### Story 7.15: VPAT automation & evidence pipeline (UX-DR35)

As a **UX designer and compliance officer**,
I want automated axe reports from Storybook and Playwright aggregated into VPAT evidence,
So that Epic 13's VPAT authoring consumes ready evidence rather than hand-compiling from CI logs (per Party Mode Sally: clear split).

**Acceptance Criteria:**

**Given** axe-playwright + `@storybook/addon-a11y` + `pa11y` in CI
**When** a release candidate is built
**Then** `apps/tools/vpat-aggregator/` collects axe + pa11y + keyboard-flow + SR-flow evidence into `artifacts/vpat/evidence-<version>.json`
**And** `apps/tools/vpat-authoring/` provides a draft Markdown template consuming the evidence file
**And** a CI job publishes the aggregated evidence to S3 with 7-year retention (matches audit log retention)
**And** Epic 13 Story 13.4 authors the VPAT from this evidence


---

## Epic 8: Morning Digest, Phase Tracking & Evening Synthesis Surfaces

> **Status: V1 walking skeleton shipped (2026-04).** The detailed stories below remain the **target**; implementation coverage vs `main` is tracked in [`epic-8-implementation-status.md`](../implementation-artifacts/epic-8-implementation-status.md) · [retrospective](../implementation-artifacts/epic-8-retrospective-2026-04-26.md). **Next:** [Epic 9](#epic-9-in-meeting-alert-action-queue--validation-queues) (in-meeting + queues) after scheduling remaining Epic 8 hardening (Oracle, perf E2E, nav completeness).

Compose Epic 7's primitives into the three V1 "reflective/proactive" surfaces. The Morning Digest + Phase Tracking + Evening Synthesis stack lands by week 19.

### Story 8.1: Morning Digest surface (FR34, NFR1, NFR2)

As a **Deployment Strategist**,
I want a Morning Digest at start-of-day with phase-contextualized priorities, hard 3-item top, and "What I Ranked Out" footer,
So that FR34 is satisfied — I walk in prepared at 07:00 with emotional pacing that respects cognitive load (DP2).

**Acceptance Criteria:**

**Given** Oracle (Story 6.3–6.5) produces phase-gated ranked results
**When** the Morning Digest is rendered at 07:00 strategist-local
**Then** `apps/web/src/app/digest/page.tsx` renders three-column desktop / two-column laptop / stacked tablet/mobile layout (UX-DR13)
**And** the top section shows exactly 3 items (FR22 + FR34 hard cap) as `CitationChip`-composed cards
**And** "What I Ranked Out" footer lists suppressed candidates from Story 6.4
**And** every item's `CitationChip` opens an inline `EvidencePanel` (expand-inline default per FR41)
**And** delivery ≤ 15 min p95 from scheduled job start (NFR2)
**And** no shimmer on agent content (UX-DR23)
**And** `axe-playwright` passes; full keyboard + SR flow demo recorded
**And** integration test: seeded tenant → digest renders with real citations

### Story 8.2: Phase & Task Tracking surface (FR39, UX-DR15)

As a **Deployment Strategist**,
I want a Phase & Task Tracking surface with TanStack Table two-pane layout, filter chips, default sort, and `aria-sort`,
So that FR39 is satisfied — I can view current phase, phase-required tasks, outstanding blockers, and Action Queue items.

**Acceptance Criteria:**

**Given** the 7-phase state machine (Story 5.4) and Action Queue (Story 6.6)
**When** the strategist navigates to `/phase-tracking`
**Then** `apps/web/src/app/phase-tracking/page.tsx` renders two panes: TanStack Table v8 left (filterable) + detail pane right
**And** filter chips: phase, status, assignee, date range
**And** columns sortable with `aria-sort`; default sort by priority then date
**And** detail pane shows the full Action Queue item with evidence citations, phase context, resolution options
**And** keyboard-only interaction verified (UX-DR26)
**And** `FreshnessChip` with Phase Tracking SLO ≤ 5 min (NFR5)

### Story 8.3: Evening Synthesis surface (FR35, NFR3)

As a **Deployment Strategist**,
I want an Evening Synthesis surface at end-of-day parallel to Morning Digest,
So that FR35 is satisfied — I close the day with candidate-learning review and cross-account pattern surfacing.

**Acceptance Criteria:**

**Given** Oracle's end-of-day synthesis job
**When** Evening Synthesis is delivered by 19:00 strategist-local (NFR3)
**Then** `apps/web/src/app/evening/page.tsx` renders candidate learnings, cross-account pattern notes, and a Class B review entry point
**And** layout parallels Morning Digest for muscle-memory continuity (UX-DR14)
**And** links into `/solidification-review` (Epic 9 Story 9.7)
**And** `axe-playwright` passes

### Story 8.4: Expand-inline citation deep-link resolution (FR41, NFR4)

As a **Deployment Strategist**,
I want clicking any `CitationChip` to expand inline an `EvidencePanel` within ≤ 1.5 s,
So that FR41 continuity-of-reference and NFR4 latency are satisfied and "navigate to source" is an explicit opt-in, not the default.

**Acceptance Criteria:**

**Given** `CitationChip` from Story 7.1 and `EvidencePanel` from Story 7.2
**When** a user clicks a chip
**Then** the EvidencePanel expands inline in ≤ 1.5 s p95 (NFR4)
**And** `aria-expanded` flips and live region announces expansion
**And** the same `node_id` resolves to bit-identical canonical data across all surfaces (FR41, enforced by Story 1.12 contract test)
**And** a "navigate to source" action inside the panel deep-links to `/evidence/:node_id`
**And** E2E test: digest chip click → EvidencePanel expands with real data ≤ 1.5 s

### Story 8.5: Left-rail + top-rail nav chrome (UX-DR20)

As a **Deployment Strategist**,
I want a 240 px left rail and 56 px top rail with collapsible behavior and breadcrumbs on nested records,
So that navigation chrome is consistent across every surface and Epic 7's `PhaseIndicator` + `FreshnessChip` + `SessionBanner` have a canonical slot.

**Acceptance Criteria:**

**Given** Epic 7 primitives
**When** the chrome is implemented
**Then** left rail renders 240 px with primary (Digest, Phase Tracking, Validation Queue) + secondary (Override history, Personal audit) nav sections
**And** collapses to 56 px on `< 1280 px` viewports
**And** top rail: 56 px with `PhaseIndicator` left; `FreshnessChip` + Cmd+K trigger + user menu right
**And** `SessionBanner` slot renders above top rail when break-glass or external-auditor session active
**And** breadcrumbs render only on nested record pages (`/evidence/:id`, `/overrides/:id`)
**And** chrome components shared under `apps/web/src/components/chrome/`
**And** a11y: landmarks `<nav>`, `<main>`, `<complementary>`

### Story 8.6: Cmd+K command palette (UX-DR19)

As a **Deployment Strategist**,
I want a Cmd+K universal command palette with verb-based actions, surface navigation, and global search,
So that every user workflow is keyboard-reachable (NFR41).

**Acceptance Criteria:**

**Given** shadcn `Command` (cmdk)
**When** a user presses Cmd+K
**Then** a palette modal opens with focus-trap
**And** categories: Navigate (surfaces), Actions (override, resolve, claim), Search (canonical memory global search)
**And** search results show CitationChip previews
**And** Esc closes; keyboard-arrow navigates; Enter executes
**And** `axe-playwright` passes on the palette
**And** E2E test: Cmd+K → type "digest" → Enter → navigates to `/digest`

### Story 8.7: Agent-error and ingestion-in-progress states on surfaces (FR46, FR47)

As a **Deployment Strategist**,
I want every active surface to degrade gracefully when agents fail and to show an explicit ingestion-in-progress indicator,
So that FR46 and FR47 are satisfied — no silent failures, progress is visible.

**Acceptance Criteria:**

**Given** agent graceful degradation (Story 6.8) and ingestion runs (Story 3.8)
**When** an agent is in `agent_error` state or ingestion is in-flight for the tenant
**Then** Digest and Phase Tracking and Evening Synthesis surfaces render `AgentOutageBanner` (Story 7.9) when agents are degraded
**And** an ingestion-in-progress indicator renders in the top rail when active runs exist
**And** surfaces fall back to canonical-memory-only rendering (no agent outputs) while agents degrade
**And** integration test: trigger agent_error → banner appears on all 3 surfaces

---

## Epic 9: In-Meeting Alert, Action Queue & Validation Queues

Ship the full reactive surface stack — real meeting detection, Action Queue lifecycle, and the two queue surfaces.

### Story 9.1: In-Meeting Alert meeting detection + ≤ 8 s render (FR36, NFR1)

As a **Deployment Strategist**,
I want the In-Meeting Alert to detect when I'm in a meeting and render the alert card within 8 s of agent trigger,
So that FR36 and NFR1 are satisfied — the 10:03 moment lands on time.

**Acceptance Criteria:**

**Given** Teams meeting integration (Story 3.3) and Oracle (Story 6.3)
**When** a meeting starts and Oracle triggers an alert
**Then** meeting detection runs via Graph calendar + active-meeting signal (configurable polling interval ≤ 30 s)
**And** the `InMeetingAlertCard` (Story 7.6) renders in `active` state ≤ 8 s p95 from agent decision (NFR1)
**And** evidence payload lazy-loads after glyph render (≤ 3 s additional p95)
**And** E2E test: seed meeting + trigger alert → card appears ≤ 8 s p95 over 100 iterations

### Story 9.2: 3-item hard budget enforcement (FR22, FR36)

As a **Deployment Strategist**,
I want the In-Meeting Alert surface to show at most 3 items with suppressed ones visible in a "ranked out" expandable footer,
So that FR22 is enforced at the surface (not just agent) level.

**Acceptance Criteria:**

**Given** Oracle's 3-item budget (Story 6.4)
**When** the InMeetingAlertCard renders
**Then** the card shows exactly ≤ 3 primary items
**And** a collapsible "ranked out" footer lists suppressed candidates
**And** contract test asserts `primary_item_count ≤ 3` on every render

### Story 9.3: Correction-vs-dismissal non-confusable actions (FR37)

As a **Deployment Strategist**,
I want correction and dismissal to be architecturally separated as non-confusable actions on every alert item,
So that FR37 is satisfied — 0 silent-mislearning events on the validation protocol.

**Acceptance Criteria:**

**Given** the InMeetingAlertCard
**When** each item renders
**Then** two distinct affordances: `Correct` (evidence-blue, triggers OverrideComposer from Epic 10) and `Dismiss` (neutral ghost, no learning consequence)
**And** the affordances are visually distinct (color + icon + text per UX-DR28) and separated by ≥ 16 px
**And** a dismissed item emits `alert.dismissed` to the audit log with no learning update
**And** a correction emits `alert.corrected` and opens OverrideComposer
**And** validation protocol: 100 simulated mixed interactions → 0 silent-mislearning events asserted

### Story 9.4: Unattended alert items persist as Action Queue items (FR38)

As a **Deployment Strategist**,
I want alert items not attended during a meeting to persist as Action Queue items rather than silently expiring,
So that FR38 is satisfied.

**Acceptance Criteria:**

**Given** an active In-Meeting Alert with unattended items when the meeting ends
**When** the meeting-end signal fires
**Then** unattended items are converted to Action Queue entries with `source: in_meeting_alert` and original citation envelopes preserved
**And** the user sees an Evening-Synthesis-linked notification summarizing carryovers
**And** integration test: 5 unattended items → all appear in Action Queue post-meeting

### Story 9.5: Action Queue lifecycle — claim / in-progress / resolve (FR56, FR57, FR58)

As a **Deployment Strategist**,
I want to claim, mark in-progress, and resolve Action Queue items with resolution state + linked evidence,
So that FR56–58 are satisfied.

**Acceptance Criteria:**

**Given** Action Queue items from Oracle/Master Strategist/In-Meeting carryover
**When** a strategist acts
**Then** `/action-queue` surface renders a TanStack Table of items with columns `{priority, phase, description, status, claimed_by, updated_at}`
**And** `POST /action-queue/:id/claim` assigns to self and emits audit event
**And** `POST /action-queue/:id/progress` transitions to `in_progress`
**And** `POST /action-queue/:id/resolve` accepts `{state: resolved|deferred|rejected_with_reason, reason?, evidence_event_ids?}`
**And** reject_with_reason feeds Oracle re-ranking per FR53
**And** integration tests cover the full lifecycle

### Story 9.6: User Validation Queue surface (FR33, FR59)

As a **Deployment Strategist**,
I want a User Validation Queue surface with ValidationQueueCard composition and confirm/modify/reject actions,
So that FR33 + FR59 are satisfied — distinct from Action Queue and Digest.

**Acceptance Criteria:**

**Given** Master Strategist's low-confidence escalations (Story 6.6) and `ValidationQueueCard` (Story 7.7)
**When** the strategist navigates to `/validation-queue`
**Then** the surface renders queued items using the card composition
**And** actions: confirm (promotes to canonical), modify (opens OverrideComposer), reject with reason (feeds re-ranking)
**And** resolved items drop from the queue; decisions emit audit events
**And** integration test: 10 queued items → strategist confirms 5 / modifies 3 / rejects 2 → correct state transitions

### Story 9.7: Solidification Review Queue surface (FR28, FR59)

As a **Deployment Strategist**,
I want a Solidification Review Queue surface for Class B weekly reviews with promote/demote/defer actions,
So that FR28 (Class B review tier) and FR59 are satisfied.

**Acceptance Criteria:**

**Given** Class B classifications (Story 5.5) and `ValidationQueueCard` (Story 7.7)
**When** the strategist navigates to `/solidification-review`
**Then** the surface renders Class B candidates
**And** actions: promote (to `solidified`), demote (to `candidate`), defer (mark for next review)
**And** manual promote/demote per FR29 also available
**And** a weekly automated nudge surfaces via Evening Synthesis (Story 8.3)
**And** integration test: 20 Class B items → strategist promotes 10 / demotes 5 / defers 5

### Story 9.8: Alert-card draggable position persistence per-tenant (UX-DR9, UX-DR16)

As a **Deployment Strategist**,
I want the InMeetingAlertCard's dragged position to persist per-tenant,
So that my ergonomic choices survive across sessions and my SR-colleague's choices do not collide with mine.

**Acceptance Criteria:**

**Given** `InMeetingAlertCard` from Story 7.6
**When** I drag the card and close the browser
**Then** position persists under `tenant:<uuid>:user:<uuid>:alert:position` in localStorage (and server-side for cross-device)
**And** keyboard-drag equivalent (arrow keys with modifier) also persists
**And** reset-to-default action available from the card's context menu

---

## Epic 10: Override, Trust Repair & Personal Audit

Ship the full override capability with private-scope annotations, override history, and personal audit surfaces.

### Story 10.1: Override event schema + first-class canonical log entry (FR49, FR50)

As a **platform engineer**,
I want override events recorded as first-class canonical memory log entries,
So that FR49 + FR50 are satisfied and trust repair is auditable.

**Acceptance Criteria:**

**Given** the canonical memory substrate (Story 1.8)
**When** a strategist submits an override
**Then** an `override_event` row is inserted into the canonical event log with `{override_id, user_id, learning_id, override_evidence_event_ids, reason_string, timestamp (RFC 3161 signed)}`
**And** the event is immutable (append-only trigger enforces)
**And** the associated `solidified_learnings.state` transitions to `overridden` with a supersession link pointing to the new evidence
**And** contract test asserts schema conformance
**And** integration test: submit override → event persisted + learning state transitions

### Story 10.2: OverrideComposer submission endpoint (FR49)

As a **Deployment Strategist**,
I want to submit an override from the `OverrideComposer` with new evidence and a reason string,
So that FR49 is satisfied.

**Acceptance Criteria:**

**Given** `OverrideComposer` (Story 7.5) and the override event schema (Story 10.1)
**When** the strategist submits
**Then** `POST /overrides` accepts `{learning_id, what_changed, why, evidence_event_ids: [...]}`
**And** validation: at least one evidence event ID required; reason string ≥ 20 chars
**And** on success, the propagation preview sidecar shows affected surfaces
**And** a persistent confirmation chip appears (UX-DR24 — not auto-dismissed)
**And** integration test: valid submission → 201 + override_event row + preview accurate

### Story 10.3: Override-applied sub-citation in future reasoning trails (FR51)

As a **Deployment Strategist**,
I want future agent reasoning trails that cite an overridden learning to surface an override-applied sub-citation linking to the override event,
So that FR51 is fully satisfied (not a "hook" — per Party Mode John).

**Acceptance Criteria:**

**Given** an overridden learning and any subsequent Oracle output citing it
**When** the citation envelope is constructed
**Then** the envelope includes `supersession: {type: 'overridden', override_event_id, overriding_evidence_event_ids}`
**And** the `CitationChip` in `overridden` state (Story 7.1) shows a visible override-applied badge
**And** clicking the badge navigates to the override event's EvidencePanel view
**And** contract test asserts supersession fields present whenever an overridden learning is cited
**And** integration test: override → subsequent Oracle run cites learning → sub-citation appears in rendered surface

### Story 10.4: Trust-earn-back confidence cue (FR55)

As a **Deployment Strategist**,
I want subsequent surfaces citing a corrected learning to show a trust-earn-back confidence cue,
So that FR55 is fully satisfied and DP11 (trust, repaired) is visible in the UI.

**Acceptance Criteria:**

**Given** an overridden learning and its supersession
**When** Oracle surfaces the corrected learning on later surfaces
**Then** the CitationChip or surface item shows a subtle "recovered" affordance (neutral evidence-blue micro-label)
**And** the cue appears for 30 days post-correction (configurable) then decays to baseline
**And** color + glyph + text per UX-DR28
**And** integration test: override → subsequent surface shows trust-earn-back cue → after TTL it decays

### Story 10.5: Private-scope annotations (FR52, NFR37)

As a **Deployment Strategist**,
I want to attach private-scope annotations to my own overrides, invisible to Successor Strategists inheriting the account,
So that FR52 is satisfied with the NFR37 authorization + encryption guarantees.

**Acceptance Criteria:**

**Given** the break-glass + role matrix from Epic 2
**When** a strategist attaches a private annotation
**Then** the annotation is stored in `private_annotations` table in a logically-separate encrypted store (distinct per-annotation DEK wrapped by tenant DEK, per NFR37)
**And** authorization-layer check precedes every query: only the original author (and Platform Admin under break-glass) can read
**And** Successor Strategists (V1.5) cannot read; SCIM role transition enforces immediately
**And** FOIA export (Epic 12) includes them with an explicit private-scope disclosure tag
**And** integration test: author reads own annotation (success) → different strategist reads (denied) → Platform Admin under break-glass reads (success, audited)

### Story 10.6: Override history surface `/overrides` (FR54, UX-DR17)

As a **Deployment Strategist**,
I want an override history surface showing my own overrides and non-private overrides by others on accessible accounts,
So that FR54 is satisfied (distinct from personal audit per UX-DR17).

**Acceptance Criteria:**

**Given** override events (Story 10.1)
**When** the strategist navigates to `/overrides`
**Then** a TanStack Table renders override events with `{timestamp, learning_belief, reason, overriding_evidence_count, author}`
**And** filters: mine-only, account, date range
**And** clicking an entry opens the override event's EvidencePanel (Story 7.2)
**And** private-scope entries from other authors are excluded per Story 10.5 authz
**And** `axe-playwright` passes

### Story 10.7: Personal audit surface (FR66, UX-DR17)

As a **Deployment Strategist**,
I want a personal audit surface showing my own overrides, actions, corrections, and integration kill-switch toggles on accessible accounts,
So that FR66 is satisfied — distinct from admin audit-log access.

**Acceptance Criteria:**

**Given** all user-originated audit events
**When** the strategist navigates to `/audit/personal`
**Then** the surface aggregates overrides, action-queue resolutions, alert corrections, and kill-switch toggles authored by the current user
**And** event categories are filterable
**And** the surface is NOT a full audit log — it is scoped to the current user's own actions
**And** integration test: user performs 5 distinct actions → all appear on personal audit surface


---

## Epic 11: Edge Capture Agent (Tauri macOS V1)

Build on Epic 1's signed Hello-World spike to ship the production edge agent.

### Story 11.1: Tauri 2.x capability-based permissions scaffold (AR17)

As a **platform engineer**,
I want the Tauri app's capability-based permissions configured in `tauri.conf.json`,
So that FR13 is satisfied with least-privilege defaults and every permission is auditable.

**Acceptance Criteria:**

**Given** Epic 1's signed Hello-World (Story 1.15)
**When** capabilities are configured
**Then** `apps/edge-agent/src-tauri/tauri.conf.json` declares capabilities: `fs:local-only`, `dialog:file-select`, `audio:capture` (explicit consent), `keychain:read-write`, `http:api-only`
**And** each capability is scoped to the minimum path / endpoint necessary
**And** a capability audit CI step parses the config and fails on any `fs:all` or over-broad grant
**And** `docs/edge-agent/capabilities.md` documents each capability

### Story 11.2: Per-device hardware-backed signing key (AR17, NFR20)

As a **compliance engineer**,
I want each edge-agent instance to generate a per-device signing key stored in macOS Keychain,
So that transcripts are tamper-evident and verifiable offline without DeployAI services (FR13, NFR20).

**Acceptance Criteria:**

**Given** Keychain access from Story 1.15
**When** the edge agent first launches on a device
**Then** a fresh Ed25519 keypair is generated and the private key persists in Keychain with access-control `WhenPasscodeSetThisDeviceOnly`
**And** the public key is registered with the DeployAI control plane via `POST /edge-agents/register` tied to tenant + device
**And** key revocation is supported via the kill-switch (Story 11.7)
**And** integration test: fresh install → key generated → registered → public key retrievable
**And** Windows DPAPI variant stubbed for V1.5 (Epic 14)

### Story 11.3: Tamper-evident local transcript (FR13, NFR20)

As a **Deployment Strategist**,
I want local meeting transcripts signed with the per-device key on write,
So that FR13 tamper-evidence is verifiable offline.

**Acceptance Criteria:**

**Given** a local audio capture and the per-device signing key
**When** a transcript is produced
**Then** the transcript file is written with a detached signature via the per-device private key
**And** a Merkle chain links sequential transcript segments, rooted in an RFC 3161 TSA timestamp when online
**And** the FOIA CLI (Epic 12 Story 12.1) can verify the signature + chain offline using the registered public key
**And** tampering detection: flipping any byte in the transcript invalidates the signature → verifier reports failure
**And** integration test on fresh VM: record → sign → tamper → verify fails; untampered → verify succeeds

### Story 11.4: Audio capture + two-party consent UX (FR12, NFR39)

As a **Deployment Strategist**,
I want the edge agent to prompt for two-party consent before recording and capture audio on-device,
So that FR12 + NFR39 are satisfied.

**Acceptance Criteria:**

**Given** the Tauri audio capability
**When** a recording session starts
**Then** a two-party consent dialog renders with jurisdiction awareness (configurable defaults per tenant)
**And** consent is cryptographically attested and stored with the transcript metadata
**And** audio captures locally via the Tauri Rust sidecar using CoreAudio (macOS V1)
**And** no audio or transcript leaves the device until an explicit upload action fires
**And** integration test on VM: consent flow → record → transcript written locally

### Story 11.5: Sparkle auto-updater with signed appcast (AR17)

As a **platform engineer**,
I want Sparkle auto-updates with a signed appcast feed,
So that edge-agent updates are securely delivered without manual reinstallation.

**Acceptance Criteria:**

**Given** the Sparkle spike from Story 1.15
**When** a new release is built
**Then** the updated binary is signed + notarized and pushed to an S3-hosted appcast feed
**And** the appcast.xml is signed with an ed25519 key held in the CI secret store
**And** the edge-agent verifies the appcast signature before applying the update
**And** integration test: bump version → CI pushes appcast → running agent auto-updates

### Story 11.6: Offline verification via FOIA CLI integration (FR61)

As a **Customer Records Officer or any third-party verifier**,
I want to verify edge-agent transcripts offline using only the FOIA CLI and public trust-authority keys,
So that FR61 is satisfied — no DeployAI dependency for verification.

**Acceptance Criteria:**

**Given** the FOIA CLI from Epic 12 Story 12.1 and the registered per-device public keys
**When** a verifier runs `foia verify <bundle>` on a transcript
**Then** the verifier validates the per-device signature, the RFC 3161 chain-of-custody, and reports pass/fail
**And** no network calls to DeployAI services required (air-gapped verification)
**And** integration test: on a clean machine with no network, verify a valid bundle → success; tampered → fail

### Story 11.7: Edge Agent kill-switch (FR14, NFR24)

As a **Platform Admin**,
I want to remotely disable any deployed Edge Agent binary, revoking trust and halting capture in ≤ 30 s,
So that FR14 is fully satisfied and NFR24 met.

**Acceptance Criteria:**

**Given** the per-device key registration and kill-switch infra from Epic 2
**When** a Platform Admin triggers `POST /edge-agents/:id/kill`
**Then** the control plane publishes a revocation event that the edge-agent polls (or subscribes to via SSE/WebSocket)
**And** the edge-agent halts capture and refuses to sign new transcripts
**And** subsequent signature verifications by the FOIA CLI check a revocation list and reject signatures post-revocation
**And** end-to-end wall-clock ≤ 30 s (NFR24)
**And** integration test drills the flow on staging

---

## Epic 12: FOIA Export, Compliance, Operability & External Auditor

The compliance- and operability-delivery epic. FOIA CLI, break-glass end-to-end, External Auditor JIT shell, immutable audit log, quarterly packet, SLOs + paging + chaos + DR + cost envelope + self-hosted parity validation.

### Story 12.1: Go FOIA CLI — signed single-binary with offline verifier (FR60, FR61, AR18)

As a **Customer Records Officer**,
I want a single static Go binary, Sigstore-signed, that produces and verifies FOIA export bundles offline,
So that FR60 + FR61 are satisfied without engineering support.

**Acceptance Criteria:**

**Given** the canonical memory substrate and RFC 3161 signing
**When** the CLI is built
**Then** `apps/foia-cli/` builds a static binary for macOS, Linux, Windows via `CGO_ENABLED=0`
**And** the binary is Sigstore-cosign-signed on release
**And** `foia export --account <id> --from <date> --to <date>` produces a bundle of canonical events + tombstones + signatures
**And** `foia verify <bundle>` performs offline verification using bundled public trust-authority keys + FreeTSA cert
**And** bundle format documented in `docs/foia/bundle-format.md`
**And** cross-platform test matrix in CI verifies binaries run on each OS

### Story 12.2: FOIA bundle construction within ≤ 4 hr / ≤ 10 GB (NFR7, FR60)

As a **Customer Records Officer**,
I want FOIA export bundles to complete within 4 hr for ≤ 10 GB,
So that NFR7 is satisfied.

**Acceptance Criteria:**

**Given** the FOIA CLI from Story 12.1
**When** an export is invoked
**Then** the export streams from the canonical event log via cursor pagination and writes to S3 or local filesystem incrementally
**And** parallel workers compute per-event signatures concurrently
**And** a progress meter renders on stderr
**And** load test: 10 GB account → bundle built ≤ 4 hr on reference infra
**And** tombstones included per NFR38 with destruction attestation

### Story 12.3: External Auditor JIT read-only `/auditor` shell (FR65, UX-DR21)

As an **External Auditor**,
I want a JIT time-bounded read-only shell exposing audit log + controls evidence with watermarked exports,
So that FR65 is satisfied — no canonical memory access, only audit evidence.

**Acceptance Criteria:**

**Given** the break-glass + auditor session schema (Story 2.7)
**When** a Platform Admin provisions an auditor session
**Then** `/auditor` renders a read-only view of audit log + controls evidence within the session's time-bound (≤ 48 hr)
**And** all exports are watermarked with session ID + timestamp
**And** canonical memory is not readable from the auditor role (RLS + authz-check enforced)
**And** `SessionBanner` (Story 7.10) persists with countdown
**And** session auto-expires; all evidence accessed logs every action with session ID (UX-DR42)

### Story 12.4: Break-glass end-to-end operability (FR64, NFR21, NFR22)

As a **Platform Admin**,
I want the break-glass flow end-to-end — dual-approval request → customer Security-contact notification → 15-min objection window → SessionBanner → ≤ 4 hr auto-expiry → post-hoc transcript,
So that FR64 + NFR21 + NFR22 are fully satisfied.

**Acceptance Criteria:**

**Given** break-glass plumbing (Story 2.7) and `SessionBanner` (Story 7.10)
**When** a break-glass session is initiated
**Then** customer Security-contact is notified via email + webhook ≤ 2 min from request
**And** non-emergency sessions enforce a 15-min objection window before session opens
**And** the SessionBanner renders on every surface the Platform Admin visits during the session
**And** every action within the session annotates the audit log with `break_glass_session_id`
**And** session auto-expires at T+≤ 4 hr
**And** a post-hoc transcript is emitted to the customer Security-contact within 24 hr
**And** E2E test: request → approve → notify → banner → action → expire → transcript delivered

### Story 12.5: Immutable audit log with S3 Object Lock (NFR34, AR11)

As a **compliance officer**,
I want all audit log entries emitted to a separate S3 bucket with Object Lock in compliance mode and 7-year retention,
So that NFR34 is satisfied — immutable, independently attestable.

**Acceptance Criteria:**

**Given** all audit event emitters (integration kill-switch, override, break-glass, FOIA export, etc.)
**When** audit events are emitted
**Then** events are written to the audit S3 bucket with Object Lock compliance mode
**And** the bucket is versioned, SSE-KMS encrypted with a dedicated audit CMK
**And** retention is 7 years on every object
**And** a monthly attestation job verifies no object has been mutated (via ETag drift detection)
**And** terraform in `infra/terraform/audit-log/` provisions the bucket + Object Lock

### Story 12.6: Quarterly compliance packet generator (FR63, NFR61)

As a **Customer Success / Compliance Officer**,
I want a quarterly compliance packet generator producing the Replay-Parity Gate Report + SLA adherence + incident summary,
So that FR63 + NFR61 are satisfied.

**Acceptance Criteria:**

**Given** the Replay-Parity Gate Report (Story 4.8), SLO telemetry, and incident audit log
**When** the quarterly job runs
**Then** `apps/tools/compliance-packet/` aggregates gate report + availability metrics + Sev-1/Sev-2 incident count + MTBF/MTTR + override statistics
**And** the packet is rendered as a customer-ready PDF and signed via cosign
**And** an integration test covers one full quarter's data aggregation
**And** Sev-2 citation-accuracy regression triggers immediate customer notification per NFR61 (not just quarterly)

### Story 12.7: Procurement package artifact set (FR79, NFR69)

As a **Customer Procurement Officer (Sourcewell path)**,
I want an on-demand procurement package with line-item pricing, standards-conformance, vendor-security, and data-sharing contract shape,
So that FR79 + NFR69 are satisfied.

**Acceptance Criteria:**

**Given** pricing + SBOM + SLSA + SOC 2 / StateRAMP posture docs
**When** a procurement package is generated
**Then** `apps/tools/procurement-package/` produces: line-item pricing breakdown, standards-conformance summary (SOC 2, StateRAMP, WCAG 2.1 AA, Section 508, NIST AI RMF mapping), vendor-security doc (SBOM, SLSA L2 provenance, CVE posture), data-sharing contract shape draft
**And** the artifact set is signed + versioned
**And** a sample generation against the NYC DOT fixture produces a complete package for review

### Story 12.8: NIST AI RMF mapping doc (NFR32)

As a **compliance officer**,
I want a living NIST AI RMF mapping document tying citation envelope → MEASURE, replay-parity → MANAGE, override-in-reasoning-trail → GOVERN,
So that NFR32 is satisfied.

**Acceptance Criteria:**

**Given** the PRD commitments
**When** the mapping doc is authored
**Then** `docs/compliance/nist-ai-rmf-mapping.md` explicitly maps each NIST AI RMF function + category to DeployAI controls
**And** the doc is versioned per release and reviewed quarterly
**And** Epic 12 Story 12.6's quarterly packet references the doc

### Story 12.9: Self-hosted reference build fresh-laptop acceptance (NFR67, NFR68)

As an **Enterprise Customer (List tier, V1.5)**,
I want a documented self-hosted reference build that a fresh engineer can stand up in ≤ 1 day,
So that NFR67 + NFR68 are satisfied (per Party Mode Winston: "not implicit in Epic 1").

**Acceptance Criteria:**

**Given** the docker-compose dev env from Story 1.7
**When** the self-hosted reference build is packaged
**Then** `infra/self-hosted/` hosts a compose file + bring-up runbook + seeded config + TLS story + SSO wiring stub
**And** a fresh-laptop drill runs monthly: a new engineer with no prior DeployAI context stands up a working instance in ≤ 1 day using only the runbook
**And** the drill's wall-clock is recorded; any drill exceeding 1 day triggers a runbook improvement task
**And** helm deferred to V1.5 (Epic 14) per NFR68
**And** BYOK/HSM interface stubbed for V1.5 per FR78/NFR18

### Story 12.10: SLOs + Grafana dashboards + Grafana OnCall paging (NFR10, NFR57, NFR58, NFR60)

As an **SRE**,
I want SLO-based paging tied to Grafana Mimir / Tempo / Loki dashboards and Grafana OnCall,
So that NFR10/57/58/60 are satisfied.

**Acceptance Criteria:**

**Given** OpenTelemetry in every service (AR22)
**When** the observability stack lands
**Then** SLOs defined per service: availability (NFR10), p95/p99 agent latency (NFR1/4/48), surface freshness (NFR5)
**And** Grafana dashboards render per-service health + SLO budget burn
**And** Grafana OnCall pages on SLO breach; Sev-1 response-start ≤ 15 min (NFR60)
**And** traces retained ≥ 30 days (NFR58)
**And** tenant-scoped Loki log labels (AR22) support tenant-level debugging without cross-tenant leakage

### Story 12.11: Unleash feature flags + canary deploy (AR28, NFR75)

As a **platform engineer**,
I want Unleash OSS feature flags with per-tenant flag evaluation and canary ≤ 10% traffic for agent-layer or citation-assembler changes,
So that NFR75 rollback ≤ 5 min is achievable via flag toggle.

**Acceptance Criteria:**

**Given** the ECS Fargate + ALB deploy topology (AR19)
**When** Unleash is deployed
**Then** a self-hosted Unleash instance runs in `infra/`
**And** `packages/feature-flags/` exposes a client evaluating flags per tenant_id
**And** agent-layer and citation-assembler deploys route 10% traffic canary via ALB target-group weights before full rollout
**And** flag-toggle rollback of any deployed feature takes ≤ 5 min wall-clock
**And** integration test: toggle a flag → verify feature disabled across all traffic within 5 min

### Story 12.12: Monthly chaos drills + backup/DR verification (NFR69, NFR78)

As an **SRE**,
I want monthly chaos drills (pod kill, DB failover, LLM timeout, integration throttle storm) and a DR exercise verifying RPO ≤ 5 min and RTO ≤ 4 hr,
So that NFR69 + NFR78 are satisfied.

**Acceptance Criteria:**

**Given** the observability stack (Story 12.10)
**When** drills run
**Then** `infra/chaos/` hosts monthly drill scripts: ECS task kill, RDS failover, LLM provider forced-timeout, SQS throttle burst
**And** each drill has a runbook at `docs/runbooks/chaos-<drill>.md`
**And** a quarterly full DR exercise restores from backup on a separate AWS account and measures RPO/RTO
**And** RPO ≤ 5 min and RTO ≤ 4 hr (single-AZ) asserted per NFR8/NFR9

### Story 12.13: Cost-per-account telemetry (NFR71)

As a **product manager**,
I want telemetry tracking infra + LLM cost per account with a ≤ $400/month/account envelope (rolling 30-day mean),
So that NFR71 is satisfied and cost drift triggers alerts.

**Acceptance Criteria:**

**Given** LLM usage metrics (Story 5.1) and AWS cost allocation tags
**When** cost telemetry runs
**Then** per-account LLM token spend emits via OpenTelemetry tagged by tenant_id
**And** AWS cost allocation tags group ECS/RDS/S3/SQS costs by tenant
**And** a Grafana dashboard shows per-account rolling 30-day cost mean
**And** an alert fires when any account exceeds $400/month rolling mean
**And** quarterly compliance packet (Story 12.6) includes cost adherence evidence

### Story 12.14: Platform Admin privileged-override audit log (NFR59)

As a **compliance officer**,
I want every Platform Admin privileged action logged with structured audit entries + RFC 3161 signed time,
So that NFR59 is fully satisfied across all admin-level operations.

**Acceptance Criteria:**

**Given** all Platform Admin operations (provisioning, break-glass, kill-switch, schema-proposal promotion)
**When** any privileged action fires
**Then** a structured audit entry `{actor_user_id, action, target_tenant_id, target_resource_id, rfc3161_timestamp, action_hash}` is written to the immutable audit bucket (Story 12.5)
**And** all authz decisions also emit audit entries (NFR59)
**And** a CI lint rule flags any Platform Admin endpoint missing an audit decorator

---

## Epic 13: Usability Validation & VPAT Authoring

Calendar-committed validation + compliance-authoring epic, recruitment from week 16.

### Story 13.1: Usability study recruiting (NFR44)

As a **UX designer**,
I want to recruit n ≥ 5 users including ≥ 1 screen-reader-primary user starting week 16,
So that NFR44 is achievable and the study does not collide with ship pressure (per Party Mode Sally: "recruiting begins w16 not w22").

**Acceptance Criteria:**

**Given** the need for pre-V1 usability validation
**When** recruiting begins
**Then** recruiting outreach begins by w16, 6 weeks before V1 ship target
**And** ≥ 5 participants confirmed with ≥ 1 screen-reader-primary
**And** participants represent at least 2 of the 3 stakeholder topology variants (Anchor profile, Design-Partner profile)
**And** `docs/research/usability-study-plan.md` documents recruiting criteria, screener, and consent
**And** consent forms and NDAs signed before sessions

### Story 13.2: Top-5 V1 journeys scripted with axe-playwright (NFR40)

As a **UX designer**,
I want the top-5 V1 journeys scripted for both sighted and screen-reader walkthroughs with axe-playwright benchmarking,
So that NFR40 screen-reader task-completion parity (≤ 1.5× sighted time) is measurable.

**Acceptance Criteria:**

**Given** Epics 8/9/10 surfaces
**When** journey scripts are authored
**Then** five journeys scripted: Morning Digest review, In-Meeting Alert review, Phase Tracking, Override-with-Evidence, FOIA as Records Officer
**And** each script has sighted + keyboard-only + screen-reader (VoiceOver, NVDA, JAWS) variants
**And** `tests/usability/journeys/*.spec.ts` runs axe-playwright with per-journey assertions
**And** sighted baseline completion time recorded; SR completion time ≤ 1.5× sighted asserted

### Story 13.3: Usability study execution + triaged findings

As a **UX designer**,
I want to execute the usability study with all recruited participants and produce triaged findings with ship/no-ship gates,
So that NFR44 is satisfied and V1 ships with validated experience evidence.

**Acceptance Criteria:**

**Given** recruited participants and scripted journeys
**When** the study runs
**Then** each participant completes all 5 journeys (or marks incompletable)
**And** findings are categorized: ship-blocker, ship-gate, post-ship, nice-to-have
**And** ship-blockers must resolve before V1 ship
**And** findings report at `docs/research/usability-findings-v1.md` summarizes per-journey completion times + SR parity + qualitative themes

### Story 13.4: VPAT authoring + publication (NFR28, UX-DR35)

As a **compliance officer**,
I want a published VPAT for V1 using the Story 7.15 evidence pipeline,
So that NFR28 is satisfied at launch.

**Acceptance Criteria:**

**Given** the VPAT evidence aggregator (Story 7.15)
**When** V1 release is cut
**Then** the VPAT Markdown template is populated from `artifacts/vpat/evidence-<version>.json`
**And** reviewed + signed by a compliance officer
**And** published at `docs/compliance/vpat-v1.md` and linked from the customer-facing site
**And** covers WCAG 2.1 AA + Section 508 with pass/partial/fail per criterion

### Story 13.5: Post-ship n ≥ 8 usability study (NFR44)

As a **UX designer**,
I want to schedule and execute a post-ship study with n ≥ 8 participants within 6 months of V1 ship,
So that NFR44 second-pass is satisfied.

**Acceptance Criteria:**

**Given** V1 shipped
**When** the post-ship study runs
**Then** ≥ 8 new participants recruited, including ≥ 1 SR user
**And** findings added to `docs/research/usability-findings-v1-post.md`
**And** any regressions flagged for V1.5 backlog (Epic 14)

---

## Epic 14: V1.5 Scaffolding & Successor Inheritance

Explicitly post-Anchor-ship.

### Story 14.1: Successor Strategist inheritance activation (FR74, FR75)

As a **Platform Admin**,
I want to assign a Successor Strategist to an inherited account triggering the Inherited Account Onboarding flow,
So that FR74 + FR75 are activated (data model ships V1, active role V1.5).

**Acceptance Criteria:**

**Given** Story 10.5's private-scope annotation enforcement and Story 2.1's role matrix
**When** a Platform Admin assigns a Successor
**Then** the Successor inherits canonical memory, Action Queue, and public-scope annotations
**And** private-scope annotations from the predecessor remain invisible (authz enforced)
**And** an Inherited Account Onboarding flow walks the Successor through phase context, active blockers, and top-priority Action Queue items
**And** integration test: assign Successor → predecessor private annotations denied → public annotations visible

### Story 14.2: Timeline surface (FR40)

As a **Deployment Strategist**,
I want a Timeline surface showing account history at week-level zoom with landmark-bloom annotations and presenter-mode,
So that FR40 is satisfied.

**Acceptance Criteria:**

**Given** canonical memory event log
**When** the Timeline renders
**Then** events aggregate to week-level zoom with landmark bloom (key phase-transition + override events)
**And** presenter-mode enlarges for projection
**And** `FreshnessChip` with Timeline SLO ≤ 5 min (NFR5)
**And** responsive to tablet + desktop

### Story 14.3: Customer Admin self-service user management (FR77)

As a **Customer Admin**,
I want to manage my own organization's DeployAI users via a self-service surface,
So that FR77 is satisfied.

**Acceptance Criteria:**

**Given** Role matrix and SCIM (Epic 2)
**When** a Customer Admin navigates to `/customer-admin/users`
**Then** they can view their organization's users, assign/remove `deployment_strategist` roles, disable accounts
**And** changes flow via SCIM and emit audit events
**And** scope is strictly tenant-internal; no cross-tenant visibility

### Story 14.4: [List tier] SIEM egress — syslog/CEF/OCSF + pull-API (FR67, NFR13)

As a **Customer IT / Security team**,
I want SIEM egress via syslog/CEF/OCSF push + pull-API fallback with 72-hour replay buffer,
So that FR67 + NFR13 are satisfied for List-tier customers.

**Acceptance Criteria:**

**Given** the audit log emission pipeline
**When** SIEM egress is configured per tenant
**Then** push delivery via configured protocol (syslog over TLS, CEF, or OCSF)
**And** pull-API endpoint `GET /siem/events?from=<cursor>` supports 72-hr replay
**And** delivery reliability ≥ 99.9% measured
**And** integration test against a Splunk HEC staging instance

### Story 14.5: Edge Agent Windows port (FR13 V1.5)

As an **Enterprise Customer on Windows**,
I want the edge agent running on Windows with DPAPI-backed signing,
So that FR13's second-OS commitment is fulfilled.

**Acceptance Criteria:**

**Given** the macOS edge agent (Epic 11)
**When** the Windows port lands
**Then** Tauri Windows build produces a signed binary with Authenticode signing
**And** per-device key uses Windows DPAPI (hardware-backed where available via TPM)
**And** the offline FOIA verifier works across Windows bundles
**And** cross-platform E2E test matrix passes

### Story 14.6: Helm chart + BYOK/HSM interface (FR78, NFR18, NFR68)

As an **Enterprise Customer (List tier)**,
I want a Helm chart for Kubernetes deployment and a BYOK/HSM interface,
So that FR78 + NFR18 + NFR68 are satisfied at V1.5.

**Acceptance Criteria:**

**Given** the self-hosted docker-compose reference (Story 12.9)
**When** Helm + BYOK land
**Then** `infra/helm/deployai/` provides a production-grade chart with values.yaml for tenant-scoped config
**And** BYOK/HSM interface implemented in `packages/kms-byok/` supporting AWS KMS + customer-hosted HSM variants
**And** a fresh-kubernetes-cluster install via Helm completes in ≤ 1 eng-day (NFR68 uplift)


---

## Final Validation Report

### FR Coverage: 79/79 ✅

Every FR from the PRD is covered by at least one story. The FR Coverage Map (above) lists each FR's owning epic and story. Spot checks:

- **FR1–8 (Canonical Memory):** Epic 1 Stories 1.8, 1.11, 1.13, 1.17
- **FR13 (Edge Agent):** Epic 1 Story 1.15 (spike) + Epic 11 Stories 11.1–11.4 (full)
- **FR14 (Kill-Switch):** Epic 2 Story 2.6 (plumbing) + Epic 11 Story 11.7 (edge full)
- **FR27 (Citation Envelope):** Epic 1 Story 1.11 (contract); consumed by Epic 4 Story 4.2 and every agent/surface story
- **FR36 (In-Meeting Alert ≤ 8 s):** Epic 9 Story 9.1 + NFR1 performance gate
- **FR41–43 (Continuity-of-Reference):** Epic 1 Stories 1.11/1.12 + Epic 7 primitives + Epic 8 Story 8.4
- **FR51 + FR55 (Override-applied sub-citation + Trust-earn-back):** Full V1 coverage in Epic 10 Stories 10.3 + 10.4 (no "hooks" per Party Mode John)
- **FR62 + FR63 (Replay-parity + Quarterly Gate Report):** Epic 4 Stories 4.5–4.8 + Epic 12 Story 12.6
- **FR64 (Break-glass):** Epic 2 Story 2.7 (plumbing) + Epic 12 Story 12.4 (end-to-end) + Epic 7 Story 7.10 (`SessionBanner`)

### Epic Independence ✅

Each epic is demo-able using only prior-epic outputs:

- Epic 1 → standalone (foundation)
- Epic 2 → uses Epic 1
- Epic 3 → uses Epic 1 + Epic 2
- Epic 4 → uses Epic 1
- Epic 5 → uses Epic 1 + Epic 4
- Epic 6 → uses Epic 1 + Epic 4 + Epic 5 + Epic 3
- Epic 7 → uses Epic 1 (no agent dependency — design system is bootable in parallel with agent work)
- Epic 8 → uses Epic 1 + Epic 6 + Epic 7
- Epic 9 → uses Epic 1 + Epic 6 + Epic 7 + Epic 8 (chrome)
- Epic 10 → uses Epic 1 + Epic 6 + Epic 7 + Epic 8
- Epic 11 → uses Epic 1 (Tauri spike) + Epic 2 (kill-switch) + Epic 7 (edge UI subset) + Epic 12 Story 12.1 (FOIA CLI verifier)
- Epic 12 → uses Epic 1 + Epic 2 + Epic 6 + Epic 7
- Epic 13 → uses Epics 7/8/9/10 (parallel w18–23)
- Epic 14 → explicitly post-V1

### Within-Epic Story Ordering ✅

Every story can be completed using only outputs from stories appearing earlier in its epic (or from prior epics). Spot checks:

- Epic 1: Story 1.1 (scaffold) → 1.2 (CI) → 1.3 (workspace starters) → 1.4 (tokens) → 1.5 (shadcn) → 1.6 (a11y CI) → 1.7 (compose) → 1.8 (schema) → 1.9 (isolation) → 1.10 (fuzz) → 1.11 (envelope) → 1.12 (continuity contracts) → 1.13 (TSA) → 1.14 (LLM interface) → 1.15 (Tauri spike, can run parallel from w3) → 1.16 (admin shell — depends on 1.5) → 1.17 (schema-evolution — depends on 1.8)
- Epic 7: Stories 7.1–7.10 can run parallel (each independent component) → 7.11 (primitives — depends on tokens only) → 7.12 (patterns) → 7.13 (responsive) → 7.14 (Storybook governance — depends on all prior 7.x) → 7.15 (VPAT automation — depends on 7.14)
- Epic 10: 10.1 (schema) → 10.2 (submission endpoint) → 10.3 (supersession citations) → 10.4 (trust-earn-back) → 10.5 (private annotations) → 10.6 (override history UI) → 10.7 (personal audit UI)

No story forward-depends on a later story within the same epic. ✅

### Architecture Alignment ✅

- **Starter templates used:** Epic 1 Story 1.3 initializes per-workspace starters (Next.js 16 App Router for `apps/web`, Tauri 2.x for `apps/edge-agent`, Go module for `apps/foia-cli`, FastAPI+Pydantic+SQLAlchemy+uv for `services/*`) — matches AR2.
- **Database entities created incrementally:** No "Epic 1 creates all tables upfront" anti-pattern. Canonical memory schema (Story 1.8) creates only event log + identity + learning + tombstone + schema-proposals tables (the canonical substrate). Later stories add their own tables as needed:
  - Story 2.1 adds `user_roles`
  - Story 2.4 adds Redis session keys (not SQL)
  - Story 2.6 adds integration state rows (via Alembic)
  - Story 2.7 adds `break_glass_sessions`
  - Story 3.8 adds `ingestion_runs`
  - Story 5.4 adds phase-transition tables
  - Story 6.6 adds action_queue
  - Story 9.7 adds `solidification_review_queue`
  - Story 10.1 adds `override_events`
  - Story 10.5 adds `private_annotations`
  - Story 12.5 adds audit-log S3 bucket (not SQL — object-locked immutable store)

### Story Sizing ✅

Per Party Mode Amelia's feedback: stories most likely to blow a single-session budget were decomposed. Specifically:
- Epic 1's original "canonical memory + RLS + envelope encryption" → split into Stories 1.8 + 1.9 + 1.10
- Epic 5's original "Oracle" → split into Stories 6.3 + 6.4 + 6.5 (three user-facing aspects)
- Epic 4's original "replay-parity cascade" → split into Stories 4.5 (rule) + 4.6 (judge) + 4.7 (human adjudication surface) + 4.8 (gate enforcement)

No story depends on a "phantom" adjudication UI or a smuggled golden-set authoring task — both are explicit stories (4.7 and 4.3/4.4 respectively).

### Non-Negotiable Commitments Mapped to Stories

- **DP1 (No inference outside canonical memory):** Story 6.2 AC explicitly forbids external inference in Cartographer prompts
- **DP2 (Emotional pacing):** Story 8.1 AC enforces hard 3-item top + no shimmer on agent content
- **DP5 (Agent-error explicit):** Story 6.8 contract + Story 7.9 primitive + Story 8.7 surface integration
- **DP8 (Schema evolution under review):** Story 1.17 admin-promotion flow
- **DP10 (Master Strategist internal, suggestions-only):** Story 6.5 (suggestions-only contract) + Story 6.6 (no user-facing UI asserted in AC)
- **DP11 (Trust, repaired):** Story 10.3 + Story 10.4 trust-earn-back

### Defining Experience Protection ✅

The 07:00 → 10:03 identical-citation handshake is protected structurally:
- `CitationChip` ships as a single primitive in Story 7.1 before any surface consumes it
- Epic 7 Storybook governance (Story 7.14) + Chromatic visual regression ensures no surface forks the primitive
- Epic 1 Story 1.12's four continuity-of-reference contract tests gate every release
- Epic 8 Story 8.4's expand-inline latency gate (NFR4) ensures the handshake latency is enforced

### Operability as DoD, Not Standalone Epic ✅

Per Party Mode consensus, Epic 11 (Platform Reliability) was dissolved. Its components are distributed:
- Feature flags + canary → Epic 12 Story 12.11
- SLOs + Grafana + paging → Epic 12 Story 12.10
- Chaos + DR → Epic 12 Story 12.12
- Cost envelope → Epic 12 Story 12.13
- Self-hosted parity → Epic 12 Story 12.9
- SLSA L2 → Epic 1 Story 1.2
- VPAT → Epic 7 Story 7.15 (automation) + Epic 13 Story 13.4 (authoring)

---

**All validations complete.** 14 epics, ~120 stories, full FR + NFR + UX-DR + AR coverage, no forward dependencies, defining-experience-protected structure.

**Next step:** Stories are ready for Dev-agent execution via the `bmad-dev-story` skill, starting with Epic 1 Story 1.1.

