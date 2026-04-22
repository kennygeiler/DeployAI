---
title: "Product Brief Distillate: DeployAI"
type: llm-distillate
source: "product-brief-DeployAI.md"
created: "2026-04-21"
purpose: "Token-efficient context for downstream PRD creation"
companion_inputs:
  - "_bmad-output/brainstorming/brainstorming-session-2026-04-21-150108.md"
---

# DeployAI — Detail Pack

Dense context for PRD, architecture, and first-sprint planning. Assumes reader has NOT loaded the full brief. Every bullet is standalone.

---

## 1. Product One-Liner and Category

- **External positioning:** "Deployment System of Record" — durable, cited, agentic memory for long-cycle customer accounts.
- **Aspirational / vision framing:** "Deployment Operating System" — reserved for 3-year vision; do not use in V1 copy.
- **Primary user:** deployment strategist running 12–36 month hardware+software municipal/enterprise account (simultaneously PM, AM, CS engineer).
- **First deployment:** DeployAI's own NYC DOT LiDAR pavement-analytics engagement — dogfood-on-blue-chip.
- **First external customers (V2):** peer GovTech vendors (infrastructure analytics, utilities, defense, healthcare IT) whose strategists face the same problem.
- **Not-to-build, ever:** competitive intelligence, external-threat mapping, vendor-tracking. This is a strategist productivity tool, not a market-intel product.

---

## 2. The Four Product Surfaces (V1 in-scope; PRD anchor)

Every V1 requirement must be weighable against whether it improves one of these four. If it doesn't, it's out.

### 2.1 Morning Digest
- Three items, hard cap. More items dilute scannability.
- Ranked by **leverage-at-this-moment** (what unblocks/advances today's interaction), not by recency or similarity.
- Each item cites specific events + prior learnings that produced it (citation envelope mandatory).
- Transparency footer: **"What I ranked out"** — the items DeployAI considered but deprioritized, with brief reason. Builds strategist trust + calibrates ranking over time.
- Scannable in ≤60 seconds (unit test: time-to-scan on seeded data).
- Corpus-confidence marker: distinguish learnings derived from within-this-deployment evidence vs. across-deployment patterns. UI must show which.
- **Null-result retrieval supported:** Oracle surfaces *absence* of expected events (e.g., "expected weekly report from stakeholder X not received — last 2 weeks silent") — not only present events.

### 2.2 In-Meeting Alert
- **Private, retrieval-only.** Never audible, never visible to customer, never scripts strategist dialogue. Surfaces named patterns + evidence (e.g., "3-day MVC accepted in 2/2 prior cases") — strategist decides phrasing.
- **Latency budget: ≤8 seconds** from triggering utterance → card rendered.
- **Solidified-only learnings surface in-meeting.** Provisional learnings stay suppressed to prevent noise at high-stakes moments.
- **Phase-tuned confidence floors:** threshold for surfacing is higher in pre-sale/scoping (less room for error) than in value-creation (strategist is established).
- **Learning card references the learning, not the trigger utterance.** Card does not paraphrase what the customer just said; it references the pre-existing learning that applies.
- **Capture path is compliance-native:** local transcription on the strategist's own device for supported meeting platforms (Zoom, Teams, Google Meet, Webex); manual post-meeting upload as fallback for platforms where local capture is not viable. **No bot joins the call. Ever.** This is product architecture, not a workaround.
- Two-party consent required; meeting capture requires explicit user toggle + visible recording indicator on strategist's device.

### 2.3 Timeline / Visibility View
- Live visualization: phases traversed, key events on time axis, stakeholder graph evolving (entries/exits/role changes), landmark learnings surfaced at solidification moments.
- The **"Living Digital Twin" made tangible** — highest-leverage demo surface for prospects evaluating implementation rigor.
- Historical playback: scrub through account trajectory over time.
- Shows current AdvocacyScore(t) per stakeholder, open blockers, phase transition risks, upcoming milestones, causal chain of events leading to current state.

### 2.4 Phase & Task Tracking
- Deployment's current phase (one of seven) + signals accruing toward next transition + phase-specific tasks the strategist should be doing now.
- Blocker-removal items surfaced automatically from communication signals (no standalone Blocker dashboard — blockers are typed events and action-queue items).
- Agent **proposes** phase transitions; strategist **confirms** (symbiotic, never auto-promotes).

---

## 3. The DeployAI Deployment Framework (7 phases — published as open methodology)

Framework is intentionally published as open method; the tool makes it executable. Reference this in all PRD / epic planning.

| # | Phase | Focus | Representative "shmuck alert" trigger |
|---|---|---|---|
| 1 | Pre-sale / Scoping | Incentive mapping; true buyer vs. user | Scope-without-PPI risk |
| 2 | Preparation | Resource logic; LiDAR rollout logistics; data offloading | Unconfirmed upload bandwidth → processing lag |
| 3 | Integration / Data Collection | On-site reality; digital-twin calibration | Calibration shortcut → $20k re-scan in month 9 |
| 4 | User Training | Adoption pattern; end-user vs. champion disconnect | Resistance pattern in field techs |
| 5 | Value Creation | Business case; $X savings; top-10 blocks | Efficiency report not sent to budget office → expansion blocked |
| 6 | Preparing for Expansion | Champion → P&L authority bridging | Current champion lacks P&L authority |
| 7 | Expansion | Scale logic; 10x rollout language | Manual-review process won't scale at 10x |

Phase transitions are **agent-proposed, human-confirmed** — never auto-promoted.

---

## 4. Agent Architecture (three agents, V1)

### Cartographer (passive extraction)
- Scans every communication (email, meeting transcript, call recording, field note) and extracts people, organizations, roles, committees, relationships.
- **Mission-Relevance Triage (pre-extraction gate):** routine low-salience content is logged as event only, not extracted for entity/relationship deltas. Prevents over-extraction noise.
- **Thread (and session) as extraction unit, not individual messages:** email thread or meeting session is the atomic unit; single-message extraction overfits.
- **Person as stable identity with evolving attribute history.** Role changes, title changes, re-orgs → same person node, versioned attributes. Two "Marias" in different orgs should resolve to one identity with time-stamped role transitions.
- **Web-aware identity disambiguation agent (narrow use):** cross-references LinkedIn / government registries to buffer first-last-name duplicates only. NOT a general web-research surface.
- **Blockers are a typed event class (`blocker_candidate`)** detected by Cartographer, filtered into action queue — no standalone Blocker Agent in V1.
- Symbiotic posture: below confidence threshold → enters User Validation Queue, not the canonical store.

### Oracle (learning retrieval + insight surfacing)
- Three modes:
  - **Proactive (Morning Digest):** 3-item hard budget, phase-gated, corpus-confidence marked.
  - **Reactive (In-Meeting Alert):** solidified-only, ≤8s latency, private channel, phase-tuned confidence floor.
  - **Reflective (Evening Synthesis):** proposes new learning candidates + stakeholder attribute updates for weekly review.
- **Surfaces evidence and named patterns, not prescriptive language.** Example: "3-day MVC accepted 2/2 prior cases" ✅. Not: "Tell them: 'We can do a 3-day calibration.'" ❌.
- **Leverage-at-this-moment ranking** — not similarity, not recency. Ranks by potential to unblock/advance current interaction.
- **Phase-gated retrieval** — a learning is eligible only if it matches current deployment phase + stakeholder context.
- **Tiered solidification:**
  - Most new learnings enter as `provisional-in-deployment` automatically; reviewed weekly in batch.
  - **High-impact learnings require explicit human gate** (e.g., learnings that affect a pricing proposal, contract claim, or stakeholder classification).
  - Class-C noise is dropped silently (not queued for review).
- **Rejection with reason:** when a strategist rejects a learning candidate, they provide structured feedback. This trains the calibration history.

### Master Strategist (integration layer, NOT a UI)
- Ranks the action queue (leverage, urgency, phase-fit, blocker-severity).
- Arbitrates inter-agent negotiation (logic runs in V1; trace UI deferred).
- Escalates below-threshold items into User Validation Queue.
- Proposes phase transitions → strategist confirms.
- No independent dashboard surface in V1.

---

## 5. Canonical Memory Substrate (anti-hallucination, anti-drift core)

The product's moat. LLMs are swappable; this is not.

- **Immutable event log.** Every inbound communication, every agent output, every human override is an append-only event with cryptographic attestation.
- **Time-versioned identity graph.** Person nodes persist; attributes (role, AdvocacyScore, political read, committee membership) are time-stamped and queryable at arbitrary `t`.
- **Solidified-learning library with evidence snapshots.** Each learning: `Belief`, `Evidence` (pointer to event + optional snapshot), `Application Trigger` (phase + context), `Manual Solidification` record, confidence, corpus-scope marker.
- **Action queue.** Typed events (blocker_candidate, stakeholder_risk, phase_transition_proposal, learning_candidate, etc.) ranked by Master Strategist.
- **User Validation Queue.** Below-confidence items awaiting human review.
- **Mandatory citation envelope on every agent output.** Agents are retrieval-bound: they cannot emit claims about identities, events, or learnings not already in the store; they can only propose additions, which route through tiered confidence gates.
- **Auditable calibration history.** Every agent parameter change (thresholds, weights, tuning) logs as a first-class event, never silent drift.

### Data boundary (FOIA-aware, PRD-critical)
- **DeployAI-controlled observational data** (sentiment analysis, political read, advocacy scores, strategist notes on municipal employees) lives **outside the customer tenant** and is not discoverable via FOIA on the customer side. This is a contractual MSA boundary as well as a technical one.
- **Customer-controlled data** (emails, meeting recordings from their side, shared documents) is scoped per-deployment and retention-governed to FOIA standards agreed with the customer.
- Data-flow diagram must be published before any new agency conversation (InfoSec precondition).

---

## 6. Testing & Reliability Mandates (non-negotiable for PRD)

- **≥95% test coverage on deterministic code paths.** Original mandate was 100% uptime; refined to ≥95% coverage on deterministic paths (LLM-generation paths tested via replay contracts, not coverage %).
- **Replay tests pin agent behavior across LLM model changes.** When a foundation model version changes, replay suite must pass before promotion to prod.
- **Schema contract tests** on every agent input/output boundary.
- **Fallback tests** for every external-dependency failure mode (LLM unavailable, ingestion pipeline delayed, transcription failure).
- **Canonical-store invariants** tested as properties (no orphan entities, no uncited claims, identity continuity preserved across role changes).
- **Documentation schema tests**: doc claims match code behavior — every release.
- **SLO target:** fewer than 1 severity-2 citation-accuracy incident per 1,000 customer-visible agent outputs per quarter.

---

## 7. Ingestion Paths (V1)

**In:**
- Email (IMAP/Gmail/M365 API — read-only).
- Calendar (Google/M365).
- Meeting recordings: **post-hoc upload only** (local transcription path on strategist device for supported platforms; manual upload fallback).
- Manual notes / voice memos (strategist-authored, uploaded).
- Linear (read-only for tasks/context).

**Explicitly out (architectural commitment):**
- **Bot-join meeting recorders** (Gong, Fireflies, Otter, Fathom pattern). Blocked by government InfoSec; incompatible with compliance-native posture.

---

## 8. Pricing / Commercial Model (three-tier, published)

Published explicitly to prevent bad price anchoring.

| Tier | Who | Price | Trade |
|---|---|---|---|
| Anchor | NYC DOT + future municipal hardware pilots | ~$30K/year (placeholder, pending procurement) | Line item inside hardware SOW, ring-fenced from hardware contract. First tool revenue. Sets discoverable baseline. |
| Design-Partner | First 2–3 peer GovTech vendors, capped at 3 slots | $0–$15K/year | Deep access + co-development rights + named public case-study commitment. Priced *below* anchor because of strategic trade NYC DOT doesn't provide. |
| List | Peer vendors post-StateRAMP Ready | $60K–$150K ARR | 2–5x anchor; scales by active deployment count + vendor size. Public commitment: no closes at list before compliance gate. |

**Scaling narrative:** Anchor → Design-Partner (strategic discount) → List (2–5x post-compliance). The anchor creates reference; the compliance gate unlocks the multiple.

---

## 9. Scope Signals — What's In / Out / Deferred for V1

### In V1 (demo-ready in 12–16 weeks, seeded data)
- Four product surfaces (Section 2).
- Canonical memory substrate (Section 5).
- Three-agent runtime (Section 4): Cartographer, Oracle, Master Strategist.
- Seven-phase state machine with agent-proposed, human-confirmed transitions.
- Ingestion paths per Section 7.
- Documentation package: agent logic docs, product surface docs, deployment logic walkthrough, scope manifest, ingestion doc, documentation provenance trail back to brainstorming atoms.
- Replay-test-pinned demo behavior on seeded data.

### Out of V1 (architected, not engineered)
- Cross-deployment analytics dashboard (waits for N ≥ 3 real deployments).
- Live multi-agent negotiation trace UI (logic runs; trace UI deferred).
- Standalone Blocker dashboard.
- Web-aware verification as a standing surface (retained narrowly for identity disambiguation only).
- Advanced calibration-review tooling beyond basic audit log.
- Cross-corpus statistical promotion machinery (how learnings get promoted across deployments — deferred until N ≥ 2 real).

### Not-to-build, ever
- Competitive intelligence.
- External-threat / vendor-tracking surfaces.
- Market intelligence.
- Bot-join meeting capture.
- Autonomous agent actions on government-adjacent data without explicit strategist authorization.

---

## 10. Rejected Ideas (DO NOT re-propose without new evidence)

- **Competitive/vendor monitoring.** User-vetoed explicitly. Out of scope for this tool permanently.
- **Bot-join meeting recorders.** Architecturally incompatible with government compliance posture. No exceptions.
- **Auto-promoting agent-proposed insights without human review** (for high-impact learnings). Rejected early — tiered solidification is the commitment.
- **Oracle producing prescriptive language / scripted utterances.** Rejected — must surface evidence and named patterns only.
- **Duplicate person nodes on role change.** Rejected — one identity, versioned attributes.
- **Over-extraction of low-salience routine communications.** Rejected — mission-relevance triage gate.
- **Cold pre-sale documentation package as primary GTM motion.** Rejected — docs go *after* live demo, never before.
- **Standalone Blocker Agent / Blocker dashboard in V1.** Rejected — blockers are typed events + action-queue items.
- **Cross-corpus similarity-based retrieval (classic RAG).** Rejected — phase-gated retrieval is the product, not a feature.
- **NYC DOT as free reference deployment with no invoiced tool revenue.** Revised late in planning — tool is now a priced line item (~$30K anchor placeholder), not $0.

---

## 11. User Scenarios (richer than exec-summary)

### S1 — Morning Digest, day 47 of NYC DOT deployment, Phase 4 (User Training)
Strategist opens laptop at 8:15am. Digest shows:
1. "Field-tech adoption resistance pattern detected (2 communications, past 4 days). Pattern seen in 2/2 prior deployments; each resolved via re-framing training around time-savings vs. analytics depth. Evidence: [link to prior deployment learning, link to field-tech messages]."
2. "Champion (Deputy Commissioner) has not been cc'd on training progress in 12 days. In prior deployments, communication gaps of ≥10 days preceded champion disengagement 1/1 times. Suggest: send status update today. Evidence: [comm graph snapshot]."
3. "Calendar shows 3pm call with budget office analyst. AdvocacyScore for this analyst moved from 0.4 to 0.6 after last call; she asked two questions about pothole-reduction stats. Consider leading with that metric. Evidence: [transcript excerpt]."
**Footer:** "Ranked out: upcoming contract renewal (Phase 7 concern, not active now); LiDAR calibration drift warning (low confidence, provisional)."

### S2 — In-Meeting Alert, Phase 3 (Integration)
Customer says: "Can we skip the on-site calibration this time? We're tight on dates."
Within 8 seconds, private card on strategist screen:
> **Prior learning applies.** Skipping on-site calibration in Phase 3 is a solidified failure pattern (1 prior case: $20K re-scan, 6-week delay). Named alternative: 3-day Minimum Viable Calibration, accepted 2/2 prior cases. Confidence: high (solidified, cross-deployment corpus).
Strategist chooses how to phrase response. Card never speaks to them, never scripts. Logged as "alert served" event.

### S3 — Evening Synthesis / weekly review
Friday 4pm. Strategist reviews learning candidates queue:
- 4 provisional-in-deployment items from the week.
- 1 high-impact candidate (proposed update to pricing-proposal template based on Wednesday's budget-office conversation) → requires explicit human gate.
- 2 candidates rejected with structured reason ("insufficient evidence — single data point" / "out of scope — competitive intelligence").
- Calibration history shows Oracle's morning-digest threshold auto-adjusted down 0.05 after 3 rank-out overrides this week; strategist can accept or revert.

### S4 — Cartographer identity continuity
Maria Rodriguez, Program Manager at NYC DOT in month 2, is promoted to Deputy Commissioner in month 14. Same email address, new title in email signature.
- Cartographer detects role-attribute delta.
- Person node `person_maria_rodriguez` gets new time-versioned attribute: `role: Deputy Commissioner, effective: 2026-06-01`.
- Prior `role: Program Manager` is preserved with end-date.
- AdvocacyScore history carries forward; political read updates (P&L authority now yes).
- Agent proposes phase-6 readiness signal: "champion now has P&L authority — prior bridging concern resolved."

### S5 — Timeline playback, prospect demo
Prospect evaluating DeployAI. Strategist scrubs the NYC DOT timeline back to month 3. Prospect watches stakeholder graph update in real-time as each meeting landmark passes. Solidified learnings appear as flags on the timeline at their creation moments. Prospect understands in 90 seconds what the product does — on real deployment data, not seeded.

---

## 12. Competitive Intelligence (specifics worth preserving)

- **Gong / Chorus (revenue intelligence):** sales-cycle only. Nothing for post-sale deployment. Not a competitor — an adjacency.
- **Fireflies / Otter / Fathom / Read.ai (meeting assistants):** atomic per-meeting summaries; bot-join blocked in most government InfoSec; no cross-meeting canonical memory. DeployAI's compliance-native capture + canonical memory is the differentiator.
- **Affinity / Clay (relationship intelligence):** built for outbound/VC sourcing; no deployment-phase dynamics; no AdvocacyScore-over-time. Wrong architecture for the use case.
- **Gainsight / Catalyst / Vitally (customer success platforms):** SaaS-telemetry-centric. Weak for multi-year hardware+services deployments with municipal complexity. The peer-vendor customer is often already paying for Gainsight and knows it doesn't cover deployment.
- **Industry signal:** GovTech services spend growing 20% CAGR, outpacing solutions spend. Agencies are paying more for deployment services every year — the deployment layer is where hardware+software wins or loses accounts.
- **Stakeholder turnover** is industry-named as the #1 silent killer of long-cycle government deployments.
- **Procurement reality:** municipal cycles are 12–24 months. First invoiced revenue from a greenfield pilot is more likely year 2 than year 1. Cooperative-purchasing vehicles (NASPO, GSA Schedule, Sourcewell) are the shortcut and must be filed early.
- **Compliance certification signals:** StateRAMP Ready is the realistic gate for multi-municipal sales; FedRAMP for federal; CJIS for justice-adjacent data. None claimed in V1; V1 posture is "architected for, path engaged on first real pilot."

---

## 13. Technical Context & Constraints

- **Foundation model:** swappable. No model-specific logic in agent cores; agents are retrieval-bound + contract-bound. Replay tests are the contract.
- **Deployment model offered:** single-tenant / self-hosted option available for customers who block shared-tenant LLM calls (expected in sensitive municipal InfoSec reviews). Shared-tenant is the default for design-partner vendors.
- **API-first ingestion.** No browser extension, no bot-join, no desktop agent required for ingestion (local transcription is optional, platform-specific, strategist-controlled).
- **Immutable event log** with cryptographic attestation (append-only, hash-chained — design choice; implementation pending arch stage).
- **Time-versioned identity graph** — design preference for a purpose-built store over retrofitting a generic graph DB; implementation decision deferred to architecture stage.
- **Canonical memory invariants** tested as properties: no orphan entities, no uncited claims, identity continuity preserved across role changes.

---

## 14. Documentation Strategy (Documentation-as-Artifact)

- Documentation is a **product deliverable**, not marketing collateral.
- Docs ship alongside code and are version-controlled with the same release process.
- Traceable via provenance trail to design atoms in the brainstorming corpus (FP, SCOPE, ENG, RP-CART, RP-ORACLE, RP-MS, RP-BLOCKER atom IDs).
- **Sequenced correctly:** docs go to prospects *after* a live demo on real deployment data — never cold pre-sale. Docs reinforce rigor after buyer has seen software work.
- Documentation schema tests pass on every release — doc claims match code behavior, enforced in CI.
- V1 documentation package: agent logic docs, product surface docs, deployment logic walkthrough, scope manifest, ingestion doc, documentation provenance trail.

---

## 15. Open Questions (deferred, not resolved)

- **Exact NYC DOT pricing.** $30K/year is a placeholder pending procurement conversation. Actual may be lower (bundled-discount reality) or higher (full-value capture). Anchor number must be locked before first peer-vendor pricing conversation.
- **Cross-corpus learning promotion mechanics.** How does a learning solidified in deployment A become available to deployment B? Deferred until N ≥ 2 real deployments exist. No machinery in V1.
- **Non-founder design-partner recruitment timeline.** 2 target design partners; path to find them not yet specified (peer-vendor network, GovTech SIG meetups, LinkedIn outreach — TBD).
- **FedRAMP vs. StateRAMP vs. CJIS certification sequencing.** First real pilot dictates which certification path is engaged first; no commitment yet.
- **Graduation decision criteria beyond N ≥ 2.** Decision is "product line / spinout / stay internal" at N ≥ 2 design partners — but success criteria for each option not yet specified (ARR thresholds, team size, investor interest, founder bandwidth).
- **AdvocacyScore(t) calculation spec.** Conceptually defined; concrete formula (sentiment weighting, meeting-attendance weighting, initiative-on-behalf weighting, recency decay) pending first real data.
- **Phase-transition signal spec.** Which combination of events/signals proposes each transition? Conceptual for each of 7 phases; concrete detection rules pending architecture stage.
- **In-meeting alert: false-positive tolerance.** Below-threshold suppression is mandated; exact threshold calibration requires real-deployment data — seeded data will not tune this correctly.

---

## 16. Strategic Decisions Locked (do not re-litigate without new evidence)

- **Dual positioning:** internal utility first, external product later. Graduation decision at N ≥ 2 validated design partners.
- **NYC DOT:** priced bundled line item inside hardware SOW (~$30K/yr placeholder, pending procurement). Anchor price. Not free reference.
- **Pricing:** three-tier (Anchor ~$30K bundled / $0–$15K design-partner / $60K–$150K list post-StateRAMP). Published explicitly.
- **Docs sequencing:** demo-first, docs after. Not cold pre-sale artifact.
- **Category framing:** "Deployment System of Record" for external positioning. "Deployment Operating System" for vision only.
- **Seven-phase DeployAI Deployment Framework:** published as open methodology. Tool makes it executable.
- **Four surfaces, nothing else in V1.** Every scope question weighed against them.
- **Three agents, no Blocker Agent.** Blockers are typed events, not a standalone agent.
- **Canonical memory + citation envelopes = non-negotiable.** Agents are retrieval-bound.
- **Tiered solidification:** provisional default, explicit human gate for high-impact.
- **Compliance-native capture:** no bot-join, ever.

---

## 17. Success Criteria (measurable, SLO-style)

### 12-week
- NYC DOT engages substantively with documentation package + seeded demo.
- Pre-visualization conversation progresses into concrete pilot scoping.

### 12-month product
- DeployAI's own next deployment measurably benefits: shorter Phase 5 → 6 transition, zero surprise stakeholder-turnover losses.
- First traceable reuse of learning across deployments (triggered once deployment #2 begins).
- NYC DOT converts to paid pilot at anchor price.
- One additional municipal prospect enters active pre-visualization.

### 12-month commercial
- NYC DOT SOW includes tool at anchor price (~$30K) as discoverable line item — first tool revenue recognized.
- 2 named peer-vendor design partners in active discovery.
- First design-partner MOU signed.
- Pricing-validation conversations complete with first 3 peer-vendor prospects.

### 24-month commercial
- First recognized peer-vendor design-partner revenue.
- One additional municipal agency in bundled-pricing scoping (target: match or exceed NYC DOT anchor).
- NASPO / GSA Schedule / Sourcewell application filed.
- StateRAMP Ready certification path engaged.

### Operational SLOs (ongoing)
- ≥95% test coverage on deterministic paths, maintained release-over-release.
- <1 severity-2 citation-accuracy incident per 1,000 customer-visible agent outputs per quarter.
- Documentation schema tests pass on every release.

---

## 18. Top Risks (tracked, mitigated)

1. **Single-threaded pipeline (NYC DOT).** Mitigation: 15–20 peer-vendor V2 prospect list + 5 discovery calls within 30 days of V1 build kickoff.
2. **Procurement reality.** Mitigation: 12-month milestone is MOU + SOW line item, not greenfield revenue. Cooperative-purchasing vehicles filed early.
3. **Internal-tool vs. external-product tension.** Mitigation: structural decision framework explicit; graduation at N ≥ 2.
4. **Builder-is-user N = 1.** Mitigation: 2 non-founder design partners by end of V1 build.
5. **FOIA exposure of canonical memory.** Mitigation: MSA data-boundary language; DeployAI-controlled observational data outside customer tenant; customer-controlled data retention-governed.
6. **LLM data-handling InfoSec review.** Mitigation: data-flow diagram published before next agency conversation; single-tenant / self-hosted option offered.

---

## 19. Brainstorming Atoms → Brief Section Traceability

Provenance trail for downstream workflows. Cite atom IDs when updating spec, so traceback to original user intent is preserved.

- **FP (Foundational Problems):** stakeholder turnover, meeting-island problem, tribal knowledge loss, compliance-blocked tooling, invisible value-creation → Brief §"The Problem".
- **SCOPE:** SCOPE #1 (not-to-build CI), SCOPE #2 (First-Deployment-First), SCOPE #3 (four surfaces), SCOPE #4 (don't over-engineer) → Brief §"Scope", §"What Makes This Different".
- **ENG (Engineering mandates):** canonical memory anti-hallucination, ≥95% coverage + replay tests, audited calibration history → Brief §"Technical Approach", §"Success Criteria / Operational SLOs".
- **RP-CART (Cartographer role-play):** mission-relevance triage, thread-as-unit, stable identity + evolving attributes, symbiotic confidence gating, no competitive intel → Distillate §4.
- **RP-ORACLE (Oracle role-play):** 3-item hard budget, "what I ranked out" footer, corpus-confidence marker, null-result retrieval, evidence-not-prescriptive, leverage ranking, in-meeting latency/phase floors, tiered solidification, rejection-with-reason → Distillate §4.
- **RP-MS (Master Strategist role-play):** integration layer not UI, action queue ranking, arbitration, phase-transition proposal → Distillate §4.
- **RP-BLOCKER:** retired as standalone agent; blockers reclassified as typed events → Distillate §4.
