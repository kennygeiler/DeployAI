---

stepsCompleted:

- step-01-init
- step-02-discovery
- step-02b-vision
- step-02c-executive-summary
- step-03-success
- step-04-journeys
- step-05-domain
- step-06-innovation
- step-07-project-type
- step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete

visionContext:
  statement: "DeployAI is the agentic Deployment System of Record — durable, cited, phase-gated memory for every long-cycle customer account at every hardware-enabled software company selling into regulated customers."
  differentiator: "Four surfaces projecting the same Event-Node canonical-memory graph at four zoom levels (second/day/week/account). Phase-gated retrieval (not similarity). Compliance-native capture (no bot-join, local transcription). Agents retrieval-bound with mandatory citation envelopes. Moat is the memory substrate; LLMs are swappable, the graph is not."
  coreInsight: "Long-cycle deployments fail slowly in structurally-addressable ways — lost memory, stakeholder turnover, skipped calibrations, invisible value creation. Phase-gated retrieval over a Living Digital Twin converts those failure modes from inevitable into detectable-and-preventable."
  whyNow:
    - "GovTech services spend growing 20% CAGR outpacing solutions — widening procurement gap"
    - "Bot-join meeting tools structurally excluded from government InfoSec — greenfield category opened by that exclusion"
    - "Canonical memory + citation envelopes newly tractable with current foundation-model extraction fidelity; 12–18 month window to build the substrate before incumbents add hallucinated features on top of atomic summaries"
    - "Founder is running a real municipal deployment now — dogfood-advantage is time-limited"
  aspirationalOnly:
    - "DeployAI Deployment Framework becoming Agile/RACI-level industry vocabulary — vision language only, NOT a PRD success metric"
inputDocuments:

- "_bmad-output/planning-artifacts/product-brief-DeployAI.md"
- "_bmad-output/planning-artifacts/product-brief-DeployAI-distillate.md"
- "_bmad-output/brainstorming/brainstorming-session-2026-04-21-150108.md"
documentCounts:
briefCount: 1
distillateCount: 1
researchCount: 0
brainstormingCount: 1
projectDocsCount: 0
workflowType: "prd"
project_name: "DeployAI"
author: "Kennygeiler"
created: "2026-04-21"

classification:
  projectType: "saas_b2b"
  primaryDomain: "b2b_deployment_ops"
  complianceOverlay: "govtech_adjacent"
  complexity: "high"
  projectContext: "greenfield"
  dogfoodConstraint: "greenfield product, brownfield deployment — V1 features must serve DeployAI's live NYC DOT hardware engagement"

architecturalShapeModifiers:

- "Edge-capture tier — device-resident ingestion (local transcription) as first-class tier with its own reliability + trust contract, remote-kill behavior, signed-binary update channel"
- "Dual deployment topology — shared-tenant + single-tenant/self-hosted over a single invariant substrate; event log, identity graph, learning library, action queue, citation envelope contract must be substrate-invariant across topologies"
- "Bifurcated record-of-truth — customer-tenant artifacts vs. DeployAI observational store; cross-boundary citation resolution; asymmetric retention and FOIA/offboarding cascade; self-hosted collapses the boundary and requires a different data-sharing contract"
- "Deterministic-replay compliance posture — ≥95% coverage on deterministic paths + model-pinned replay tests as first-class NFR (not a QA note); replay-parity semantics (byte-identical | semantic-equivalent | citation-set-identical) must be explicitly chosen"

designCommitments:
  zoomMetaphor: "One Account, Four Distances — Morning Digest (day), In-Meeting (second), Phase/Task (week), Timeline (account). Event Node is the atom across surfaces; citations are deep links, not footnotes."
  inMeetingMode: "pull-primary for V1 (strategist-summoned via hotkey, no system push unprompted); push mode deferred to V2 pending calibration evidence from real deployments"
  inMeetingCardFormat: "peripheral placement, no motion/sound/badges, one noun phrase + one citation, solidified-only enforced as hard gate at Oracle layer, correction affordance faster than dismiss affordance"
  inheritedAccountOnboarding: "first-class named flow; successor-user reaches operational fluency in <4h of Timeline exploration vs. 2–6 weeks industry baseline; optional 'Inheritance Tour' curated playback"
  morningDigestPacing: "rank by leverage, sequence for emotional pacing — actionable-first, watch-item-last"
  trustCalibration: "every surface shows honest confidence signal (solidification evidence count + time window, not softmax-dressed-as-percentage); 'what I ranked out' footer locked as non-deprioritizable"
  accessibility508: "product-shape constraint, not checkbox — In-Meeting card uses non-visual differentiator for solidified/emerging; Timeline scrubbing has full keyboard + screen-reader equivalence; local-transcription captioning story included in edge-tier spec"
  timelineTripleDuty: "primary UX for strategist + demo-close surface for founder-CEO buyer + onboarding surface for successor user; must ship in V1, cannot slip to V1.5"

personas:
  dailyUser: "deployment strategist (4+ yrs, multi-account, the 'Maya' persona) running 12–36 month customer engagements"
  economicBuyer: "founder-CEO / VP Customer Success / Head of Implementation at peer GovTech vendor"
  successorUser: "strategist who inherits an account in year 2 when the original strategist is promoted or leaves; primary retention lever"

competitiveSet:
  primaryIncumbent: "status quo (Notion + Google Docs + strategist's head) — the real switching cost"
  adjacentCategories:
    - "Gainsight / Catalyst / Vitally (CS platforms) — SaaS-telemetry-centric, wrong for hardware+services multi-year deployments"
    - "Gong / Chorus (revenue intelligence) — sales-cycle only, no post-sale memory"
    - "Fireflies / Otter / Fathom / Read.ai (meeting assistants) — atomic per-meeting output, bot-join blocked in gov"
    - "Affinity / Clay (relationship intel) — outbound/VC sourcing, no deployment-phase dynamics"
    - "Kantata / Certinia (PSA) — closest analog, project-accounting-centric not memory-centric"

icpSizing:
  designPartnerTier: "founder-led to early-Series-B (10–50 person) peer GovTech vendors; V1 UX optimizes for this profile"
  listTier: "50–200 person Series B cos post-StateRAMP with dedicated CS/Deployment teams; $60–$150K survives here; multi-strategist team views earned at V2 by this tier"
  sequencingRationale: "founder-led earns the case studies that justify the List-tier multiple; Series B buyers want peer-case-studies before signing six-figure deals"

commercialMotions:
  anchor: "embedded services line inside hardware SOW (~$30K/yr placeholder, NYC DOT) — not self-serve, not PLG, no independent buying process; discoverable line-item pricing for procurement"
  designPartner: "co-development contract with public named case-study rights; $0–$15K/yr; first 2–3 peer-vendor slots"
  list: "SaaS subscription ARR; $60–$150K; activated only after StateRAMP Ready (or equivalent) compliance gate"

riskWatchlist:

- "Substrate divergence between shared and self-hosted deployments — highest risk, cheapest to prevent now"
- "<8s In-Meeting hot-path prototype required before SLO lock — mitigated by pull-primary mode (budget only spends on user request)"
- "Cross-boundary deletion + FOIA semantics need legal sign-off pre-V1 dogfooding"
- "Replay-parity semantics (byte-identical | semantic | citation-set) decision required before coverage-target commitment"
- "Edge-tier remote kill / revocation behavior during live customer meeting — P0 question the template will not ask"
- "Category-creation narrative is a wedge, not claimed — TAM is bottoms-up peer-vendor count ($120M–$750M serviceable), not top-down analyst report"

partyModeInputs:
  round1_classification:
    participants: ["John (PM)", "Winston (Architect)", "Mary (Analyst)", "Sally (UX)"]
    resolvedQuestions:
      - "peer-vendor size for List-tier survival — answer: design-partner ICP is 10–50 person founder-led; list-tier ICP scales to 50–200 person post-compliance"

- "In-Meeting Alert push vs. pull — answer: pull-primary for V1, push deferred to V2"

---

# Product Requirements Document — DeployAI

**Author:** Kennygeiler
**Date:** 2026-04-21

## Executive Summary

**DeployAI is the agentic Deployment System of Record** — durable, cited, phase-gated memory for every long-cycle customer account at hardware-enabled software companies selling into regulated customers (municipal, utilities, defense, healthcare IT). It converts every meeting, email, call, and field note across a 12–36 month deployment into a **Living Digital Twin of the account** — a canonical store of events, stakeholders, and justifiable beliefs — and projects that single graph through four surfaces at four zoom levels:

- **Morning Digest** (day-distance): three items ranked by leverage-at-this-moment, each citing source events, with a transparent "what I ranked out" footer. Scannable in ≤60 seconds.
- **In-Meeting Alert** (second-distance): strategist-summoned private retrieval card during live customer calls — one noun phrase plus one citation, solidified-only, peripheral placement, ≤8-second latency, no bot ever joins the call.
- **Phase & Task Tracking** (week-distance): current phase in the published 7-phase DeployAI Deployment Framework, signals accruing toward next transition, phase-specific tasks, blocker-removal items surfaced from communication signals.
- **Timeline / Visibility View** (account-distance): Living Digital Twin made tangible — scrubbable history of stakeholder graph evolution, phases traversed, and landmark learnings solidifying at their real moments. Serves triple duty: daily strategist UX, demo-close surface for founder-CEO buyer, and first-class onboarding flow for the successor strategist who inherits the account in year 2.

Underneath the surfaces, three agents do the work: a **Cartographer** passively extracts entities and relations; an **Oracle** runs phase-gated, corpus-confidence-marked retrieval to surface the right learning at the right moment; and a **Master Strategist** ranks the action queue, arbitrates negotiations, and proposes phase transitions for human confirmation. Every agent output carries a mandatory citation envelope back to primary evidence in canonical memory — agents are retrieval-bound and cannot emit claims that don't trace to the store.

**The first deployment is DeployAI's own.** V1 is dogfooded inside a live NYC DOT LiDAR pavement-analytics hardware engagement, with the tool shipping as a priced line item inside the hardware SOW (~$30K/year placeholder anchor, pending procurement). V2 extends to peer GovTech vendors — 10–50 person founder-led through Series B cos whose deployment strategists face the same problem without the option of building the tool themselves. The commercial model is three-tier and published explicitly: **Anchor ($30K bundled, reference pricing) → Design-Partner ($0–$15K, first 2–3 peer vendors trading co-development and public case-study rights) → List ($60K–$150K, 2–5× anchor, activated only after StateRAMP Ready certification gate)**.

**The architectural foundation is compliance-native by design, not bolt-on.** No bot-join meeting capture (local transcription on strategist's own device is a first-class edge tier). Two-party consent. Immutable event log with attestation. Time-versioned identity graph. Human-in-the-loop gating on below-confidence agent output. A FOIA-aware bifurcated record-of-truth — customer-authored artifacts inside the customer tenant, DeployAI observational derivatives in a separately-operated store with asymmetric retention and cross-boundary citation resolution. Single-tenant / self-hosted deployment topology offered for customers whose InfoSec blocks shared-tenant LLM calls, over a substrate-invariant memory schema. Deterministic-replay test contracts pinning agent behavior across LLM model version changes, at ≥95% coverage on deterministic code paths.

### What Makes This Special

Incumbents don't solve the deployment strategist's actual problem because none were built for it. Revenue intelligence (Gong, Chorus) is sales-cycle only. Meeting assistants (Fireflies, Otter, Fathom) produce atomic per-meeting summaries, and their bot-join capture model is blocked at municipal InfoSec review. Relationship intelligence (Affinity, Clay) is shaped for outbound and venture sourcing. Customer success platforms (Gainsight, Catalyst, Vitally) are SaaS-telemetry-centric and weak for multi-year hardware-plus-services engagements in regulated verticals. The real incumbent is the **status quo itself** — a strategist's Notion page, Google Doc meeting notes, Slack archive, and the mental model they carry in their head. DeployAI's defensible position rests on five combinations no incumbent can replicate without cannibalizing its existing model:

1. **Canonical memory as the product's actual moat** — an immutable event log, time-versioned identity graph, solidified-learning library with evidence snapshots, and action queue, addressable by phase and identity as first-class keys. Agents are retrieval-bound: the system cannot emit a claim that doesn't trace to the store. LLMs are swappable; the graph is not. Incumbents layer atomic summarization on their existing data models and inherit the hallucination surface they can no longer refactor away.
2. **Phase-gated retrieval, not textual similarity** — DeployAI retrieves a learning because it matches the current deployment phase and stakeholder context, not because the embedding is close. This is the specific failure of RAG that long-cycle deployment use cases actually need fixed. Competitors cannot retrofit phase-gating without rebuilding their retrieval layer.
3. **Compliance-native architecture shipped in V1, not promised for V2** — no bot-join, consented on-device transcription, immutable audit logs, citation-envelope traceability, bifurcated FOIA-aware record-of-truth, human-in-the-loop gating. This lands cleanly inside government InfoSec reviews where incumbents get blocked and buys the addressable market the bot-join category cannot reach.
4. **One account, four distances, one graph** — the four surfaces are projections of the same Event-Node canonical-memory graph. A citation clicked in the Morning Digest resolves to the same node shown in the In-Meeting card and scrolls to the same landmark on the Timeline. Continuity-of-reference across surfaces is an NFR, not a nice-to-have. Competitors shipping "AI features" across disconnected products cannot produce this coherence without unifying their stack.
5. **Dogfooded on a named live municipal deployment** — the first deployment strategist using DeployAI is the founder, running DeployAI's own NYC DOT LiDAR engagement. The documentation package, agent logic, demo surfaces, and first-real-data reference are shaped by actual deployment reality, not imagined personas — and the credibility is named, not aspirational. This is a time-bounded dogfood window; it closes once founder attention scales to a second hardware customer.

**Core insight:** Long-cycle deployments fail slowly in structurally-addressable ways — lost memory, stakeholder turnover, skipped calibrations, invisible value creation. Phase-gated retrieval over a Living Digital Twin converts those failure modes from inevitable into detectable-and-preventable. The four surfaces are the UI; phase-gated retrieval over canonical memory is the product.

## Project Classification

- **Project Type:** `saas_b2b`, with three commercial motions disclosed inside one product: Anchor (embedded services line inside hardware SOW, non-self-serve), Design-Partner (co-development contract, capped at 3 slots), List (SaaS subscription ARR, activated post-compliance gate).
- **Primary Domain:** `b2b_deployment_ops` — deployment operations tooling for vendors running long-cycle implementations. The primary buyer is the peer vendor, not the government agency.
- **Compliance Overlay:** `govtech_adjacent` — the users' data is government-touching, which pulls FOIA, StateRAMP / FedRAMP / CJIS pathway, two-party consent, Section 508, and immutable audit logs into the substrate as hard constraints. The overlay shapes data-layer architecture, not go-to-market surface area.
- **Complexity:** `high` — multi-agent retrieval-bound architecture, mandatory citation envelopes, deterministic-replay test contracts across LLM model versions, dual deployment topology (shared-tenant + self-hosted) over a substrate-invariant memory schema, bifurcated FOIA-aware record-of-truth with cross-boundary flows, edge-capture tier with remote-kill and signed-binary update requirements, three-tier commercial model with independently managed contracts.
- **Project Context:** `greenfield` with a **dogfood constraint** — the product is new, but V1 is built against an existing live NYC DOT hardware SOW and must serve that deployment in real time. V1 scope is capped by what the dogfood deployment actually needs; features that don't serve it don't ship.

## Success Criteria

Each metric below is tied to the differentiator it validates. A metric that does not validate a differentiator does not belong in this PRD.

### User Success

Success is measured per product surface against the user experience the surface must deliver. The four surfaces are projections of one graph, and the metrics honor the zoom-level each surface occupies.

- **Morning Digest (day-distance):** the three-item hard cap is honored on 100% of digests. The digest is scannable in ≤60 seconds by a strategist on their phone with a coffee in hand — measured via first-use time-to-close-app telemetry on seeded-data demos during the 12-week pre-visualization window. The "what I ranked out" footer is present on 100% of digests; its absence is a release blocker. Ordering follows the emotional-pacing rule: highest-leverage actionable item first, watch-item last, on every digest.
- **In-Meeting Alert (second-distance):** the card renders in ≤8 seconds P95 from hotkey summon to visible glyph — a pull-triggered latency budget, not a push one. Solidified-only surfaces in-meeting, enforced as a hard gate at the Oracle layer (emerging items are physically incapable of appearing). The card format is locked: one noun phrase plus one citation, peripheral placement, no motion/sound/badges. The correction affordance is measurably faster (fewer keystrokes, closer to resting hand position) than the dismiss affordance.
- **Timeline / Visibility View (account-distance):** on a NYC-DOT-fidelity seeded-data demo, a founder-CEO reaches comprehension — "I understand how my account is being run" — in ≤90 seconds of scrub. Timeline scrubbing has full keyboard and screen-reader equivalence; a mouse-only Timeline is a Section 508 release blocker, not a retrofit item.
- **Phase & Task Tracking (week-distance):** current phase is visible within one click from every other surface. Phase transitions are always agent-proposed and human-confirmed — 0 auto-promotions in the audit log. Blocker-removal items appear in the action queue within one ingestion cycle of the signal that triggered them.
- **Inherited Account Onboarding (successor-user flow, Timeline-based):** a year-2 successor strategist reaches operational fluency on an inherited account in ≤4 hours of Timeline exploration, versus an industry baseline of 2–6 weeks. Fluency is verified by the successor correctly identifying, unprompted: (a) current deployment phase, (b) top 3 stakeholders and their evolving AdvocacyScore(t), (c) top 5 solidified landmark learnings, and (d) the 3 most recent solidification events.

### Business Success

Business metrics are sequenced around three gates: pre-visualization (12-week), first revenue (12-month), external validation (24-month).

- **12-week pre-visualization milestone:** NYC DOT engages substantively with the DeployAI documentation package and a seeded demo on their own data shape. The pre-visualization conversation progresses into concrete pilot scoping with a named SOW line-item candidate — not a generic "we'll pilot this someday."
- **12-month product milestones (ongoing dogfood proof):**
  - DeployAI's own second deployment measurably benefits: shorter Phase 5 → 6 transition vs. the baseline established by the NYC DOT Phase 5 → 6 duration; zero surprise stakeholder-turnover losses attributable to missed signals that were present in canonical memory; first traceable reuse of a solidified learning from deployment #1 to deployment #2.
  - NYC DOT SOW includes the tool at the anchor price (~$30K/year placeholder) as a discoverable line item — first recognized tool revenue.
  - One additional municipal prospect enters active pre-visualization with a named procurement timeline.
- **12-month commercial milestones:**
  - 2 named peer-vendor design partners in active discovery.
  - First Design-Partner MOU signed.
  - Pricing-validation conversations completed with the first 3 peer-vendor prospects; their willingness-to-pay is documented and the List-tier $60K–$150K anchor is either confirmed or re-anchored from real data.
- **24-month commercial milestones:**
  - First recognized peer-vendor Design-Partner revenue.
  - One additional municipal agency in bundled-pricing scoping — anchor target: match or exceed NYC DOT line item.
  - Cooperative-purchasing application (NASPO, GSA Schedule, or Sourcewell — whichever fits first pilot) filed.
  - StateRAMP Ready certification path engaged (not completed; engaged).
- **Retention lever (validated opportunistically when inheritance events occur):** the first time an inheritance happens at a design-partner vendor, successor onboarding meets the ≤4-hour fluency target and the renewal conversation is unblocked without founder intervention.

### Technical Success

Technical metrics are the architectural invariants the product must hold in production, not aspirational engineering practices. They are release blockers, not KPIs.

- **Canonical memory invariants (property-tested on every commit):**
  - Zero orphan entities in the identity graph.
  - Zero agent-emitted claims lacking a citation envelope resolving to a store event.
  - Identity continuity preserved across all role-change events — same person node, versioned attributes, never a duplicate-identity creation.
- **Test coverage and replay parity:**
  - ≥95% test coverage on deterministic code paths, enforced every release; below-threshold coverage is a release blocker.
  - Replay-parity test suite passes 100% on every LLM model version change before that version is promoted to any environment.
  - **Replay-parity semantics must be chosen before the coverage target is locked** — the team picks one of: (a) byte-identical outputs, (b) semantically-equivalent outputs, (c) citation-set-identical outputs. The chosen semantic is recorded in the PRD and the test suite is written against it.
- **Citation-accuracy SLO:** fewer than 1 severity-2 citation-accuracy incident per 1,000 customer-visible agent outputs per quarter. A severity-2 incident is defined as: an agent-emitted claim whose cited evidence does not support the claim, surfaced to a customer-visible channel, caught either by human review or by the user.
- **In-Meeting hot-path SLO (prototype-gated):** ≤8s P95 hotkey-to-glyph latency on a graph-join + citation-envelope-resolution path, on the target device class. **Prototype evidence is required before this SLO is locked in the PRD as a commitment.** Pull-primary mode mitigates the budget because it only spends on user request, but the target is still measured.
- **Substrate-invariance SLO:** the shared-tenant build and the single-tenant/self-hosted build pass an identical agent-contract test fixture set against identical expected outputs. Any divergence is a release blocker on both builds. The event log, identity graph, learning library, action queue, and citation envelope contract are declared substrate-invariant in architecture.
- **Documentation-schema tests:** doc claims about agent behavior match actual agent behavior — tested as contract assertions on every release. Documentation-as-artifact is enforceable, not decorative.
- **Edge-capture tier reliability:**
  - Remote-kill proven end-to-end within ≤30 seconds of incident detection during live customer meetings, verified in staging.
  - Crash recovery preserves in-flight transcript buffers through graceful degradation (no silent data loss on the capture edge).
  - Signed-binary update channel with verifiable rollback; a misbehaving build is revocable from the strategist's device within the same ≤30-second window.
- **FOIA-aware data-boundary integrity:**
  - Customer-offboarding cascade correctly removes customer-tenant artifacts without corrupting DeployAI-side cross-customer learnings — tested end-to-end before V1 dogfooding.
  - Cross-boundary citation resolution does not leak tenant-A identifiers into tenant-B audit logs.
  - Legal sign-off on the bifurcated-record-of-truth data-sharing contract is completed before V1 dogfooding begins with NYC DOT — a procurement precondition, not a post-hoc concern.

### Measurable Outcomes

Consolidated numeric targets, organized for dashboard/audit readability:


| Metric                                         | Target                           | Gate                                     |
| ---------------------------------------------- | -------------------------------- | ---------------------------------------- |
| Morning Digest item count                      | Exactly 3                        | 100% of digests                          |
| Morning Digest "what I ranked out" footer      | Present                          | 100% of digests                          |
| Morning Digest time-to-scan                    | ≤60 seconds                      | Seeded-data UX test                      |
| In-Meeting Alert latency (pull-triggered)      | ≤8s P95                          | Prototype-gated; continuous post-V1      |
| In-Meeting Alert emerging-learning leaks       | 0                                | Enforced at Oracle layer                 |
| Timeline founder-demo comprehension            | ≤90 seconds                      | Pre-viz demo evidence                    |
| Timeline keyboard/screen-reader equivalence    | 100%                             | Section 508 release gate                 |
| Successor-user fluency on inherited account    | ≤4 hours                         | Verified at first real inheritance event |
| Test coverage (deterministic paths)            | ≥95%                             | Every release                            |
| Replay-parity test pass rate on LLM upgrade    | 100%                             | Every model version change               |
| Citation-accuracy severity-2 incidents         | <1 per 1,000 outputs per quarter | Ongoing SLO                              |
| Substrate invariance (shared vs. self-hosted)  | 100% contract-test parity        | Every release                            |
| Edge-tier remote-kill latency                  | ≤30 seconds                      | Staging-verified before V1               |
| Phase-transition auto-promotions in audit log  | 0                                | Ongoing invariant                        |
| NYC DOT tool revenue recognized                | ~$30K anchor line item           | 12 months                                |
| Named peer-vendor design partners in discovery | 2                                | 12 months                                |
| First Design-Partner MOU                       | Signed                           | 12 months                                |
| First peer-vendor Design-Partner revenue       | Recognized                       | 24 months                                |
| Cooperative-purchasing application filed       | 1 (NASPO/GSA/Sourcewell)         | 24 months                                |
| StateRAMP Ready certification path             | Engaged                          | 24 months                                |


## Product Scope

Scope is defined against the dogfood constraint: V1 features must serve the live NYC DOT hardware engagement. Features that don't serve it are deferred — not because they're bad, but because dogfood is the ground truth for prioritization.

### MVP — Minimum Viable Product (V1, demo-ready in 12–16 weeks on seeded data, then dogfooded on NYC DOT)

- **Four product surfaces at demo-ready fidelity:** Morning Digest, In-Meeting Alert (pull-primary), Timeline / Visibility View (including Inherited Account Onboarding as a named flow — not V1.5), Phase & Task Tracking.
- **Canonical memory substrate:** immutable event log with attestation, time-versioned identity graph, solidified-learning library with evidence snapshots, action queue, User Validation Queue for below-confidence items.
- **Three-agent runtime with mandatory citation envelopes:** Cartographer (passive entity/relation extraction with mission-relevance-triage gate), Oracle (phase-gated retrieval, tiered solidification, corpus-confidence markers), Master Strategist (integration layer — not a UI — for action-queue ranking, arbitration, phase-transition proposal).
- **Seven-phase DeployAI Deployment Framework as an executable state machine:** agent-proposed, human-confirmed transitions. Framework itself published as open methodology alongside V1.
- **Ingestion paths:** email (IMAP / Gmail / M365 read-only), calendar (Google / M365), post-hoc meeting-recording upload, manual notes / voice memos, Linear read-only. No bot-join ever.
- **Edge-capture tier (first-class, not "just an input"):** local transcription for supported platforms (Zoom, Teams, Google Meet, Webex) running on the strategist's own device, with manual post-meeting upload as a fallback for platforms where local capture is not viable. Signed-binary update channel, remote-kill capability, crash-recovery for in-flight transcript buffers. Two-party consent and visible recording indicator enforced.
- **Compliance-native foundation:** immutable audit logs, citation-envelope traceability on every agent output, human-in-the-loop gating on below-confidence outputs, FOIA-aware bifurcated record-of-truth with legal-signed-off data-sharing contract before dogfood begins.
- **Dual deployment topology foundation (not full self-hosted GA yet):** architecture is substrate-invariant and contract-tested; shared-tenant ships first, self-hosted path validated by design (contract tests passing on a reference self-hosted build) even if not GA in V1.
- **Section 508 essentials:** full keyboard + screen-reader equivalence for Timeline scrubbing; non-visual differentiator for In-Meeting card solidified/emerging; captioning story documented for edge-capture transcription tier.
- **Documentation package (documentation-as-artifact):** agent logic docs, product surface docs, deployment logic walkthrough, scope manifest, ingestion doc, documentation provenance trail traceable to brainstorming atom IDs. Documentation schema tests pass on every release.
- **Test coverage and replay tests:** ≥95% on deterministic code paths; replay-parity semantics chosen and documented; replay test suite pinning demo behavior and V1 agent-contract behavior.

### Growth Features (Post-MVP, unlocked at N ≥ 2 validated design partners)

- **Cross-deployment analytics dashboard** — requires a real cross-corpus with N ≥ 3 real deployments before it's genuinely informative; seeded cross-deployment is misleading.
- **Cross-corpus statistical promotion machinery** — how a learning solidified in deployment A becomes available (appropriately abstracted under the FOIA-aware data-sharing contract) to deployment B. Deferred until N ≥ 2 real deployments exist.
- **Live multi-agent negotiation trace UI** — the logic runs in V1; the trace UI is deferred.
- **Advanced calibration-review tooling** — beyond the basic audit log present in V1.
- **Push-mode In-Meeting Alert (opt-in, gated on real-deployment calibration data)** — V1 ships pull-primary; push mode requires calibration from real deployments to set the confidence-floor threshold safely. False-positive-in-live-customer-meeting risk makes this a post-V1 feature, not a toggle.
- **Multi-strategist team views** — for Series B List-tier customers with dedicated CS/Deployment teams. Earned at V2 by the List tier after the design-partner cohort proves the single-strategist UX first.
- **Inheritance Tour curated-playback mode** — the automatic V1 Timeline supports successor onboarding via raw scrub; a curated guided-chapter mode is a nice-to-have refinement once we have first-real-inheritance telemetry.
- **Self-hosted GA** — V1 validates the architecture via contract tests on a reference build; the GA operational wrapper (customer-run deployment automation, observability export, break-glass support model) is a growth-phase deliverable.

### Vision (Future — 3 years)

- **DeployAI is the Deployment Operating System** for every long-cycle deployment at every hardware-enabled software company selling into regulated customers. A deployment strategist joining a peer-vendor company — municipal infrastructure, utilities, defense, healthcare IT — inherits not a folder of legacy docs but a queryable, versioned, cited deployment history going back years.
- **The Living Digital Twin** becomes the default way companies remember, learn from, and transfer knowledge about their most expensive customer relationships.
- **Agents evolve to handle new decision classes:** pricing proposals, contract-renewal risk modeling, cross-account pattern learning once the corpus matures — always through the same foundation: canonical memory, citation envelopes, human-in-the-loop, surface-don't-script.
- **The DeployAI Deployment Framework** — aspirational-only, not a PRD success metric — may become the shared vocabulary the industry uses to talk about long-cycle deployments, the way Agile and RACI became vocabulary. The published open methodology positions for this, but the PRD does not measure against it.
- **Category expansion:** the product proven on municipal infrastructure (NYC DOT hardware dogfood) extends to adjacent regulated-vertical deployment categories (utilities, defense integrators, healthcare IT) — same substrate, same agent contracts, domain-specific phase-framework adaptations.

## User Journeys

V1 journey set covers five distinct user types and nine named arcs, plus one variant persona for accessibility. API-consumer journeys are deferred (V1 ships no external API). Admin work is represented via the DeployAI Operator role because at design-partner scale there is no in-customer admin; multi-strategist team admin is a V2 List-tier concern. Two stakeholder roles — customer-agency procurement reviewer and bifurcated-record-of-truth legal counsel — are one-shot gate users addressed in the contract pack, not product UX. Maya's VP CS cross-account rollup view is drafted as a mini-journey (Journey 10) but scoped as V2 evidence, not a V1 release gate.

### Journey 1 — Morning of a Steering Committee

**Persona:** Maya, deployment strategist, 5 years. Running DeployAI's own NYC DOT LiDAR pavement-analytics engagement, Phase 5 (Value Creation). Monthly steering committee at 10:00am with her champion, the data-ops liaison, and Deputy Commissioner Torres (new, 30 days on the account).

**Opening.** 7:14am on the Q train. Maya opens the Morning Digest. Exactly three items. Top of list: *"Deputy Commissioner Torres attended two steering committees without speaking; quiet-deputy posture at month 9 has twice preceded budget-office reassignment. Suggest: open today with a direct question to Torres on which metric his office carries to budget review."* Confidence marker: *solidified, n=3 evidence events, corpus age 61 days.* Item two: pothole-reduction vs. TCO framing. Item three: unconfirmed Queens borough bandwidth spec (blocker-removal). Footer: *"What I ranked out: 4 items deferred."*

**Rising action.** Maya taps the Torres item; citations deep-link to the 2026-04-15 email thread passage. 35 seconds. She glances at item two, disagrees — her champion has been citing TCO explicitly this month, the pattern is stale — and hits *reject with reason*: "champion has pivoted to TCO this month, evidence dated before 2026-04-01." The reject writes a first-class event into the audit log. The Oracle will down-weight that pattern for this deployment going forward and the "what I ranked out" trail now reflects both system-ranked-out items and user-rejected items in the same log.

**Climax.** 10:06am, live meeting. Maya opens with the Torres question as written. Torres needs a citywide-comparison number for his budget review. A deliverable that was invisible two hours ago becomes the 14-day priority.

**Resolution.** Meeting ends. Maya flags the Torres pattern as a Class-A candidate for further corroboration. She does not need to approve it today — tiered solidification handles the rest.

**Capabilities revealed:**

- Morning Digest (3-item hard cap, leverage ranking, emotional pacing, "what I ranked out" footer as non-deprioritizable)
- **Reject-with-reason affordance** (differentiator vs. atomic-summary tools): user rejection is a first-class event that down-weights future ranking and appears in the audit trail
- Confidence marker semantics (solidified / n-evidence / corpus-age)
- Citation envelope deep-link with breadcrumb-back
- Mobile-first subway-grade reading UX
- Phase-gated retrieval (Phase 5 patterns surface; Phase 7 suppressed)

### Journey 2 — Mid-Call Retrieval Under Social Pressure

**Persona:** Maya. Three weeks later. Phase 5 → 6 transition conversation.

**Opening.** 2:47pm video call. The data-ops liaison proposes skipping a planned 5-day calibration window to "make up time." Maya has a half-memory of this failing before. 15 seconds of silence before it gets awkward.

**Rising action.** Maya hits `⌥⌘K`. Her DeployAI card slides in at the upper-right, peripheral, no sound, no motion. One noun phrase, one citation: *"Brooklyn Bike Lane, Phase 3. Calibration skipped under similar pressure. $20K re-scan, 11-day slip. Event 2025-09-22, Priya's incident note."* Glyph visible **within the ≤8s P95 budget** (exact latency is prototype-gated; the PRD commits to the budget, not to a specific observed number). Solidified diamond glyph is present; this learning is corroborated.

**Climax.** Maya speaks in her own voice: *"We tried a compressed calibration on a Brooklyn deployment. Re-scan cost twenty thousand, eleven-day slip. Three-day minimum-viable calibration instead?"* The liaison pauses, agrees.

**Resolution.** Maya dismisses the card — single keystroke, near resting hand. The system logs it as a *pull-positive retrieval*. An hour later in the full UI, Maya confirms the alert landed correctly. If it had been wrong, she would have hit *correction* — a distinct gesture, in a different screen region, measurably faster than dismiss and intentionally not adjacent to it. A correction under customer-on-screen pressure cannot be reversible-by-accident.

> **Prototype gate:** the correction-vs-dismiss affordance is the single hardest interaction design in the product. The PRD does not lock correction-vs-dismiss visual or gestural mechanics. Prototype evidence on video (Maya on a live call, correction executed without visible disruption to the customer-side view) is required before the In-Meeting Alert UX is frozen.

**Capabilities revealed:**

- In-Meeting Alert: pull-triggered hotkey, peripheral placement, no motion/sound/badges
- ≤8s P95 budget on hotkey-to-glyph (SLO committed; prototype-gated)
- Solidified-only gate at Oracle layer
- One-noun-phrase + one-citation card format (locked)
- **Correction ≠ dismiss:** distinct gesture, distinct screen region, measurably faster than dismiss, non-reversible-by-accident (prototype-gated before UX lock)
- Non-visual solidified/emerging differentiator (Section 508 AND camera-privacy for shared-screen calls)
- Pull-positive retrieval telemetry (future ranking) and correction telemetry (separate signal, not conflated with dismiss)

### Journey 3 — Founder-CEO Demo Close with Citation Stress-Test

**Persona:** David, founder-CEO of a 35-person peer GovTech vendor (drone-inspection software, state-DOT and utility-co-op customers). Already read and passed the documentation package (pre-visualization filter; that's why this call is happening).

**Opening.** 45-minute call. David has blocked seven adjacent tools. He runs a Notion wiki he genuinely believes is the best his team can do.

**Rising action.** Kenny shares the Timeline of DeployAI's NYC DOT account in **presenter mode** — not raw scrub, but a guided narrative overlay where Kenny can annotate and pin beats live, with an inline side-by-side of what the same 14 months would look like in a Notion wiki (stakeholder list as a static page, meeting notes as flat docs). The DeployAI-vs-status-quo contrast is explicit on screen, not left to David's imagination. David watches the stakeholder graph thicken, a landmark-learning diamond bloom at Phase 5, AdvocacyScore(t) drop 22 days before the corresponding stakeholder stopped advocating internally. The system saw it before the strategist did.

**Climax — citation stress-test.** David asks the standard question: *"How do I know the AI is not lying to me?"* Kenny does not answer with a slide. He taps the landmark-learning diamond; the citation panel opens with three evidence events. David reads the first — transcript passage, three sentences highlighted. He taps the breadcrumb back. Then he picks his own test: *"Click on a claim the system made three months ago. Show me the evidence it had at the time."* Kenny does. The system resolves the citation as of that timestamp, showing the evidence set that was available when the claim first solidified — not the current evidence set. David tests two more. Each resolves cleanly. He reads the "what I ranked out" footer from the Morning Digest live. He laughs — *"That's the thing nobody shows you."*

**Resolution.** 90 seconds into the scrub: *"I understand how this account is being run. Send me the design-partner contract."* Within two weeks, MOU signed at Design-Partner tier. Terms include: public case-study rights, a live inheritance event (his senior strategist handing an account to his junior), and the right to see substrate-invariance contract-test results before any future self-hosted install.

**Capabilities revealed:**

- Timeline as triple-duty surface (strategist daily UX + demo-close + successor onboarding)
- **Timeline presenter mode:** pinnable beats, annotation overlay, status-quo side-by-side for demos (not just raw scrub)
- Citation deep-link resolves to primary source with the *as-of-timestamp evidence set* (not only current evidence)
- AdvocacyScore(t) visualization on identity nodes
- Documentation-package-as-pre-visualization-filter (gates which demos happen)
- Design-Partner contract clauses: case-study rights, inheritance-event access, substrate-invariance-evidence delivery

### Journey 4 — Inherited Account Day 1: From Orientation to First Defensible Override

**Persona:** Jordan, 3-year strategist, inherited NYC DOT from Maya. Standing steering committee in 8 days. One Monday morning to get oriented.

**Opening.** 9:02am. Timeline opens scrolled to today with a sidebar: *"Inherited Account Onboarding — recommended path. (1) Scrub the last 90 days. (2) Review the top 5 solidified landmarks. (3) Meet the stakeholder graph. Estimated: 3–4 hours to first defensible decision."* (The commitment is not "fluency." Fluency takes months. The commitment is: *in four hours, Jordan can make a decision on this account and defend it with cited evidence*.)

**Rising action.** Jordan scrubs 90 days. Torres appears, thickens. Maya's "quiet-deputy" landmark blooms at day 17-ago with three cited events. Jordan reads each landmark in the library, evidence-on-tap, 40 minutes in.

At 11:30am, Jordan hits a citation to a 2026-02 SOW amendment. The citation envelope includes a *supersession pointer* — the amendment was itself amended in March. Jordan sees both versions and a note that claims made against the February version automatically resolve to the current version unless an `as-of-timestamp` is specified.

**Climax — the first override.** 1:15pm. Jordan opens the digest for tomorrow's pre-meeting review. Personalized: *"You have not yet appeared on any transcript with Torres. Suggest: 10-minute intro call before the steering committee."* (Derived from the user-to-event co-attendance relation — Jordan's identity has zero co-attendance on this account.)

Item two is a solidified learning: *"Champion responds best to Total-Cost-of-Ownership framing."* Jordan disagrees — the 90-day scrub showed the champion has explicitly pivoted to pothole-reduction framing, confirmed by three of the last four emails. Jordan taps *override with evidence*, cites the three emails, and writes a two-sentence rationale. The system acknowledges: *"Override recorded. The TCO-framing learning will be re-evaluated against your cited evidence. It will not surface in digests for this account until re-corroborated."*

Jordan has just contradicted canonical memory and the system did not break. The audit log shows the override, the cited evidence, and a re-evaluation task now in the Master Strategist's queue.

**Resolution.** 1:50pm. Jordan can run the steering committee. First defensible decision: the intro call with Torres, backed by "I inherited this account and have zero prior contact with him," audit-loggable.

> **Accessibility-primary variant (named persona):** A strategist using keyboard navigation and a screen reader inherits the same account. The Timeline scrub, landmark library traversal, override affordance, and citation resolution are all available through the keyboard + SR path with equivalent information and equivalent time-to-first-defensible-decision. Section 508 is not a post-V1 retrofit; this variant ships in V1 and is a release blocker.

**Capabilities revealed:**

- Timeline as first-class onboarding surface (V1, not V1.5)
- Guided-path sidebar for inherited-account flow
- Landmark library with evidence-on-tap
- **Supersession-aware citation resolution:** citations carry a pointer to the current version; claims resolve to current unless `as-of-timestamp` is specified
- **User-to-event co-attendance as a first-class relation** in canonical memory (attendance provenance: calendar + transcript speaker-diarization + manual)
- **Override-with-evidence affordance:** user can contradict a solidified learning by citing evidence; override is first-class in the audit log and suppresses the overridden learning from future digests until re-corroborated
- Digest personalization by user identity (zero-co-attendance signal)
- Section 508 keyboard+SR equivalence on all of the above — release blocker

### Journey 5 — InfoSec Pre-Visualization Review

**Persona:** Priya, Customer InfoSec Reviewer at a 120-person Series-B peer vendor eyeing the List tier.

**Opening.** Priya receives the documentation-as-artifact package: agent logic spec, ingestion doc, scope manifest, deployment framework spec, compliance-architecture brief (bifurcated-record-of-truth diagram with legal-signed data-sharing contract appendix, edge-capture tier spec with remote-kill procedure, immutable audit log and attestation design, two-party consent and on-device transcription commitment), and a signed reference-architecture letter from an earlier peer operator. No marketing content.

**Rising action.** She reads the edge-capture tier spec: *"no bot ever joins a call"* specified down to the enforcement layer. Remote-kill: ≤30s procedure with signed-binary rollback and verifiable provenance on-device. Substrate-invariance contract-test evidence: shared-tenant and reference self-hosted builds produce identical outputs on the agent-contract fixture set. FOIA-aware data-boundary section: customer-offboarding cascade, cross-boundary citation resolution without tenant-A ID leakage, legal-signed data-sharing contract with amendment lifecycle.

**Climax.** Six-item checklist. Four items usually end reviews. All six have specific named answers. Priya calls to clarify two edge cases (remote-kill interaction with in-flight buffer; delayed legal sign-off on amended data-sharing contract). Both answered with named procedures.

**Resolution.** Sign-off with two conditions — self-hosted deployment for customer-touching environment, annual contract-test evidence delivery as subscription clause. Both already in the Design-Partner-to-List contract template. StateRAMP Ready closes the loop six months later; deal lands at $110K ARR.

**Capabilities revealed:**

- Documentation package as priced, versioned, signed product deliverable
- Contract-test evidence export format (customer-reviewable, not just internal CI)
- Remote-kill and signed-binary-update as procedurally-documented guarantees
- Self-hosted topology as the commercial path for InfoSec-gated segment
- Data-sharing contract amendment lifecycle (addressable without re-contracting)
- Documentation-schema tests enforce doc-matches-behavior on every release

### Journey 6 — Operator Decision Under Pressure

**Persona:** Rafael, DeployAI operator (V1 scale: founder + one). Monitoring edge-capture tier across a small fleet.

**Opening.** 3:14pm Tuesday. Build-health alert from the edge-capture binary on a strategist's laptop: integrity-hash audit failing on 3 of 30 segments. The strategist is 14 minutes into a live customer call.

**Rising action — the three-option tree, and the shame beat.** Rafael opens the operator console: strategist ID visible, customer identity *not* visible (bifurcated-record-of-truth enforced at the operator surface). Build version, last-verified-good checkpoint, integrity-audit trace pointing to a decoder-library regression in the latest signed build. Three options:

- **(a)** Allow capture to continue with integrity flag on the suspect segments. Under FOIA audit, half-trusted evidence is worse than no evidence — a flagged transcript that makes it into an audit artifact becomes a liability. Rejected.
- **(b)** Silently disable capture on this device for the rest of the session. Safe. Also means the strategist finds out from an empty transcript later.
- **(c)** Remote-kill the running binary. Strategist sees a single toast: *"DeployAI capture paused — operator-initiated."* No hidden failure.

Rafael feels the pull of (b) — least disruptive right now — and recognizes it as the cowardly choice. The strategist deserves to know mid-call that their capture has stopped. He selects (c). *"I should have caught the regression in the signed-build review this morning. I didn't. Now the strategist pays for it."*

**Climax.** Remote-kill executes **well under the ≤30s committed budget**. Strategist's toast renders; session ends cleanly. Audit log records: incident ID, detection source, operator decision, elapsed time, affected segment range (customer-identity redacted).

**Resolution.** Rafael rolls the edge-capture binary back to the last-verified-good build — signed rollback, verifiable on-device. Opens a severity-2 incident ticket, tags the decoder regression for the next dev cycle, writes the 4-line post-mortem that will be included in the next-quarter compliance-review packet to design-partner customers.

**Capabilities revealed:**

- Operator console: build-health alerts, per-segment integrity-hash audits, strategist-ID-only visibility
- Remote-kill with ≤30s staging-verified latency; signed-binary rollback with on-device verifiable provenance
- Operator-decision audit schema: incident ID, detection source, decision, elapsed time, segment range (customer-identity redacted)
- Severity-2 incident workflow tied to citation-accuracy and capture-integrity SLOs
- Quarterly compliance-review packet as a recurring operator deliverable

### Journey 7 — Trust Repair: Maya Overrides a Solidified Learning

**Persona:** Maya. Month 11 on the NYC DOT account. The product is six months in and she has relied on it daily.

**Opening.** Morning Digest surfaces a solidified learning — a *confident* one, high evidence count, surfaced in the top-three slot: *"Data-ops liaisons in NYC DOT context prefer async over live calls for schedule changes."* The digest is citing the liaison Maya has worked with for eleven months. Maya reads it and tightens up. That's the opposite of true. The liaison hates async schedule changes — she has said so in three separate voice memos, one of which Maya's Cartographer apparently classified as tone-unrelated.

This is the first time Maya catches DeployAI confidently wrong about a stakeholder she knows well. It matters — if the Oracle's model of this liaison is wrong, *every* downstream recommendation touching her is suspect.

**Rising action.** Maya opens the learning. Five cited evidence events, the top two being sync-call transcripts where the liaison said things like *"text me when you can — I'll get back to you when I'm not in the field"* — and Cartographer extracted these as "prefers async." Maya taps *override with evidence* and cites the three voice memos plus her own annotation: *"She prefers deferred response, not async-as-channel. These are not the same thing. She wants live calls when I'm available; she just can't guarantee when she can take one."*

The system does four things, visibly:

1. **Suppresses the overridden learning immediately** from all surfaces on this account. Maya does not have to see it again while waiting for re-evaluation.
2. **Writes the override as a first-class event** in the audit log — Maya's identity, the cited evidence, her rationale — that a future Jordan inheriting this account will see on the Timeline.
3. **Schedules a Cartographer re-extraction pass** on the three voice memos Maya cited, flagged as "human-correction-indicated."
4. **Adds the mis-extraction pattern to a meta-learning candidate**: *"async-as-channel vs deferred-response extraction ambiguity"* — a Class-C candidate that may or may not solidify depending on whether this pattern recurs across deployments. Maya doesn't have to approve it.

**Climax — the trust-earn-back.** Two weeks later, the liaison gets re-modeled correctly in the Morning Digest. The Digest surfaces a suggestion that leads with *"her preferred communication style (per your override on 2026-06-14): live call, expect deferred response"* — explicitly citing Maya's correction as part of the evidence, not hiding that it was a user override.

This is the trust-earn-back. The system did not paper over its error. It did not pretend it always knew. It surfaced Maya's correction *as part of the reasoning trail*, acknowledging both that it had been wrong and that it was now right because the user corrected it.

**Resolution.** Maya's trust in DeployAI increases from this event, not despite it. Six months later at a peer-vendor conversation, when David asks her *"what do you do when the AI is wrong?"*, she has a specific, emotionally-credible answer.

**Capabilities revealed:**

- **Override with evidence** as a first-class affordance (shared with Journey 4, reinforced under trust-strain)
- **Override-visible-in-reasoning-trail:** user corrections are cited in future recommendations, not hidden. The system never pretends it always knew.
- **Re-extraction pass scheduling:** user overrides trigger Cartographer re-examination of cited evidence with human-correction flag
- **Meta-learning candidates:** cross-deployment extraction-pattern learning (Class-C) as deferred solidification, not user-approved
- **Audit log as inheritance surface:** override events are visible to future strategists inheriting the account
- **Trust-earn-back as an explicit design goal:** corrected behavior is surfaced with the correction in the reasoning trail

### Journey 8 — Replay-Parity Gate on an LLM Model Upgrade

**Persona:** Rafael (operator). A new LLM model version is available. The replay-parity test suite gates promotion.

**Opening.** Release candidate model notification arrives. Rafael queues the replay-parity test suite against the recorded Cartographer+Oracle trace corpus (NYC DOT dogfood + the design-partner seeded corpus).

**Rising action.** The suite runs. Replay-parity semantics chosen at V1 lock are *citation-set-identical* (citation sets produced by the new model match the recorded set on the same input; narrative text may diverge). Results: 98.6% pass rate, 1.4% citation-set divergence on 247 Cartographer extractions and 89 Oracle retrievals.

Rafael investigates the 1.4%. Most are genuine improvements (new model catches a citation the old one missed). Three are regressions — the new model drops a citation the old model correctly made, on a specific passage pattern (quoted email within a meeting transcript).

**Climax — the promotion decision.** Rafael does not promote. He opens a gate-report: the divergence count, the regression cases with exact input/output diffs, the pass-rate summary, and a recommendation to the next dev cycle. The old model stays in production. The gate-report is included in the next quarterly compliance packet — design-partner customers see *why* the model was not promoted, not just a version number.

**Resolution.** The replay-parity gate prevented a silent regression that would have broken citation accuracy on roughly 1% of quoted-email-in-transcript extractions. Without the gate, the regression would have been invisible until it produced a customer-visible severity-2 incident months later.

**Capabilities revealed:**

- **Replay-parity semantics chosen and locked:** citation-set-identical (not byte-identical, not semantically-equivalent). Lock this decision before V1.
- **Replay-parity test suite** runs across recorded Cartographer+Oracle traces from every deployment (not synthetic only)
- **Promotion gate:** 100% pass rate required before model promotion to production
- **Gate-report artifact:** divergence count, regression cases with diffs, recommendation — included in quarterly compliance packet for customer-facing transparency
- **Architectural spike required pre-V1-lock:** run the replay-parity suite on an actual model-version bump on recorded traces. The choice of parity semantics, the coverage target, and the believability of Journey 2's ≤8s budget all depend on this prototype.

### Journey 9 — Customer Offboarding Cascade

**Persona:** Rafael. A design-partner customer has given 90-day termination notice.

**Opening.** Termination notice triggers the offboarding runbook. Under the bifurcated record-of-truth, offboarding is non-symmetric: customer-tenant artifacts (transcripts, meeting recordings, customer-authored notes) have one retention treatment; DeployAI observational derivatives (solidified learnings, extraction patterns, meta-learning candidates, cross-customer pattern data) have another. The data-sharing contract specifies which side each artifact class sits on.

**Rising action.** Rafael runs the offboarding cascade:

1. **Customer-tenant artifacts:** purged per contract (30-day grace, then destroyed; certificate of destruction issued).
2. **DeployAI observational derivatives:** retained per contract — *but* with customer-identity redaction. Solidified learnings that were deployed-only-on-this-customer are either (a) retained with customer-identity redaction if the learning is anonymizable, or (b) destroyed if the learning is inseparable from the customer identity. The contract specifies the rule per artifact class.
3. **Cross-boundary citation resolution:** every citation envelope pointing at a now-destroyed customer-tenant artifact is rewritten to a *tombstone citation*: "evidence existed at `as-of-timestamp`, destroyed on `termination-date` per customer contract, learning `L` was solidified from this evidence." The learning persists; its evidence is attested-destroyed.
4. **Audit log:** the offboarding cascade is itself audit-logged with customer identity, artifact classes affected, and timestamps.

**Climax — the sev-2 customer-facing incident (folded in).** Two weeks post-offboarding, a sev-2 citation-accuracy incident surfaces on a *different* customer: an agent-emitted claim cited a now-destroyed artifact (the tombstone citation was not resolved correctly by the retrieval layer). Rafael opens the sev-2 workflow — which is customer-facing, not just internal. The affected customer is notified with: the exact claim, the broken citation, the investigation timeline, and the remediation. Root-cause: a citation-resolver edge case on tombstone-chained citations. Fixed within the sev-2 SLO window.

**Resolution.** Offboarding cascade completes cleanly. The sev-2 is resolved with customer notification included in the next quarterly compliance packet. The *existence* of the sev-2 is treated as a credibility-earning event, not hidden — the data-sharing contract explicitly specifies that sev-2 incidents are reported to all active customers in the next compliance packet, with customer identity of the affected account redacted.

**Capabilities revealed:**

- **Offboarding cascade procedure:** customer-tenant purge with certificate-of-destruction, DeployAI-derivative retention with customer-identity redaction per artifact class, tombstone citation rewrite, audit log of the cascade itself
- **Tombstone citation:** evidence-destroyed-but-learning-persists pattern with full attestation trail
- **Sev-2 citation-accuracy workflow (customer-facing):** customer notification within SLO, investigation timeline, remediation, disclosure in quarterly compliance packet (affected customer identity redacted)
- **End-to-end test:** offboarding cascade tested on seeded data before V1 dogfood — release blocker, not post-hoc

### Journey 10 — VP CS Cross-Account Rollup (V2 Evidence, Not V1 Release Gate)

**Persona:** Maya's VP CS / Head of Implementation at a design-partner vendor. Oversees 8 deployment strategists across 14 active accounts.

**Opening (abbreviated — V2).** The VP CS logs in at end-of-quarter. Wants a cross-account rollup: where each strategist spends time, the override rate per strategist (a proxy for "how much the system is wrong in each account"), the ranked-out trails (a proxy for "which strategists are under-surfacing items the system thought were important"), and the phase-distribution across the book.

**Why this is drafted but not V1:** at design-partner scale, the VP CS is typically either the CEO (David's role — Journey 3 covers him) or does not yet exist as a distinct role. The cross-account rollup requires N ≥ 4 active accounts at a single customer to be genuinely useful, which means the role becomes material only at the List tier. Drafted here so the PRD acknowledges the rollup view exists as a stakeholder need and so the V1 audit log schema is designed with rollup queries in mind — but the UI is V2 scope.

**Capabilities revealed (V1 implications only):**

- Audit log schema must support cross-account rollup queries (override rate per strategist, ranked-out trail per strategist, phase distribution across a book of accounts)
- V1 ships the *data*; the rollup UI ships at V2 when the role becomes material

### Deferred / Deliberately-Not-Drafted Journeys


| Stakeholder / moment                                                                  | Reason for deferral                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Customer-agency procurement reviewer (price-reasonableness on the $30K SOW line item) | One-shot gate user. Addressed in the commercial contract pack (discoverable line-item pricing, scope severability clause), not in product UX.                                                                                                                      |
| Bifurcated-record-of-truth legal counsel (data-sharing contract signature)            | One-shot gate user. Addressed in the legal contract pack with amendment lifecycle procedure (Journey 5 covers the architectural shape; legal counsel does not interact with product surfaces).                                                                     |
| CFO procurement review                                                                | Journey 3 half-covers buyer economics. No additional product journey adds information. Remaining concerns go to the commercial pack.                                                                                                                               |
| Agency-stakeholder FOIA-style "what do you have on me?" request                       | V1 has no product surface for this; the procedure is documented in the compliance pack (audit log export for a named individual, on FOIA request, with the bifurcated record-of-truth applied). A product UX would be premature before a first real request lands. |
| First self-hosted install walkthrough                                                 | Architecture doc scope (operator runbook). Not product UX.                                                                                                                                                                                                         |
| Weekly action-queue work session                                                      | Scope question flagged for Step 5 (Domain Requirements): is the action queue a V1 surface or a V1.5 surface? No journey forces weekly-queue UX into V1 today.                                                                                                      |
| Master Strategist as a visible agent surface                                          | Scope question flagged for Step 5: Master Strategist is an integration layer in V1, not a UI. No journey shows the user interacting with it directly. Confirm in Domain Requirements that this remains V1-internal.                                                |


### Journey Requirements Summary

The V1 capability surface derived from ten journeys plus variants, with two explicit gating markers: **(A)** = architectural-assumption gate (Architecture doc must lock this contract before the PRD is considered frozen), **(T)** = pre-launch-testable vs. post-ship-evidentiary split.


| Capability                                                                                                                               | Journeys that force it | Gating marker                                                                                                                     | Notes                                                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Morning Digest (3-item cap, "what I ranked out" footer, leverage + emotional pacing)                                                     | 1, 4, 7                | T: pre-launch testable on seeded data                                                                                             | —                                                                                                                                                           |
| Reject-with-reason affordance (first-class event, down-weights future ranking)                                                           | 1                      | —                                                                                                                                 | Differentiator vs. atomic-summary tools                                                                                                                     |
| In-Meeting Alert: pull hotkey, peripheral, ≤8s P95, solidified-only, one-noun-phrase + one-citation                                      | 2                      | T: pre-launch testable (contract test on seeded corpus); observed latency post-ship                                               | SLO budget committed; observed numbers not committed as narrative fiction                                                                                   |
| **Correction ≠ dismiss (distinct gesture, distinct region, measurably faster than dismiss, non-reversible-by-accident)**                 | 2                      | **Prototype gate before UX lock**                                                                                                 | Video evidence of Maya executing correction on a live call without customer-visible disruption required before In-Meeting UX freezes                        |
| Timeline (scrubbable, stakeholder graph evolution, landmark blooms, AdvocacyScore(t))                                                    | 1, 3, 4, 7             | T: pre-launch testable on seeded data                                                                                             | —                                                                                                                                                           |
| **Timeline presenter mode** (pinnable beats, annotation overlay, status-quo side-by-side for demos)                                      | 3                      | —                                                                                                                                 | David isn't scrubbing, he's narrating over a scrub                                                                                                          |
| Citation envelope (deep-link, breadcrumb, as-of-timestamp evidence-set resolution)                                                       | 1, 2, 3, 4, 7          | —                                                                                                                                 | As-of-timestamp is in V1; Journey 3 climax depends on it                                                                                                    |
| **Supersession-aware citation resolution** (time-versioned identity graph query primitive)                                               | 4, 7                   | **A:** time-versioned graph query contract must be lifted into Architecture doc with deleted/merged/split-entity semantics        | —                                                                                                                                                           |
| **User-to-event co-attendance as first-class canonical-memory relation**                                                                 | 4                      | **A:** schema decision, attendance provenance (calendar + speaker-diarization + manual)                                           | Substrate-invariance design check required (self-hosted computes from customer boundary; shared-tenant must not leak)                                       |
| Override with evidence (suppresses overridden learning until re-corroborated; schedules re-extraction; adds to meta-learning candidates) | 4, 7                   | —                                                                                                                                 | Core trust mechanism                                                                                                                                        |
| Override-visible-in-reasoning-trail (corrected behavior cites the correction)                                                            | 7                      | —                                                                                                                                 | Trust-earn-back design commitment                                                                                                                           |
| Inherited Account Onboarding guided-path sidebar                                                                                         | 4                      | T: pre-launch testable on seeded data; "4-hr first-defensible-decision" target post-ship-evidentiary (requires real inheritance)  | —                                                                                                                                                           |
| Accessibility-primary variant on all Timeline/Override/Citation affordances (keyboard + SR)                                              | 4 variant              | T: pre-launch testable (usability study)                                                                                          | 508 is product-shape, gets its own named variant                                                                                                            |
| Documentation-as-artifact package (versioned, signed, schema-tested)                                                                     | 3, 5, 8, 9             | T: pre-launch testable (schema tests on every release)                                                                            | —                                                                                                                                                           |
| Contract-test evidence export (customer-reviewable, annual delivery)                                                                     | 5                      | T: pre-launch testable (fixture snapshot diff)                                                                                    | —                                                                                                                                                           |
| Self-hosted reference build with contract-test parity                                                                                    | 3, 5                   | T: pre-launch testable (agent-contract fixture identity)                                                                          | —                                                                                                                                                           |
| Edge-capture tier (signed binary, on-device transcription, ≤30s remote-kill, signed rollback, crash-recovery)                            | 2, 6, 9                | T: pre-launch testable (staging procedure)                                                                                        | —                                                                                                                                                           |
| **Per-segment integrity-hash schema** (Merkle structure, per-segment redaction without invalidating event attestation)                   | 6                      | **A:** schema commitment must be lifted into Architecture doc                                                                     | —                                                                                                                                                           |
| Operator console (strategist-ID-only visibility, build-health, integrity audit, decision audit log)                                      | 6                      | T: pre-launch testable (procedure + tabletop)                                                                                     | —                                                                                                                                                           |
| Replay-parity test suite + promotion gate (citation-set-identical)                                                                       | 8                      | T: pre-launch testable (gate runs on every model bump); gate-report artifact pre-launch demonstrable                              | **Architectural spike required** — run the suite on a real model-version bump on recorded traces before V1 locks. Gates the ≤8s budget and coverage target. |
| Offboarding cascade (purge, retention-with-redaction, tombstone citations, audit log)                                                    | 9                      | T: pre-launch testable end-to-end before V1 dogfood                                                                               | Release blocker, not post-hoc                                                                                                                               |
| Sev-2 citation-accuracy customer-facing workflow (notification, timeline, remediation, disclosure in quarterly packet)                   | 9                      | T: procedure pre-launch testable; `<1 per 1,000 outputs per quarter` SLO is post-ship evidentiary                                 | —                                                                                                                                                           |
| Phase-gated retrieval (deliberate suppression of non-current-phase items)                                                                | 1, 2, 4                | T: pre-launch testable on seeded data; "0 phase-transition auto-promotions" SLO is post-ship evidentiary (needs live transitions) | —                                                                                                                                                           |
| Bifurcated record-of-truth boundary (customer-tenant vs DeployAI-tenant enforced in citations, operator visibility, offboarding)         | 5, 6, 9                | T: pre-launch testable (tenant-ID leakage tests)                                                                                  | —                                                                                                                                                           |
| Audit log as a cross-account rollup substrate (schema supports rollup queries even if UI is V2)                                          | 10                     | —                                                                                                                                 | V1 data; V2 UI. Journey 10 is drafted, not a V1 release gate.                                                                                               |


**Journey type coverage against step-04 minimum requirements:**

- Primary-user success path → Journey 1
- Primary-user edge case / error recovery → Journey 2 (mid-call retrieval + correction affordance), Journey 7 (trust repair)
- Secondary user (buyer, successor, gate-keeper, leadership) → Journeys 3, 4, 5, 10
- Admin / operator → Journeys 6, 8, 9
- Accessibility-primary variant → Journey 4 variant (explicit named persona, V1 release blocker)
- API consumer → explicitly deferred (V1 has no external API surface)

**Post-party-mode integration log (what changed and why):**

- Added Journey 7 (Trust Repair), Journey 8 (Replay-Parity Gate), Journey 9 (Offboarding Cascade + folded sev-2), Journey 10 (VP CS rollup, V2-drafted)
- Amended Journey 1 (added reject-with-reason beat per Mary's Fireflies-test critique)
- Amended Journey 2 (softened narrative latency number to budget-committed language per Winston; added explicit correction-vs-dismiss prototype gate per Sally)
- Amended Journey 3 (added presenter mode per Sally; added as-of-timestamp citation stress-test per Mary)
- Amended Journey 4 (reframed "fluency" as "first defensible decision" per Sally; first-override climax replaces mastery narrative; accessibility-primary variant named)
- Amended Journey 6 (softened narrative latency per Winston; added operator decision-tree and shame beat per Sally; explicit customer-identity-redaction on operator surface)
- Gated three architectural assumptions as **A**-marked contracts in Requirements Summary (supersession-aware citation resolution, user-to-event co-attendance, per-segment integrity-hash)
- Split success metrics in Requirements Summary into pre-launch testable (**T**) vs post-ship evidentiary (Mary's flag)
- Declined John's cuts (Journey 3, Journey 6): Journey 3 is the Design-Partner commercial tier's only live-validation moment (Mary's single-point-of-failure flag); Journey 6 anchors Journey 5's compliance-native credibility
- Master Strategist agent V1-earning and Action-Queue V1-vs-V1.5 scope flagged to Step 5 (Domain Requirements)

## Domain-Specific Requirements

Primary domain is `b2b_deployment_ops`; the substrate constraints come from the `govtech_adjacent` compliance overlay driven by the users' data being government-touching. This section is organized around a **two-tier gate structure** — Anchor gates (what V1 must deliver to ship the $30K NYC DOT SOW line-item) vs. List gates (what the $60–$150K List tier requires, activated post-StateRAMP Ready). Items that are neither are marked as **Post-V1** and moved to the Future Compliance Roadmap subsection. Each compliance claim in the matrix carries an explicit `V1 Status` (Committed / Ready-at-V1 / Post-V1) and a named evidence artifact; a claim without an artifact is not in the matrix.

### 1. Compliance Commitments Matrix

The load-bearing artifact a Customer InfoSec reviewer (Priya, Journey 5) will read. Every row is testable against a named artifact. Documentation-schema tests key off this matrix.


| #   | Standard / Regulation                                            | Version                                                   | Gate Tier | Scope                                                                                                                                        | Evidence Artifact                                                                                     | Attestation Source                                       | V1 Status                                                                    |
| --- | ---------------------------------------------------------------- | --------------------------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | FOIA / state open-records                                        | NY FOIL (Public Officers Law §84–90)                      | Anchor    | Customer-tenant artifacts, audit log export                                                                                                  | FOIA Export Runbook + sample export bundle                                                            | Internal procedure, legal-reviewed                       | Committed                                                                    |
| 2   | Two-party consent (wiretap)                                      | Per-state (NY ECL, CA PC §632, MA Ch 272 §99, etc.)       | Anchor    | Meeting capture                                                                                                                              | Consent-Check Procedure doc + consent UI screenshots + jurisdiction lookup table                      | Internal procedure, legal-reviewed                       | Committed                                                                    |
| 3   | Section 508                                                      | 2017 Refresh (adopts WCAG 2.0 AA; project targets 2.1 AA) | Anchor    | All product surfaces                                                                                                                         | VPAT 2.4 Rev 508 + third-party accessibility audit + keyboard+SR usability study report               | Third-party accessibility auditor (named vendor, pre-V1) | Committed                                                                    |
| 4   | WCAG                                                             | 2.1 AA                                                    | Anchor    | All product surfaces                                                                                                                         | Same as row 3                                                                                         | Same as row 3                                            | Committed                                                                    |
| 5   | NIST SP 800-53 Moderate baseline                                 | Rev 5                                                     | List      | Shared-tenant + reference self-hosted                                                                                                        | SSP (System Security Plan) + control implementation statements                                        | 3PAO                                                     | Ready-at-V1 (SSP drafted); Post-V1 (full implementation and 3PAO assessment) |
| 6   | NIST SP 800-171                                                  | Rev 3                                                     | List      | Applies to CUI-adjacent handling on future federal path                                                                                      | Alignment memo                                                                                        | Internal                                                 | Post-V1                                                                      |
| 7   | NIST AI Risk Management Framework                                | 1.0                                                       | Anchor    | MEASURE (citation envelope, replay-parity suite, override audit); MANAGE (reject-with-reason, sev-2 disclosure, override-in-reasoning-trail) | AI RMF Mapping Doc linking each RMF function to product controls                                      | Internal, peer-reviewed                                  | Committed                                                                    |
| 8   | StateRAMP                                                        | Ready tier (not Authorized)                               | List      | Shared-tenant + continuous monitoring                                                                                                        | StateRAMP Marketplace listing as Ready; 3PAO attestation letter; continuous-monitoring monthly report | StateRAMP PMO + 3PAO                                     | Post-V1 (target ≤24 months; gated by sub-milestones in §3 below)             |
| 9   | SOC 2                                                            | Type I at V1; Type II post-12mo                           | List      | Shared-tenant operational controls                                                                                                           | Type I report at V1 ship; Type II report at 12-15mo                                                   | CPA firm                                                 | Type I Ready-at-V1; Type II Post-V1                                          |
| 10  | FIPS 140-2 validated cryptographic modules                       | Current validated modules at time of implementation       | Anchor    | Data-at-rest encryption; KMS; TLS modules                                                                                                    | FIPS certificate numbers listed in Architecture doc                                                   | NIST CMVP                                                | Committed (leveraging cloud-provider FIPS-validated KMS)                     |
| 11  | FedRAMP Moderate                                                 | Current baseline                                          | Future    | Shared-tenant federal path                                                                                                                   | Future pursuit                                                                                        | 3PAO + JAB/Agency ATO                                    | Post-V1, unscheduled (triggers when first federal customer enters pipeline)  |
| 12  | CJIS Security Policy                                             | Current policy                                            | Future    | Law-enforcement-adjacent customers                                                                                                           | Future                                                                                                | Customer state CJIS office                               | Post-V1, unscheduled                                                         |
| 13  | State privacy laws (CCPA/CPRA, NY SHIELD, VA CDPA, CO CPA, etc.) | Per-state current                                         | Anchor    | Strategist PII + customer-tenant PII                                                                                                         | Privacy addendum in data-sharing contract + data inventory                                            | Internal, legal-reviewed                                 | Committed                                                                    |
| 14  | GDPR / UK GDPR                                                   | Current                                                   | Future    | Peer-vendor customers with EU operations                                                                                                     | Future                                                                                                | Customer DPAs                                            | Post-V1, on-demand (activates if a design-partner customer has EU ops)       |
| 15  | EU AI Act                                                        | As enacted                                                | Future    | Same trigger as row 14                                                                                                                       | Future                                                                                                | Self-assessment initially                                | Post-V1, on-demand                                                           |
| 16  | Colorado AI Act (and state-level peers)                          | As enacted                                                | Future    | Monitored, not triggered at V1                                                                                                               | Monitoring memo                                                                                       | Internal                                                 | Post-V1                                                                      |


### 2. V1 Anchor Gates (what must ship for the $30K NYC DOT line-item)

The V1 release is gated by, and only by, the items below. Anything not on this list is either a List-tier gate (§3) or Post-V1 (§4). Each commitment is expressed in testable form per John's acceptance criterion.

1. **FOIA export — testable commitment:** "NYC DOT's records officer, without engineering support, can produce a complete, timestamped, cryptographically-verifiable export of any meeting's transcript, citations, and decision trail within 4 business hours of request, in a format accepted by NYC Law Department." FOIA Export Runbook + sample export bundle is the artifact.
2. **Two-party consent — testable commitment:** meeting capture refuses to start when any detected participant is in a two-party-consent jurisdiction and the consent check has not cleared within the last 24 hours; most-restrictive jurisdiction among participants wins; fallback is no-capture.
3. **Section 508 / WCAG 2.1 AA — testable commitment:** a named third-party accessibility auditor produces a VPAT 2.4 Rev 508 and a keyboard+SR usability study report (minimum sample n=5 users, at least 2 primary screen-reader users, executing Journey 4 end-to-end) before V1 ships. Below-threshold findings are release blockers.
4. **Bifurcated record-of-truth — testable commitment:** a per-tenant ID leakage test suite (run on every release) demonstrates zero customer-identity leakage across operator-console, audit-log export, or cross-customer learning surfaces; the data-sharing contract names each artifact class and its retention side; offboarding cascade is end-to-end tested on seeded data before NYC DOT dogfood begins.
5. **Citation envelope mandatory — testable commitment:** a conformance test rejects any agent output lacking a citation envelope resolving to a canonical-memory event; the citation envelope JSON schema is published in the Architecture doc and schema-tested on every release.
6. **Immutable audit + per-segment Merkle hashes — testable commitment:** event-level attestation + per-segment integrity hashes (segments within transcripts, defined in the Architecture doc); RFC 3161 signed timestamps on every audit event from a named trusted timestamp authority; a hash-chain verification CLI ships to customers as part of the FOIA Export Runbook.
7. **On-device transcription + no bot-join — testable commitment:** the product offers no cloud-only transcription path for meeting capture; an architectural conformance test fails the build if any code path initiates a meeting-join session; edge-capture binary is signed, verifiable, and remote-killable ≤30s (Journey 6).
8. **Replay-parity test suite — testable commitment:** citation-set-identical semantics; suite runs on every LLM model version change; 100% pass rate required for promotion; gate-report artifact is included in the quarterly compliance packet (Journey 8).
9. **Canonical memory RTO/RPO — testable commitment:** RPO ≤ 5 minutes, RTO ≤ 4 hours on shared-tenant V1; DR runbook tested pre-V1 on seeded data.
10. **NIST AI RMF Mapping Doc** — delivered as part of the V1 documentation package; links each RMF MEASURE and MANAGE function to a specific product control (citation envelope → MEASURE 2.9, override-with-evidence → MANAGE 4.1, etc.). Used as sales asset and as InfoSec pre-visualization artifact.

### 3. List-Tier Gates (activated post-StateRAMP Ready, targets $60–$150K ARR)

StateRAMP Ready is the commercial gate. It is credible only if the following sub-milestones are hit:

1. **Month 6:** 3PAO engaged, gap assessment complete, remediation plan dated.
2. **Month 9:** SOC 2 Type I report delivered as the evidence scaffold for StateRAMP controls.
3. **Month 12–15:** SOC 2 Type II report delivered (requires 6+ months of operating evidence — cannot be shortened).
4. **Month 18–21:** StateRAMP Ready marketplace listing.
5. **Month ≤24:** List-tier contracts activated.
6. **Continuous monitoring tooling is V1-native** — control telemetry is captured from day one, not retrofit at month 12.

Additional List-tier technical commitments:

- **BYOK / HSM** support for customer-managed keys on reference self-hosted. Customers managing their own keys is a hard requirement for List procurement.
- **Customer-owned SIEM export** (syslog / CEF / OCSF) — delivered as a configurable egress from audit log.
- **PrivateLink / VPC-endpoint** option for shared-tenant customers whose network posture requires it.
- **Substrate-invariance in production** — shared-tenant AND at least one real self-hosted customer deployment in production, both passing the contract-test suite.

### 4. Future Compliance Roadmap (explicitly Post-V1)

Tracked, not scheduled. Activated by trigger conditions, not by calendar.


| Regime                                    | Trigger Condition                                                               | Preparation at V1                                                                                     |
| ----------------------------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| FedRAMP Moderate                          | First federal customer enters pipeline                                          | NIST 800-53 SSP is the shared scaffolding with StateRAMP                                              |
| CJIS                                      | First law-enforcement-adjacent customer                                         | Self-hosted topology is the architectural answer                                                      |
| HIPAA + BAA                               | First healthcare-IT peer vendor whose deployment touches PHI, even tangentially | Data classification fields in canonical memory support PHI tagging (V1 schema-ready, not UI-surfaced) |
| NERC CIP                                  | First utility peer vendor                                                       | Self-hosted topology is the architectural answer                                                      |
| ITAR / EAR                                | First defense integrator peer vendor                                            | Pairs with cleared-personnel self-hosted path                                                         |
| FAR / DFARS flow-down                     | First federal contract                                                          | Supply-chain disclosure documentation already V1                                                      |
| GDPR / UK GDPR                            | First design-partner customer with EU ops                                       | DPA template available on request                                                                     |
| EU AI Act                                 | Same as GDPR trigger                                                            | NIST AI RMF mapping doc is the starting point                                                         |
| State AI disclosure laws (Colorado, etc.) | Threshold-based per state                                                       | Monitoring memo maintained                                                                            |
| Cooperative purchasing (NASPO ValuePoint) | 36-month follow-on after Sourcewell                                             | Sourcewell is the V1 primary path                                                                     |
| Cooperative purchasing (GSA MAS)          | Federal path                                                                    | Post-FedRAMP                                                                                          |


### 5. Technical Constraints (consolidated)

The technical substrate commitments forced by the journey set, architectural gates, and Anchor/List matrix:

- **Canonical memory:** immutable event log with event-level attestation + per-segment Merkle integrity hashes; time-versioned identity graph with supersession/merge/split query semantics; solidified-learning library with evidence snapshots; action queue with the schema specified in §8 below; user-to-event co-attendance as a first-class relation (attendance provenance: calendar + transcript speaker-diarization + manual).
- **Citation envelope:** mandatory on every agent output; JSON schema published and schema-tested; supports as-of-timestamp evidence-set resolution and tombstone-citation rewrite on offboarding.
- **No bot-join meeting capture:** architecturally enforced.
- **On-device (edge) transcription:** signed binary, signed rollback with on-device verifiable provenance, remote-kill ≤30s, crash-recovery on in-flight buffers, two-party consent check gated.
- **Dual deployment topology:** shared-tenant on AWS (committed V1 cloud; cloud-provider invariance is not a V1 commitment on shared-tenant); reference self-hosted build validated by contract-test parity at V1; GA self-hosted is Growth-phase.
- **Cryptography:** FIPS 140-2 validated modules for data-at-rest, KMS, and TLS; FIPS certificate numbers listed in the Architecture doc.
- **Key custody:** shared-tenant uses provider KMS in a named US region; reference self-hosted supports BYOK or customer-managed HSM.
- **Data residency:** US-only single AWS region at V1; multi-region after StateRAMP Ready.
- **Signed time:** RFC 3161 timestamping from a named trusted timestamp authority on every audit log event; referenced from per-segment hash chains.
- **Disaster recovery:** RPO ≤ 5 min, RTO ≤ 4 hr for shared-tenant canonical memory; DR runbook tested pre-V1.
- **Supply chain:** SBOM (SPDX or CycloneDX) generated on every release; signed artifacts via Sigstore/cosign; provenance attestation per SLSA level 2 minimum. Addresses NIST 800-53 SR-3 and StateRAMP supply-chain controls.
- **Replay-parity across LLM model versions:** citation-set-identical semantics, promotion-gate 100% pass, gate-report artifact in quarterly packet. Architectural spike required pre-V1-lock (run the suite on a real model-version bump).
- **Substrate-invariance:** contract-test parity between shared-tenant and reference self-hosted, release blocker on both builds.
- **Test coverage:** ≥95% on deterministic code paths, SAST + DAST in CI.
- **Network isolation (List tier):** PrivateLink / VPC-endpoint option for shared-tenant; VPC-peering documented for self-hosted.
- **Customer-owned SIEM export (List tier):** audit log egress in syslog / CEF / OCSF formats.

### 6. Procurement Compliance

- **Discoverable, severable line-item pricing — testable commitment:** the DeployAI charge on NYC DOT's hardware SOW appears as a named, discrete line-item with a cited price, and a scope description enabling NYC DOT procurement to evaluate price-reasonableness and severability independently of the hardware scope. Sample line-item language is part of the commercial pack.
- **Cooperative-purchasing primary path: Sourcewell** — shortest application cycle, municipal-heavy member base matching NYC DOT and peer municipal agencies, no StateRAMP prerequisite. Target filing: 18–24 months. **NASPO ValuePoint** as a 36-month follow-on once StateRAMP Ready lands (NASPO generally expects StateRAMP Authorized, not Ready; 36-month target is a realistic bridge). **GSA MAS** is not pursued pre-FedRAMP.
- **Supply-chain disclosure:** LLM vendor, cloud-infra provider, and third-party dependencies documented in the pre-visualization package from V1. Buy-American-style disclosures addressable on request.
- **Future FAR / DFARS flow-down:** not V1. Activates at first federal contract.

### 7. Security Clearance

- **V1: not applicable.** NYC DOT LiDAR pavement-analytics data is not classified. DeployAI operator role requires standard background check per the data-sharing contract, not formal clearance.
- **Future cleared-federal path:** self-hosted deployment topology; customer-owned infrastructure; customer-owned access control. Shared-tenant is not viable for cleared environments. No V1 implementation; documented in the Architecture brief.

### 8. Accessibility (with testable shapes)

- **Section 508 conformance + WCAG 2.1 AA** on every product surface. Release blocker.
- **Keyboard + screen-reader equivalence on Timeline scrubbing, Morning Digest reading, Override-with-evidence affordance, and Citation resolution** — named in Journey 4 accessibility-primary variant.
- **Non-visual differentiator on In-Meeting Alert solidified vs emerging** — also serves camera-privacy for shared-screen calls.
- **Captioning story for edge-capture transcription tier:** documented in the edge-capture spec; customer-facing captioning UI is V2.
- **Testable commitment — pre-V1 usability study:** minimum n=5 users including at least 2 primary screen-reader users, executing Journey 4 end-to-end on keyboard only; Journey 1 on mobile with VoiceOver; Journey 2 In-Meeting Alert pull + correction on keyboard. Pass criterion: each user reaches Journey 4 "first defensible decision" and each Journey 1 digest scan in within 150% of the sighted-mouse-user baseline. Below-threshold results are release blockers. Study report is a V1 deliverable.

### 9. Transparency (with testable shapes)

- **Audit log FOIA export:** testable commitment per §2 item 1.
- **Citation envelope as transparency mechanism:** every agent output traces to primary evidence; schema-tested on every release.
- **Override-in-reasoning-trail — testable commitment:** when a solidified learning has been overridden by a user, any future surface that recommends behavior derived from that learning renders an *Override context* badge with a link to the override event. Conformance test: trigger an override on a test learning, trigger a downstream recommendation, assert the badge is present and links to the audit-log event.
- **Sev-2 customer-facing disclosure — testable commitment:** affected customer is notified within 72 hours of severity classification via the contractually-specified channel (email + portal); disclosure includes the exact claim, the broken citation, the investigation timeline, and the remediation step. A template is part of the commercial pack. Summary disclosure to all active customers appears in the next quarterly compliance packet with the affected customer identity redacted.
- **"What I ranked out" footer — testable commitment:** every Morning Digest renders a footer listing the count of deferred items and a one-line reason per item (system-deprioritized or user-rejected-with-reason); footer is non-dismissable.
- **Reject-with-reason audit trail — testable commitment:** user rejection of a digest item writes a first-class audit event with user identity, item ID, reason string, and timestamp; the event appears in the "what I ranked out" trail and down-weights the pattern for this account in subsequent Oracle ranking passes.

### 10. Risks & Mitigations (pruned from 12 → 9, with 2 new entries added)

Items on this table are risks that would *change V1 scope* if they fired. Watch-only risks have been moved to the Risk Register (internal, not PRD-material): state-privacy-law divergence, supply-chain-disclosure evolution, FedRAMP-timeline shift, CJIS-applicability emergence, cooperative-purchasing-velocity variance.


| Risk                                                                                     | Mitigation                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LLM model upgrade silently regresses citation accuracy                                   | Replay-parity test suite + promotion gate (Journey 8); citation-set-identical semantics; gate-report in quarterly compliance packet                                                                                                                                                                        |
| FOIA request exposes improperly-retained data                                            | Bifurcated record-of-truth with contract-specified retention per artifact class; offboarding cascade tested end-to-end pre-V1 (Journey 9); tombstone citations preserve learnings without surviving evidence; signed-time audit log establishes evidentiary admissibility                                  |
| Customer InfoSec late-blocks deployment                                                  | Pre-visualization documentation package as pre-demo filter (Journey 5); substrate-invariance contract-test evidence exportable on request; NIST AI RMF mapping doc as additional reviewable artifact                                                                                                       |
| Edge-capture binary regression during live customer meeting                              | Remote-kill ≤30s + signed rollback (Journey 6); operator console with integrity-hash audit; visible toast to strategist, never silent failure                                                                                                                                                              |
| Cross-tenant data leakage on shared-tenant                                               | Per-tenant ID leakage tests in contract-test suite (run every release); co-attendance signal design-checked for substrate invariance; encryption with per-tenant key scope                                                                                                                                 |
| Accessibility retrofit becomes release-slipping work                                     | 508 as product-shape from V1 (named persona variant in Journey 4); pre-V1 usability study with pass criterion defined (§8); 3rd-party accessibility audit named vendor engaged early                                                                                                                       |
| Agent emits confidently wrong claim about a stakeholder                                  | Override-with-evidence (Journeys 4, 7); override-visible-in-reasoning-trail; re-extraction pass on cited evidence with human-correction flag                                                                                                                                                               |
| Legal delays bifurcated-record data-sharing contract sign-off                            | Amendment lifecycle procedure in contract (Journey 5); sign-off required before V1 dogfood begins with NYC DOT — named procurement precondition; data-sharing contract template drafted as V1 deliverable (§11)                                                                                            |
| **Pricing-anchor re-anchoring (design-partner closes reset List comp)**                  | Pricing-validation conversations documented; if first 3 Design-Partner closes land below $10K, delay List pricing announcement; Anchor precedent remains insulated (priced inside hardware SOW, not on DeployAI rate card); publish pricing-rationale memo only after ≥2 real Design-Partner conversations |
| **Dogfood-window closure (founder attention scales away from NYC DOT before V1 proves)** | Time-box the dogfood window; before founder attention splits, the product must pass the "11th-call test" on seeded NYC DOT data and have an internal second strategist user onboarded; if neither achieved, defer hardware-customer-#2 attention split until reached                                       |


### 11. V1 Documentation Deliverables (Paige's additions)

Documentation is a priced V1 deliverable; these artifacts ship alongside code and are what the documentation-schema tests enforce.

- **Glossary (V1 deliverable, not nice-to-have).** Canonical, one-sentence definition per term with plain-language rewrite column for InfoSec/legal audiences. Minimum V1 entries: canonical memory, bifurcated record-of-truth, citation envelope, citation-set-identical semantics, supersession-aware resolution, tombstone citation, user-to-event co-attendance, as-of-timestamp evidence-set resolution, override-with-evidence, override-in-reasoning-trail, phase-gated retrieval, pull-positive retrieval, reject-with-reason, solidified / Class-A / Class-B / Class-C candidate, replay-parity promotion gate, Merkle integrity per-segment, substrate-invariance contract-test parity, NIST AI RMF MEASURE / MANAGE mapping.
- **Data-Sharing Contract Shape (legal-counsel audience — currently underserved).** Section in the compliance-architecture brief that enumerates: data categories flowing each direction, retention rules per category, sub-processor list, breach-notification SLA, amendment lifecycle procedure, termination cascade procedure, audit rights.
- **Compliance-Architecture Brief with three named diagrams:**
  1. **Bifurcated record-of-truth boundary diagram** — what lives vendor-side vs. customer-side, with PII / FOIA / retention annotations per artifact class.
  2. **Standards-to-certifications flow diagram** — NIST 800-53 → SOC 2 (Type I → Type II) → StateRAMP Ready → (future) FedRAMP / CJIS, showing inheritance.
  3. **Evidence-artifact lifecycle diagram** — citation envelope creation → Merkle anchoring → signed-time attestation → audit log → annual contract-test evidence bundle.
- **FOIA Export Runbook + sample export bundle + hash-chain verification CLI.**
- **Consent-Check Procedure doc + jurisdiction lookup table.**
- **NIST AI RMF Mapping Doc.**
- **Pre-V1 Accessibility Usability Study Report (VPAT 2.4 Rev 508 + study methodology + findings).**

### 12. Scope Questions Resolved (from Step 4)

**Master Strategist agent V1 surface — resolved: V1 INTERNAL only.** No UI in V1; no agent-trace window, no negotiation-log view, no direct interaction surface. Live multi-agent negotiation trace UI is a Growth feature.

**Action Queue V1 schema — resolved with explicit spec:**


| Field                      | Type               | Required                                                                 | Notes                                                                                        |
| -------------------------- | ------------------ | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| `id`                       | UUID               | yes                                                                      | —                                                                                            |
| `account_id`               | foreign key        | yes                                                                      | —                                                                                            |
| `session_id`               | UUID               | nullable (null in V1; required in V1.5 work-session UX)                  | Forward-compat for V1.5                                                                      |
| `blocker_type`             | enum               | yes                                                                      | `missing_signal`, `overdue_followup`, `phase_transition_needed`, `stakeholder_gap`, `custom` |
| `proposed_by`              | enum               | yes                                                                      | `cartographer`, `oracle`, `master_strategist`, `user`                                        |
| `resolution_state`         | enum               | yes                                                                      | `open`, `in_progress`, `resolved`, `deferred`, `rejected_with_reason`                        |
| `assignee`                 | foreign key (user) | yes                                                                      | Single-owner V1. Multi-owner V1.5 via a parallel `assignees` join table, unused in V1.       |
| `sla_timer`                | nullable timestamp | nullable                                                                 | Null in V1 (no SLA enforcement); V1.5 may populate                                           |
| `source_event_ids`         | array of UUIDs     | yes                                                                      | Citations into canonical memory                                                              |
| `reason_string`            | text               | required when `resolution_state` in (`deferred`, `rejected_with_reason`) | Feeds "what I ranked out" footer and Oracle re-ranking                                       |
| `extensions`               | JSON object        | nullable                                                                 | Forward-compat for V1.5 fields without migration                                             |
| `created_at`, `updated_at` | timestamp          | yes                                                                      | RFC 3161 signed on `created_at`                                                              |


V1 UX scope: items surface in the Morning Digest when leverage-ranked into the top three; resolution state is captured through the digest item's affordances (`resolve`, `defer with reason`, `reject with reason`). V1.5 adds a dedicated weekly work-session UX (filter/sort, batch operations, cross-account view). Notification surface at V1 is digest-only (no push/email); V1.5 may add channel-configurable notifications. Persistence is durable (not session-scoped) at V1.

---

## Innovation & Novel Patterns

After critique (Winston, John, Mary, Sally), the innovation list is tightened from seven to **eight product innovations plus two architectural/positioning commitments that are often mistaken for product innovation but aren't.** Claims are made falsifiable where possible; where a claim is reduced to a commitment, it's moved out of this section.

### Product Innovations

Each item names: (1) what's novel, (2) the sharpened foil (what it's novel against), (3) the specified mechanism, (4) the falsifiable validation, (5) the risk.

---

**1. Falsifiable Citation Contract.**

- **Novel:** Citations aren't novel. The *envelope schema rejection in CI* + the *11th-call falsifiability gate* + *signed-time per citation* are. Outputs that fail envelope schema are rejected at agent-boundary before reaching the user; outputs that fail the 11th-call test block release.
- **Foil:** Perplexity, Glean, every RAG app claims citations. None of them reject un-cited outputs at CI, none publish a falsifiable accuracy gate, none carry RFC 3161 signed time per citation. "Citation" as a UI garnish vs. "citation contract" as an enforced architectural primitive.
- **Mechanism:** Citation envelope = `{node_id, graph_epoch, evidence_span, retrieval_phase, confidence_score, rfc3161_ts}`. Schema test in CI rejects outputs lacking any required field. 11th-call test (see Validation Approach §) runs on every merge to `main` against a frozen held-out call.
- **Validation:** 11th-call test gate. Pass threshold: **100% citation-presence on all agent outputs, ≥95% citation-correctness on the golden set, zero hallucinated citations (any hallucinated citation is a release-blocker, not a percentage).**
- **Risk:** Envelope overhead breaches ≤8s In-Meeting Alert budget. Mitigation: envelope present inline at glyph-time; full payload loads async after glyph renders (lazy resolution).

---

**2. Phase-Gated Retrieval with Explicit Scoring.**

- **Novel:** Retrieval keyed on deployment-phase position + stakeholder-graph topology + learning-phase-affinity, with an *explicit ranking function*, not embedding cosine similarity. Addressable-as-structure, not estimable-as-vector.
- **Foil:** LangChain/GPT-copilot apps use retrieve-then-generate over a vector index. They have no deployment-phase model. Meeting assistants have atomic per-meeting retrieval. The gap is not "retrieval exists" — the gap is "retrieval knows what phase you're in and what that phase's surface pattern demands."
- **Mechanism:** `score(learning, context) = phase_affinity_weight(learning.phase_labels, context.current_phase) × recency_decay(learning.last_citation_ts, context.now) × graph_distance_to_active_identity(learning.source_identities, context.active_stakeholders) × evidence_density(learning.source_event_ids.length)`. Tie-breaker: higher evidence-density wins. **Phase-ambiguity degradation:** when current phase is transitioning or when sub-scopes span phases, retrieval returns a *union* across eligible phases with the phase label attached to each citation — never a guess.
- **Validation:** Phase-retrieval audit matrix. Run seeded corpus through Oracle at each of the 7 phase positions × 3 stakeholder topology variants (21 cells). Per cell, measure: (a) phase-appropriate suggestions surfaced, (b) phase-inappropriate suggestions suppressed, (c) ambiguity-handling returns union with labels (no silent guesses). Gate: 100% suppression of phase-inappropriate surfaces (false positives are worse than false negatives at low confidence).
- **Risk:** Phase-gating underperforms vector similarity on certain query classes. Mitigation: hybrid — phase-gating primary, vector similarity as within-phase tiebreaker (already in phase-retrieval audit matrix per-query-class).

---

**3. "One Node, Four Distances, One Felt Object" — Four-Distances Living Digital Twin.**

- **Novel:** One canonical graph → four surfaces (Morning Digest / In-Meeting Alert / Timeline / Phase & Task Tracking) at four zoom levels (day / second / account / week). Continuity is not just "same node in the database" — it's **felt continuity across visual treatment, contextual neighborhood, and state.**
- **Foil:** Competitor products ship "AI features" as disconnected widgets — Gong's call summary, Gainsight's health score, Fireflies' meeting notes — each with its own data model. Users cross-navigate and feel they've entered a different product. Four-distances continuity is a product-shape claim, not a feature claim.
- **Mechanism:** Citations carry `{node_id, graph_epoch}` with alias-forwarding through a merge/split registry; when the stakeholder graph is deduped mid-meeting, a citation clicked from a pre-dedup Digest resolves through the alias table to the post-dedup node. Staleness SLO per surface (Digest: ≤30min; In-Meeting: ≤60s; Timeline: ≤5min; Phase-Tracking: ≤5min). Visual-token library enforces consistent rendering of identity-node chips, confidence affordances, evidence icons, resolved/overridden badges across all four surfaces.
- **Validation:** Four contract tests, all gate-blocking:
  1. **Same-node-resolution test:** citation-ID from Digest click resolves to same `{node_id}` in In-Meeting card and Timeline landmark (across graph-epoch with alias-forwarding).
  2. **Visual-token parity test:** a node renders with identical chip/affordance/icon set on all four surfaces.
  3. **Context-neighborhood test:** the relationship context surrounding a node (stakeholder peers, active blockers, recent events) is the same set on each surface, minus explicit zoom-level collapses (which are documented).
  4. **State-propagation test:** mutations (resolution, override, phase-transition) propagate to all four surfaces within the staleness SLO.
- **Risk:** View-model staleness causes cross-surface inconsistency in the demo moment. Mitigation: In-Meeting Alert is the tightest SLO; degrade gracefully by surfacing a "memory syncing" glyph rather than showing stale state as current.

---

**4. Three-Tier Replay-Parity Adjudication for LLM Model Upgrades.**

- **Novel:** A compliance primitive for AI products: every model-version upgrade must pass a replay-parity test with *citation-set-identical* semantics, adjudicated by a three-tier authority (rule-based → LLM-judge → human). Gate-report is a customer-visible quarterly artifact.
- **Foil:** No incumbent AI product ships a customer-visible model-upgrade parity gate. Most treat model upgrades as silent back-end concerns customers discover through regression. The novelty is not "test your model upgrades" — it's "turn model upgrades into an auditable contract with your buyer."
- **Mechanism:** Replay-parity suite runs recorded trace corpus through old model and new model. Adjudication cascade:
  1. **Rule-based adjudicator (primary authority):** auto-approve if new citation-set is a superset of old (strictly more evidence) OR if all differing citations have strictly higher phase-affinity score than the displaced citations. Auto-reject if new citation-set drops any citation whose evidence was positively-graded in held-out testing.
  2. **LLM-judge (secondary):** runs only for non-rule-decidable diffs; judge itself has its own replay contract and deterministic invocation harness; disagreements with rule-layer flagged for human.
  3. **Human adjudicator (final):** reviews disputes, issues verdict, verdict is logged as part of the gate-report with reasoning cited.
- **Validation:** Architectural spike pre-V1 lock (already flagged). Run the full suite on an actual model-version bump; measure false-regression-rate, false-acceptance-rate (divergent-improvement incorrectly auto-approved), human-disagreement-rate with LLM-judge. Publish as gate-report line items.
- **Risk:** Divergent-improvement incorrectly flagged as regression; false-regression rate drifts with model families. Mitigation: rule-layer is the default authority, LLM-judge is audited, semantics-choice (citation-set-identical) reviewed quarterly with the gate-report.

---

**5. Two-Door Override: Long-Term-Memory Handle with Live-Correction Gesture.**

- **Novel:** Two distinct override surfaces — (a) **live-correction** during In-Meeting Alert with a gesture architecturally separated from dismissal (correction-≠-dismiss), distinct gestures in distinct screen regions; (b) **retrospective override** of a solidified learning with evidence attached — both routed through a single audit trail. User corrections appear in future agent reasoning trails, not hidden.
- **Foil:** AI products don't give users a handle on their long-term memory. They let you reject a *recommendation* (ephemerally, with a thumbs-down), but they don't let you correct a *solidified learning* with evidence attached and see that correction cited back in future reasoning. Recommendations are rejectable; learnings are not. DeployAI makes solidified learnings addressable, correctable, and visible-in-reasoning.
- **Mechanism:** Override events are first-class entries in the canonical memory event log, carrying: `{override_id, user_id, learning_id, override_evidence_event_ids, reason_string, ts}`. Future agent reasoning trails that cite the overridden learning include an "override-applied" sub-citation that links to the override event. **Correction gesture design:** distinct screen region for correction (slide-right = "I have a different belief"), distinct for dismissal (slide-left = "not relevant now"); no silent-learning failure mode where a hurried user teaches the system the wrong thing.
- **Validation:** Pre-V1 usability study (n ≥ 5, per Accessibility §). Seed a wrong agent learning on the test corpus; observe the strategist's override path; measure:
  1. **Trust-recovery Likert (self-report)** at T+0, T+3 days, T+14 days: "I trust DeployAI to remember this correctly." Target: monotonically non-decreasing.
  2. **Behavioral proxy:** willingness to accept the next *unrelated* recommendation without inspecting reasoning trail. Target: return to baseline within 14 days.
  3. **Correction-≠-dismiss gesture accuracy:** 0 silent-mislearning events under timed-condition (8s budget simulated In-Meeting context).
  4. Divergence between (1) and (2) is itself a finding, not a failure — captured in the usability report.
- **Risk:** Override badge exposes user vulnerability to successor users inheriting the account. Mitigation: override events link to authored user identity, but private-annotation scope allows users to add personal notes on their own overrides without exposing to successors; inheritance view respects privacy scopes.

---

**6. Pull-Primary In-Meeting Alert.**

- **Novel:** In-Meeting Alert is structurally **pull-primary** — the strategist's gaze shifts to the card when they want it, rather than the card interrupting them. The inverse of the entire notification category.
- **Foil:** Push-notification is the category default — Slack pings, email popups, Gong live coaching — optimized for not-being-missed, not for preserving user attention in a high-stakes live conversation. Pull-primary is a category-contradicting design choice.
- **Mechanism:** Alert card lives in a persistent reserved-region on the display (lower-right corner or secondary monitor); card state updates silently; no sound, no motion-at-appearance, no modal overlay. Glyph rendered within ≤8s of trigger; content loads async on gaze or click. Two-tier attention: ambient glyph + on-demand expansion.
- **Validation:** Pre-V1 usability study. Measure: (a) strategists' self-reported cognitive interruption during live meetings (Likert, target ≥4/5 "felt non-disruptive"); (b) alert attention rate (percent of triggered alerts actually attended to within the meeting) — target ≥70% without requiring push. Failure: if pull-primary yields <30% attention, consider hybrid pull-with-optional-gentle-push per-user.
- **Risk:** Low attention rate means critical alerts get missed. Mitigation: Oracle ranks alerts by *Leverage-at-This-Moment* (top 3 hard budget); the pull-primary design is acceptable precisely because Oracle is confident enough to risk the alert going unseen if the strategist is deep in conversation — the alert persists in the Action Queue afterwards.

---

**7. Tiered Solidification (Class A/B/C) of Agent Learnings.**

- **Novel:** Not every candidate learning requires user approval. Three classes with distinct solidification paths:
  - **Class A (auto-solidify):** high-confidence extractions from structured sources (e.g., calendar invite's attendee list → stakeholder identity) auto-solidify without user review.
  - **Class B (queued for review):** medium-confidence pattern extractions (e.g., "stakeholder cares more about citizen-complaint metrics than TCO") surface in a weekly review queue.
  - **Class C (noise):** low-confidence signal is logged but not surfaced; remains retrievable via explicit query but never bubbles.
- **Foil:** AI products that treat every learning uniformly either (a) overwhelm users with validation requests, or (b) silently absorb everything and hallucinate. Tiered solidification is an intentional middle: solidify what's obviously true, queue what's interesting, suppress the noise.
- **Mechanism:** Solidification classifier takes `{extraction_source_type, evidence_density, phase_affinity_confidence, stakeholder_graph_support}` → Class. Thresholds are tunable and auditable; each class transition is logged. Manual promotion/demotion between classes is a first-class user action.
- **Validation:** On seeded NYC DOT corpus, measure: (a) Class A auto-solidification accuracy ≥98% (audited by hand-grade of a 50-event sample); (b) Class B weekly queue size ≤20 items (strategist can actually review); (c) Class C recall on re-query (when a strategist searches for a Class-C-suppressed fact, it surfaces via explicit retrieval).
- **Risk:** Class A auto-solidification accuracy drift causes silent wrong-learning. Mitigation: periodic hand-grade audit (monthly V1); Class A downgrade threshold triggers re-queue to Class B.

---

**8. Accessibility-Primary Equivalence.**

- **Novel:** Timeline (the triple-duty surface) ships with keyboard + screen-reader experience that is **equivalent, not reduced** — not a bolt-on SR mode, not a degraded variant. The zoom metaphor works intact across visual and non-visual modalities.
- **Foil:** AI products ship visually-native with accessibility retrofit. Most "accessible" AI products are unusable with a screen reader at the primary work surface. Shipping an accessibility-primary Timeline that preserves the four-distances zoom metaphor across modalities is product shape, not retrofit.
- **Mechanism:** Timeline exposed as keyboard-navigable semantic structure with `{phase, event, citation, identity-node}` as addressable anchors; SR reads node-chip content including confidence affordance, resolved/overridden state, and relationship neighborhood; zoom-level changes announce as state transitions ("Account view. Five phases. Phase 3 active."); Section 508 + WCAG 2.1 AA conformance with formal audit pre-launch.
- **Validation:** Pre-V1 usability study with n ≥ 1 SR-primary user (Journey 4 variant). Task-completion-parity: SR user completes journey within 1.5× sighted-user time on Timeline navigation and citation traversal. VPAT (Voluntary Product Accessibility Template) published at launch.
- **Risk:** Accessibility-primary discipline slows visual feature velocity. Mitigation: accepted trade-off — Section 508 is a procurement gate for NYC DOT and the entire municipal GTM path.

---

### What Is NOT Innovation (honesty test)

These are design commitments, architecture decisions, or GTM plays dressed as novelty:

- **Morning Digest** as a concept (email summaries). The *emotional-pacing + 3-item-hard-cap + "what I ranked out" footer + reject-with-reason audit* combination is a design commitment, not an innovation.
- **Timeline visualization** alone. The *Timeline as triple-duty surface + AdvocacyScore(t) + presenter mode + landmark-bloom* is a design commitment.
- **Agent entity extraction** from transcripts. Cartographer's *mission-relevance triage + person-as-stable-identity-with-evolving-attribute-history + thread-as-extraction-unit* is a design commitment.
- **On-device transcription** (exists in consumer products). The *architecturally-enforced capture tier with signed-binary remote-kill and immutable Merkle-chained output* is a compliance-architecture decision.
- **Audit logs.** The *RFC 3161 signed time + per-segment integrity hashes + tombstone citations + customer-exportable verification CLI* is a compliance-architecture decision.
- **Citation tracking** alone. See Innovation #1 — the innovation is the falsifiable contract, not citations.

### Architectural Commitments Often Mistaken for Product Innovation

Two patterns previously framed as innovations are reframed here. Both carry substantial engineering and strategic commitment; neither is a product innovation per se.

**A. Bifurcated FOIA-Aware Record-of-Truth with Tombstone Citations.**

This is a **compliance-architecture decision**, not product innovation. It is table stakes for govtech — without it, DeployAI doesn't clear procurement. Keeping the spec (because it's load-bearing):

- Customer-tenant artifacts (the customer's evidence) vs. DeployAI observational derivatives (our learnings) in separately-operated stores with asymmetric retention.
- **Tombstone citation spec:** when evidence is destroyed under retention contract, a tombstone survives with exactly: `{citation_id, evidence_class, destruction_timestamp, destruction_authority, learning_hash_contributed_to}`. No snippets, no paraphrase, nothing else. Customer-tenant keeps the full tombstone; the FOIA-record-of-truth keeps only the attestation that learning-hash X had source evidence destroyed per policy Y.
- **Cross-boundary citation resolution:** citation render-time lookup first checks live evidence, then falls back to tombstone with explicit UI treatment ("evidence destroyed under retention contract on [date]").
- Validation: offboarding-cascade end-to-end test on seeded data (Journey 9); cross-boundary leakage test.

**B. DeployAI Deployment Framework (Published Open Methodology).**

This is a **GTM / category-creation play**, not product innovation. Publishing the 7-phase methodology as an open artifact (analogous to RACI, SBAR, Agile) is positioning, not product. Commitment retained because category-creation is load-bearing for the List-tier motion:

- Published framework spec pre-V1-ship.
- Seek ≥3 external deployment strategists (peer-vendor or consulting) to independently categorize a deployment using it within 18 months of publication; consistent phase-assignments → framework is legible; absence of third-party adoption within 18 months → framework stays proprietary and positioning collapses.
- Historical predictors: SAFe/Agile/SBAR succeeded via institutional sponsor + training economy + certification; most vendor-published frameworks failed due to no third-party adoption. Explicit risk.

### Market Context & Competitive Landscape

Calibrated against Mary's evidence pass:

- **Revenue intelligence (Gong, Chorus).** Historically sales-cycle-only; Gong has pushed "Gong for CS" and Forecast into post-sale territory in the last 18 months. Safer framing: *no deployment-phase memory graph, no canonical multi-year account memory, call-centric and cloud-bot-dependent.* Bot-join blocked on government Teams/Zoom tenants with strict meeting policies (not universally, but across the ICP).
- **Meeting assistants (Fireflies, Otter, Fathom, Read.ai).** Atomic per-meeting summaries; no cross-meeting canonical graph; no phase-gating. Bot-join blocked on govt tenants with strict meeting policies (Read.ai and Otter have upload-only and on-device modes; Webex has native transcription — narrower wedge than "universally blocked," still a real wedge).
- **Relationship intelligence (Affinity, Clay).** Shaped for outbound and VC sourcing; no deployment-phase dynamics; no multi-year account memory.
- **CS platforms (Gainsight, Catalyst, Vitally).** SaaS telemetry-centric; atomic health-score models; not built for hardware+services deployment shape. No material signal of deployment-ops pivot.
- **PSA / project accounting (Kantata, Certinia).** Closest adjacent; project-accounting-centric. Kantata announced "Kantata Pulse" / AI insights — marketing-real, thin in substance. Expect a countermove within 12 months; track.
- **Agentic / general-purpose (LangChain apps, GPT-powered copilots).** Retrieve-then-generate pattern. LangChain supports source attribution structurally; what it lacks is *tamper-evident, compliance-graded* envelopes (hash chains, retention classes, NIST AI RMF mapping). Reframe as architectural rigor gap, not capability absence.
- **The real incumbent: status quo (Notion + Google Docs + strategist's head).** This is where the eight innovations above converge as moat: each individually is interesting; together on a compliance-native substrate, unreplicable without platform rewrite at incumbents.
- **The tell: nobody has shipped a FedRAMP-targeted AI substrate for deployment ops.** Not Palantir (too heavyweight, wrong shape), not Govini (analytics-only), not ServiceNow (workflow, not memory). That silence is both the opportunity and the warning: the market is either too small for incumbents to care, or the compliance cost is high enough to deter everyone. Both are true. That's the moat *and* the go-to-market tax.

### Moat Framing (calibrated)

The moat is not "incumbents can't refactor this away." Winston and Mary converge: a public-company incumbent (Gong) could, in principle, ship compliance-native in 24–36 engineering-months — ~30 for on-device capture, ~60–90 for the canonical-memory graph (data-model rewrite, the hardest piece), ~80–120 for citation envelopes + FedRAMP path. Plausible but painful; a public company will not commit that roadmap pre-revenue-signal.

What an incumbent **cannot** ship in 24 months is a canonical memory graph **with operator trust already migrated onto it**. The moat is switching cost on the graph — multi-year account memory + override history + tombstone attestations + FOIA exports in the customer's hands. The graph itself is replicable; operator trust migrated onto DeployAI's graph is not.

### Validation Approach (consolidated)


| Innovation                                     | Validation Path                                                                                         | Evidence Artifact                                                                      | Gate Threshold                                                                                                                         |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Falsifiable citation contract               | CI schema tests + 11th-call test (see below)                                                            | Frozen golden-set grader report                                                        | 100% citation-presence, ≥95% correctness, zero hallucinated citations                                                                  |
| 2. Phase-gated retrieval with explicit scoring | Phase-retrieval audit matrix (7 phases × 3 topology variants)                                           | Audit-matrix report                                                                    | 100% suppression of phase-inappropriate surfaces; union-with-labels on ambiguity (no silent guesses)                                   |
| 3. Four-distances Living Digital Twin          | Four contract tests: same-node-resolution, visual-token parity, context-neighborhood, state-propagation | Continuity contract test report                                                        | All four tests green at each release                                                                                                   |
| 4. Three-tier replay-parity adjudication       | Architectural spike pre-V1-lock; real model-version bump                                                | Gate-report with false-regression-rate, false-acceptance-rate, human-disagreement-rate | Customer-visible quarterly artifact with all three rates published                                                                     |
| 5. Two-door override + trust-repair            | Pre-V1 usability study (n ≥ 5, 2-week follow-up)                                                        | Usability study report                                                                 | Likert monotonically non-decreasing over 14 days; behavioral proxy returns to baseline; 0 silent-mislearning events under gesture test |
| 6. Pull-primary in-meeting alert               | Pre-V1 usability study — cognitive-interruption Likert + attention-rate                                 | Usability study report                                                                 | ≥4/5 non-disruptive; ≥70% attention-rate                                                                                               |
| 7. Tiered solidification                       | Seeded NYC DOT corpus test + monthly hand-grade audit                                                   | Solidification audit report                                                            | Class A ≥98% accuracy; Class B queue ≤20/week; Class C recall verified on re-query                                                     |
| 8. Accessibility-primary equivalence           | Usability study with n ≥ 1 SR-primary user + VPAT audit                                                 | Usability study report + VPAT                                                          | Task-completion-parity within 1.5× sighted time; Section 508 + WCAG 2.1 AA conformance audited                                         |


### The 11th-Call Test (made concrete)

Innovation #1 and by extension #2 lean on this validation primitive. Making it a CI job, not a ceremony:

- **Corpus:** frozen held-out NYC DOT call, chosen by criterion (same deployment, next call in chronology — never cherry-picked). Multiple 11th-calls across the dogfood engagement as calls accumulate.
- **Tooling:** `deployai eval held-out-call --suite nyc-dot` — runnable by any engineer locally; runs in CI on every merge to `main`.
- **Grader:** rule-based (not LLM) — rubric compares agent output citations against a hand-graded golden-set of expected citations per agent output. LLM-judge is NOT authoritative; it is flagged for human adjudication.
- **Pass thresholds:** 100% citation-presence on all agent outputs (no un-cited claims), ≥95% citation-correctness on golden set (cited evidence actually supports the claim), **zero hallucinated citations** (any citation referencing a non-existent or wrong node is a release-blocker, not a percentage).
- **Artifact:** versioned grader report + fixture corpus diff on every run; published as part of the quarterly compliance packet.
- **Validity guard:** 11th-call chosen by criterion, not cherry-picked; multiple 11th-calls over the engagement; failure mode is detectable and published.

### Risk Mitigation (novel-pattern specific)


| Risk                                                                                   | Mitigation                                                                                                                                                                 |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase-gated retrieval underperforms vector similarity on certain query classes         | Hybrid: phase-gating primary, vector similarity as within-phase tiebreaker; per-query-class eval in phase-retrieval audit matrix                                           |
| Citation envelope overhead breaches ≤8s in-meeting budget                              | Lazy-resolution pattern: envelope inline at glyph-time, payload async after glyph renders                                                                                  |
| Replay-parity false-regression (upgraded model improves but flagged as divergent)      | Rule-based adjudicator primary authority; LLM-judge audited secondary; human tertiary; false-regression-rate tracked quarterly; semantics-choice reviewed quarterly        |
| Continuity-of-reference staleness breaks cross-surface demo moments                    | Staleness SLO per surface; degrade to "memory syncing" glyph rather than showing stale state as current                                                                    |
| Override badge exposes user vulnerability to successor users                           | Private-annotation scope on overrides; inheritance view respects privacy scopes                                                                                            |
| Trust-recovery validation passes on weak signal ("user didn't complain")               | Paired instrument: self-report Likert + behavioral proxy; divergence between them is itself a finding                                                                      |
| Pull-primary alert yields low attention rate in field                                  | Oracle's Leverage-at-This-Moment ranking; alerts persist in Action Queue post-meeting; hybrid pull-with-gentle-push considered if attention <30%                           |
| Class A auto-solidification accuracy drifts silently                                   | Monthly hand-grade audit (V1); Class A downgrade threshold triggers re-queue to Class B                                                                                    |
| Accessibility-primary discipline slows visual feature velocity                         | Accepted trade-off; Section 508 is procurement gate for NYC DOT and municipal GTM                                                                                          |
| Published DeployAI Deployment Framework is not adopted by 3rd parties within 18 months | Seed with 2-3 non-DeployAI users at publication; if adoption absent at 18mo, framework stays proprietary — positioning-collapse risk named explicitly                      |
| Tombstone citations confuse customers under FOIA audit                                 | FOIA Export Runbook documents tombstones; legal counsel reviews contract language; customer has explicit opt-out (destroy learning alongside evidence) under amended terms |
| 11th-call test gamed by cherry-picking                                                 | Next-call-in-chronology criterion; multiple 11th-calls across engagement; failure mode detectable                                                                          |
| Kantata/Gong ship countermoves faster than expected (12 months)                        | Moat is switching cost on graph + operator trust, not the graph itself; NYC DOT dogfood migrates trust before competitors ship                                             |


## `saas_b2b` Specific Requirements

**Classification note:** Primary domain is `b2b_deployment_ops` with `saas_b2b` as the project-type shape. This section covers the `saas_b2b` shape (multi-tenancy, RBAC, subscription tiers, integrations, compliance) with an explicit **deployment-ops overlay** for the attributes that generic SaaS B2B doesn't capture (multi-year retention, deployment-phase metadata as first-class, successor-handoff data model).

### Project-Type Overview

DeployAI is a **single-tenant-per-account-at-scale SaaS product** with compliance-native architecture, deployed in two topologies (shared-tenant SaaS + reference self-hosted), priced in three tiers (Anchor / Design-Partner / List post-StateRAMP), with a deliberately focused integration catalog that leads with the compliance-native wedge (no bot-join, on-device capture, FOIA-bound egress). V1 dogfooded on the NYC DOT anchor account; Anchor-sequenced feature priorities over feature-catalog parity with incumbents.

### Tenancy Model (`tenant_model`)

**Dual topology:**

- **Shared-tenant SaaS (V1 primary):** AWS, single US region, FIPS 140-2 validated KMS (provider-managed keys), PrivateLink/VPC-endpoint for enterprise isolation. Tenant isolation at the application layer via ReBAC authorization tuples (see §RBAC). Canonical memory is per-tenant; cross-tenant reads architecturally impossible (no shared canonical-memory graph across tenants).
- **Reference self-hosted (V1 deliverable for List-tier enterprise buyers):** BYOK/HSM customer-owned keys, VPC-peering, on-prem OAuth flows (Exchange on-prem, AD FS / Entra hybrid). Parity requirement: every V1 integration that works on shared-tenant must declare its self-hosted parity status (🟢 parity / 🟡 partial / 🔴 not supported).

**Deployment-ops overlay:** account-lifetimes are multi-year (7+ years retention default for municipal anchor); canonical memory does not expire by account-age; only explicit customer-directed destruction under retention contract triggers tombstone citations. This differs from typical SaaS B2B where data is often purged at churn.

### RBAC / Authorization Model (`rbac_matrix`)

**Authz engine decision: ReBAC on OpenFGA (self-hosted, V1).** Pure RBAC doesn't model the successor-inherits-account + privacy-scoped-overrides + tenant-scoped-strategist requirements without role explosion. OpenFGA (Zanzibar-model) expresses these natively as relation tuples: `account#assignee`, `account#successor_of`, `annotation#private_to`, `canonical_memory#accessible_to`. Decision rationale: Cedar is AWS-flavored; Oso's cloud pivot is operationally risky; home-grown is malpractice for a FedRAMP-path product; OpenFGA is CNCF-stage, self-hostable, and FedRAMP-friendly.

**V1 active roles (shipping with auth flows):**


| Role                                                                                                                          | Canonical Memory                               | Action Queue                  | Overrides                                  | Audit / FOIA     | Schema Evolution                                              | Agent Config                                                         |
| ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------- | ------------------------------------------ | ---------------- | ------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Deployment Strategist** (tenant-scoped — same role governs Anchor, Design-Partner, Successor, future List-tier strategists) | read/write on assigned accounts                | own + reassign within account | create w/ evidence; private-annotation own | read own actions | propose schema additions (writes to staging field)            | —                                                                    |
| **Platform Admin** (DeployAI internal; represented as `is_platform_admin` flag, not a separate role row)                      | no tenant read without break-glass (see below) | —                             | —                                          | read             | approve/reject staging schema additions; promote to canonical | tune Cartographer/Oracle/Master Strategist parameters w/ audit trail |


**V1 data-model-supported, no active-user-at-dogfood:**

- **Successor Strategist** — same `Deployment Strategist` role, assigned via the Inherited Account Onboarding journey. No occupants in months 1–6 (founder is the only strategist). Data model, journey, and authz tuples ship V1; active use is post-dogfood.

**V1 JIT / time-bounded access:**

- **External Auditor (3PAO, SOC 2 auditor)** — scoped to audit log + controls evidence bucket, JIT-granted via OpenFGA tuple with TTL (typical engagement: 30–90 days), watermarked exports, no canonical memory access. Required by M6 for 3PAO engagement; ship V1 to avoid scramble.

**V1 no-DeployAI-login (runbook + CLI only):**

- **Customer Records Officer (FOIA/FOIL)** — produces FOIA exports via signed CLI; verifies signatures externally via open-source verification tool. No login, no RBAC row.

**Deferred to V1.5:**

- **VP Customer Success (rollup view)** — rollup journey is V1.5 per Step-4; role ships V1.5.
- **Customer Admin (buyer-side user mgmt)** — N=1 at dogfood; runbook-managed by DeployAI CS. Ships V1.5 before second List-tier close to avoid back-porting under pressure.

**Deferred to List tier gate (post-StateRAMP, M6+):**

- **Customer IT/Security (SIEM egress consumer)** — no canonical memory access; consumes SIEM stream only.

**Break-glass mechanics (V1, specified):**

1. **Contractual consent via MSA clause** — explicit contractual provision, not opt-in checkbox.
2. **Dual-approval required:** on-call engineer + Security Officer, two humans, two YubiKeys.
3. **Customer notification before session opens:** signed email to designated Security contact + portal banner; 15-minute objection window for non-emergency access.
4. **Session recorded, scoped to ticket, auto-expires ≤4h.**
5. **Transcript delivered post-hoc** to customer Security contact.
6. No exceptions for "just checking something."

**Schema evolution permission:** Cartographer auto-extraction writes proposed new fields to a staging field; Platform Admin approves/rejects/promotes to canonical. Strategist can *propose* schema additions via UI (also lands in staging); the AI never mutates the canonical schema unsupervised. Audit trail on every transition.

**Privacy-scoped annotations enforcement:** private override annotations stored in a **separate `annotation_visibility` table** with distinct encryption key, NOT a row-level filter on the main annotations table. OpenFGA tuple check precedes every query. Row-level filters in Postgres are historically leaky — missed `WHERE` clauses leak data; the separate-table + distinct-key design is belt-and-suspenders.

### Subscription Tiers (`subscription_tiers`) — recap (locked in Product Brief + Domain Requirements)

- **Anchor:** $30K/year placeholder (NYC DOT), priced as line-item inside hardware SOW. All V1 must-ship features; FOIA Export CLI; shared-tenant with PrivateLink or self-hosted reference (customer choice).
- **Design-Partner:** $0–$15K/year for first 2–3 peer vendors. Trade deep access + case studies for pricing relief. All V1 features.
- **List:** $60K–$150K ARR per vendor, activates post-StateRAMP Ready (M6+). Adds: SIEM egress (syslog/CEF/OCSF push + pull-API fallback with 72h replay buffer), network isolation options (PrivateLink / VPC-endpoint standard; VPC-peering for self-hosted), customer-owned KMS keys (BYOK/HSM for self-hosted), continuous monitoring package, Customer Admin role for self-serve user management.

### Integrations (`integration_list`) — Anchor-sequenced, not feature-catalog-sequenced

**Integration authentication model:** native OAuth clients per provider, **no broker** (Nango/Merge/Paragon are rejected for V1). Rationale: brokers add a sub-processor that breaks StateRAMP data-flow diagrams and forces extra DPAs. Revisit brokers only when integration count exceeds 15. Six V1 providers × ~2 engineer-weeks each is budgetable; the data-flow simplicity is worth the linear cost.

**Per-integration kill-switch (V1 non-negotiable):** every integration has a toggle visible in both the strategist UI and the ops console. Toggling OFF revokes the OAuth token + purges in-flight queue + emits an audit event + updates the integration status on the Account Memory Health surface.

**V1 must-ship (Anchor-sequenced):**


| #   | Integration                                                                    | Anchor Need                                                                                                                                                    | Self-Hosted Parity                        |
| --- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 1   | **M365 Calendar (via Microsoft Graph)**                                        | NYC DOT is M365-standardized (NYC ITS municipal standard)                                                                                                      | 🟡 on-prem Exchange via hybrid Entra      |
| 2   | **Exchange / M365 Email (via Microsoft Graph)**                                | Anchor-critical; primary email stack at NYC DOT                                                                                                                | 🟡 on-prem Exchange via hybrid Entra      |
| 3   | **Microsoft Teams transcription import**                                       | Municipal meetings on Teams; **must-ship, not V1.5** — deferring blocks Anchor adoption                                                                        | 🔴 Teams is cloud-only; self-hosted skips |
| 4   | **Voice / meeting upload (direct file, no bot-join)**                          | All tiers, all topologies                                                                                                                                      | 🟢                                        |
| 5   | **On-device edge-capture agent, macOS + Windows parity**                       | NYC DOT strategist team is ~60/40 Windows; macOS-only cuts off majority. Ship both V1, or redefine edge-capture as browser-extension + server-side processing. | 🟢 (binary distribution, same tier)       |
| 6   | **FOIA Export CLI — open-source, Sigstore-signed, customer-machine execution** | Anchor-critical; municipal procurement gate                                                                                                                    | 🟢 same binary                            |
| 7   | **SAML / OIDC SSO + SCIM provisioning (Entra ID / AD FS primary)**             | **Anchor-blocking** — NYC DOT will gate procurement on Entra ID integration. StateRAMP Ready also expects it.                                                  | 🟢 (on-prem AD FS supported)              |


**V1 dogfood-only (confirm founder stack; may be zero):**

- Google Calendar, Gmail — ship only if founder uses them at dogfood; otherwise defer to Design-Partner unlock (peer vendors skew Google).

**V1 stretch (Anchor-expansion-relevant):**

- **Webex transcription import** — Cisco-SLED penetration means some municipal-expansion accounts run Webex. Not Anchor-critical but relevant for expansion beyond NYC DOT.
- **Linear read-only sync** — peer-vendor dogfood use (DeployAI's own team); not Anchor-relevant.

**V1.5+:**

- Zoom native transcription import
- Salesforce CRM sync; HubSpot / Pipedrive / Attio (peer-vendor CRMs)
- Slack digest delivery
- ServiceNow workflow hook
- State-specific SIEM / SSO providers (M12+, follow Sourcewell → NASPO expansion)

**List tier gate (M6+):**

- **SIEM egress** — push (syslog/CEF/OCSF) as primary + pull-API with cursor-based pagination as fallback for customer-SIEM outages. 72-hour replay buffer. Both push AND pull — customers expect both.

**"Never" list (V1 + durably):**

- Cloud bot-join meeting capture (structural exclusion; the product is designed against this)
- Autonomous agent actions on customer data without explicit strategist authorization
- Behavioral/profiling integrations for advertising or user-tracking (even via enterprise vendors)
- LLM API passthrough that exfiltrates canonical memory to third-party tools
- Public-internet APIs for canonical memory access at V1 (even authenticated) — V1 is dogfood + design-partner scoped; broad public-API access is V1.5+ with explicit threat modeling
- Competitive intelligence / outside-threat monitoring (out of scope per brainstorming `[SCOPE #1]`)

### Compliance Requirements (`compliance_reqs`) — recap

Fully specified in the Domain-Specific Requirements § (two-tier gate structure, Anchor vs. List). Load-bearing items for the `saas_b2b` shape:

- **FIPS 140-2 validated modules** for encryption-at-rest, KMS, TLS
- **US-only single-region data residency** (V1); multi-region post-StateRAMP
- **SOC 2 Type II** (M12–15); **StateRAMP Ready** (M6 3PAO)
- **Section 508 + WCAG 2.1 AA** conformance with pre-V1 usability study + VPAT at launch
- **RFC 3161 signed time** on immutable audit logs
- **SBOM (SPDX/CycloneDX) + Sigstore/cosign signed artifacts + SLSA L2 minimum** supply chain
- **RTO ≤ 4h / RPO ≤ 5min** for shared-tenant canonical memory (V1)
- **NIST AI RMF mapping:** citation envelope → MEASURE; replay-parity → MANAGE; override-in-reasoning-trail → GOVERN

### Technical Architecture Considerations (cross-cutting)

- **ReBAC over RBAC** (OpenFGA) — committed V1
- **Native OAuth over broker** — committed V1
- **Bifurcated record-of-truth** — customer-tenant artifacts vs. DeployAI observational derivatives in separately-operated stores with asymmetric retention + tombstone citation spec (see Innovation §)
- **Per-tenant canonical-memory graph** — no cross-tenant graph or retrieval at V1 (explicit scope exclusion; re-evaluate post-List-tier-GA)
- **Separate `annotation_visibility` table with distinct encryption key** for privacy-scoped overrides
- **Schema-evolution staging with Admin approval gate**
- **Per-integration kill-switch** visible in strategist UI + ops console

### Implementation Considerations

- **Build order (Anchor-sequenced):** (1) canonical memory graph + ReBAC tuples + SSO/SCIM — foundational; (2) M365 suite (cal + email + Teams transcription) — Anchor data sources; (3) voice upload + edge-capture (macOS + Windows) — capture path; (4) FOIA Export CLI (Go binary, reproducible build, Sigstore-signed) — Anchor procurement gate; (5) agent runtimes + phase-state machine (Cartographer/Oracle/Master-Strategist internal); (6) four surfaces (Digest / In-Meeting / Timeline / Phase-Tracking) + continuity-of-reference tests.
- **Defer to V1.5+ explicitly:** Google suite (unless founder uses), Zoom/Webex native transcription (upload path covers), CRM integrations, Customer Admin UI, VP CS Rollup.
- **Build for List tier at M5 (one sprint before 3PAO):** SIEM egress, continuous monitoring package, customer-owned KMS toggles for self-hosted.
- **Compliance-track parallel work:** SBOM automation + Sigstore signing in CI from day 1 (cheap if started now, expensive to retrofit); 3PAO engagement letter at M4; SOC 2 Type I scoping at M8.
- **Deployment-ops overlay specifics:** canonical memory retention defaults set to 7-year minimum; deployment-phase metadata is a required field on every event-node (not nullable); successor-handoff data model (inheritance view) is a first-class query, not a special-cased report; V1 dogfood validates the long-retention assumption with ≥6 months of accumulated NYC DOT events before Anchor ship.

### Open Confirmations (for user review at next milestone)

- **NYC DOT stack confirmation:** are NYC DOT strategists on M365/Teams + Windows (assumed)? Founder team stack?
- **FOIA CLI open-sourcing:** willing to ship the verification tool open-source? (Mary and Winston recommend yes — auditability.)
- **OpenFGA hosting:** self-hosted (recommended) vs. managed Auth0 FGA (fewer ops, adds sub-processor)?

## Project Scoping & Phased Development

**After Party Mode critique (John + Winston + Amelia), the scope is tightened, the engineering-month estimate made honest, and a resource-decision dependency is named as non-negotiable V1 gate. This section supersedes the "Product Scope" V1/V1.5/Vision framing from Step 3 where they disagree; Step 3 reflects the earlier snapshot.**

### MVP Strategy & Philosophy

**MVP approach: hybrid Experience-MVP + Problem-solving-MVP, executed via dogfood, sequenced Anchor-first.**

- Not a revenue MVP (revenue is contracted via hardware SOW).
- Not a platform MVP (cross-tenant retrieval out of scope until Phase 4).
- Experience-MVP primary: the product must feel like a coherent Living Digital Twin across V1 surfaces on day one — three-distances at V1, four at V1.5.
- Problem-solving-MVP secondary: the product must actually save founder-strategist time on the live NYC DOT engagement. The 11th-call test is the pass/fail gate.
- Dogfood as validation harness: founder is user #0; if V1 doesn't work for him, no design-partner will close.

**Anchor ship ≠ Full V1.** Two distinct gates:

- **Anchor ship (M6-8 target):** NYC DOT completes one Phase 4 → Phase 5 transition using Morning Digest + In-Meeting Alert + Phase & Task Tracking; 11th-call test passes on NYC DOT recorded traces; FOIA export produces a NIST-auditor-verifiable bundle; Section 508 VPAT is published; SSO into NYC DOT Entra tenant; compliance substrate in place. Outcome-anchored, not feature-counted.
- **Full V1 (M10-14 target):** Anchor ship + phase-state-hooks for deferred journeys (data model ready) + 6 of 8 innovation primitives live + replay-parity Spike-2 on real NYC DOT traces completed + runnable self-hosted reference build shipped.

### Resource Decision (Non-Negotiable V1 Dependency)

Amelia's reality-check, named here because the rest of the plan doesn't hold without it:

- **V1 engineering estimate (scope-as-revised):** 18–20 engineering-months of work.
- **Single-founder productive capacity:** ≈ 9 engineering-months per 12 calendar-months, after sales calls, NYC DOT support, compliance meetings, and CI friction.
- **Implication:** single-founder solo V1 in 6 calendar-months is not achievable. The plan requires one of three paths:
  - **Option A — Hire engineer #2 at M3.** Cuts calendar time to 6-9 months. Burns runway faster.
  - **Option B — Contract vCISO / compliance consultant at M1.** Offloads SOC 2 policy authoring + StateRAMP 3PAO liaison (~3-4 em of founder non-code work). Protects founder engineering attention. Still lands V1 at 12-15 calendar-months solo.
  - **Option C — Accept 12-15 calendar-month V1 solo** with vCISO contracted + aggressive de-scope + NYC DOT dogfood as validation rather than MVP-in-production from month 1.

**Path selection required before M2. If unselected at M2, the default is Option C with explicit timeline renegotiation with NYC DOT and design-partner expectation management.**

### MVP Feature Set (Phase 1 / V1)

**V1 surfaces — three, not four:**

- Morning Digest
- In-Meeting Alert
- Phase & Task Tracking

Timeline moves to V1.5. Rationale: Timeline is the triple-duty retrospection surface; building it with full continuity-of-reference is 8-12 eng-weeks of data-plane consistency work, and it is NOT blocking the Anchor Phase 4→5 transition. Presenter-mode Timeline demos for founder-CEO conversations can be satisfied at V1 via pre-generated exports from canonical memory (a tool, not a live surface).

**V1 agents — three, two active:**

- Cartographer (passive extraction) — active V1
- Oracle (retrieval / digest / in-meeting alerts) — active V1
- Master Strategist (internal-only arbitration) — active V1 with no user-facing UI

**V1 canonical memory:** immutable event log + time-versioned identity graph + solidified-learning library + Action Queue (V1 lightweight schema per Domain Requirements §12) + User Validation Queue.

**V1 phase-state machine:** 7-phase DeployAI Framework, agent-proposed + human-confirmed transitions.

**V1 capture paths (Anchor-sequenced, one-OS edge-capture):**

- M365 Calendar (Microsoft Graph)
- Exchange / M365 Email (Microsoft Graph)
- Microsoft Teams transcription import
- Voice / meeting upload (direct file, no bot-join)
- On-device edge-capture: **ONE OS at V1** — either macOS OR Windows, chosen to match the primary dogfood user's stack (founder + NYC DOT strategist). **Open confirmation pending** (see §Open Confirmations). Second OS ships V1.5.
- FOIA Export CLI (Go binary, Sigstore-signed, reproducible build, customer-machine execution)

**V1 identity & access:**

- SAML/OIDC SSO + SCIM provisioning (Entra ID primary) — Anchor-blocking
- **Authorization: Postgres Row-Level Security with documented ReBAC migration plan** — OpenFGA ReBAC migration deferred to Design-Partner gate or List-tier gate, whichever comes first. Migration cost accepted as a later V1.5 / V2 investment rather than a V1 tax. Rationale: ReBAC is the right long-term answer for successor-inheritance + privacy-scoped overrides, but the access patterns benefit from dogfood-validation before authz-model crystallization. Postgres RLS + a 3-month migration window is acceptable; committing to OpenFGA at V1 without validated access patterns risks the authz-model rewrite Amelia flagged. Step 7 of this PRD names OpenFGA; this section supersedes that commitment.
- Per-integration kill-switch (strategist UI + ops console)

**V1 compliance substrate:**

- FIPS 140-2 validated KMS
- RFC 3161 signed time on immutable audit log
- Bifurcated record-of-truth + tombstone citations
- FOIA Export CLI (open-source, Sigstore-signed)
- Section 508 + WCAG 2.1 AA — VPAT published at launch; SR-user study at M3 post-ship (not V1)
- Day-1 cheap compliance-track parallel work: SBOM automation (syft in CI), Sigstore signing, dependency scanning, audit log retention policies

**V1 innovation primitives (6 of 8 at V1; 2 deferred to V1.5):**

1. Falsifiable Citation Contract — V1 (11th-call test as CI gate with synthetic bridge at week 6 → real NYC DOT traces at month 3-4)
2. Phase-Gated Retrieval with Explicit Scoring — V1
3. Four-Distances Living Digital Twin — **ships as "Three-Distances at V1, expanding to Four at V1.5"** when Timeline ships
4. Three-Tier Replay-Parity Adjudication — V1 with **manual** gate-report; **automated** adjudication at V1.5. Two-pass spike: Spike-1 at weeks 8-10 on Llama 3→3.1 / HotpotQA public benchmark (before agent runtime design); Spike-2 at month 4 on real NYC DOT traces.
5. Two-Door Override (live-correction + retrospective override) — V1
6. Pull-Primary In-Meeting Alert — **V1 ships as push-notification-with-persistent-card** (lower-right reserved region, no sound/motion, glyph ≤8s). Pull-primary inversion at V1.5 once baseline attention-rate data exists.
7. Tiered Solidification — **V1 ships 2 tiers** (Class A auto-solidify + Class B review queue). Class C noise-suppression classifier at V1.5.
8. Accessibility-Primary Equivalence — **reframed at V1 as "accessibility-primary across V1 surfaces (Digest + In-Meeting + Phase-Tracking)"**; accessibility-primary Timeline moves with Timeline to V1.5. VPAT at launch covers V1 surfaces.

**V1 test rigor:**

- ≥95% coverage on deterministic paths
- 11th-call test CI gate (synthetic bridge at week 6 → real traces month 3-4)
- Continuity contract tests across V1 surfaces (three-distances at V1, scales to four at V1.5)
- Phase-retrieval audit matrix
- Replay-parity suite (manual V1, automated V1.5)

**V1 documentation (three, not five):**

- Glossary
- Compliance-Architecture Brief (three diagrams: bifurcation, standards→certifications, evidence lifecycle)
- VPAT

Data-Sharing Contract Shape and FOIA Export Runbook slip to M4.

**V1 journeys actively supported (UI active, tested):** 7 of 10 core journeys — Morning Digest, In-Meeting Alert, Phase & Task Tracking, Learning Solidification, Override with Evidence (retrospective), Replay-Parity Gate (compliance packet), Customer Offboarding Cascade. Three journeys have phase-state hooks + data model ready but no active UIs at V1: Inherited Account Onboarding, Trust Repair with successor-inheritance, VP CS Rollup. Accessibility-primary variant (Journey 4a) applies to all V1-active UIs.

### Phase 2 (V1.5)

**Trigger (primary):** NYC DOT moves past Phase 4 (User Training) into Phase 5 (Value Creation). Evidence-based trigger indicating the Anchor works.

**Trigger (secondary):** First design-partner close. Commercial signal.

**V1.5 additions:**

- Timeline (fourth distance of the Living Digital Twin) + accessibility-primary Timeline
- Multi-owner Action Queue + delegation UI + full work-session UX (parallel `assignees` join table already forward-compat per Domain §12)
- VP Customer Success Rollup — active role + cross-account read-only aggregate
- Customer Admin role + self-serve user management (ship before second List-tier close)
- Inherited Account Onboarding — active users + inheritance-view polish
- Master Strategist UI surfacing — negotiation visibility, arbitration reasoning trails
- Second-OS edge-capture (whichever wasn't chosen at V1)
- Additional capture integrations: Google Calendar + Gmail (if not at V1), Zoom transcription, Webex transcription
- CRM integrations: Salesforce, HubSpot, Pipedrive, Attio
- **ReBAC migration (Postgres RLS → OpenFGA, Auth0 FGA managed first 6 months → self-host)** — gated on Design-Partner close or List-tier commitment
- Innovation completions: pull-primary In-Meeting inversion, Class-C tiered-solidification, automated replay-parity gate-report, accessibility-primary Timeline
- Cross-ACCOUNT (one vendor across their own customer portfolio) pattern retrieval — single-tenant, low-architectural-risk
- Documentation completion: Data-Sharing Contract Shape, FOIA Export Runbook
- SR-user study (innovation #8 completion)

### Phase 3 (List Tier & Expansion — M6+, post-StateRAMP Ready)

**Gated by:** StateRAMP Ready 3PAO certification (calendar-math-corrected: engagement letter M0 → Ready M6; if engagement at M4, Ready M10-11 — **adjust M6 target if engagement slips**) + SOC 2 Type II (M12-15).

- SIEM egress: push (syslog/CEF/OCSF) + pull-API fallback with 72h replay buffer
- Customer-owned KMS (BYOK/HSM) for self-hosted; managed-KMS with customer audit for shared-tenant
- Self-hosted reference build integration parity closed to 🟢 where possible (was 4-6 eng-weeks at month 5 for initial runnable build)
- Continuous-monitoring package: real-time compliance evidence dashboard, customer-visible control status
- Cooperative-purchasing expansion: NASPO ValuePoint, state-specific SIEM/SSO integrations
- Slack digest delivery + ServiceNow workflow hook

### Phase 4 (Vision — 24+ months)

- Multi-region data residency (post-StateRAMP)
- FedRAMP Moderate (trigger: first federal customer)
- Cleared-federal path (ITAR/EAR conditional — Domain §4)
- **Cross-TENANT pattern-mining (distinct from cross-account)** — requires consent framework design, DPA changes, likely differential privacy implementation. Product+legal decision, not just engineering
- Published DeployAI Deployment Framework adoption target: ≥3 external deployment-strategist reviewers using framework independently within 18 months of publication
- Deployment ops as a named category: Gartner coverage, budget-line recognition, third-party training economy

### Build Sequence (Winston's strict ordering, weeks 1-24)

**Weeks 1-3: Canonical memory schema + append-only immutable event log.**

**Weeks 3-5: Authorization layer (Postgres RLS at V1 per resource-decision rationale; tuple-model documented for ReBAC migration).** Overlap with weeks 3 permitted only after memory schema is stable.

**Weeks 5-6: SSO/SCIM (Entra ID).** Strictly last within foundational bucket — depends on tenant + authz model.

**Weeks 6: `fixtures/synthetic-call-11.json` authored** — hand-crafted DOT-flavored 10-call seed + 11th-call held-out for CI gate. Gate runs against synthetic from day 1.

**Weeks 7-8: M365 suite (Graph API): Calendar + Email + Teams transcription import.** OAuth client per provider, batched with delta queries + per-user token pools (Winston's throttling mitigation).

**Weeks 8-10: Replay-parity Spike-1** on Llama 3→3.1 / HotpotQA public benchmark to validate citation-set-identical semantics BEFORE agent runtimes. Spike outcome determines retrieval contract.

**Weeks 10-14: Cartographer + Oracle agent runtimes** built to the retrieval contract from Spike-1.

**Weeks 14-16: 7-phase state machine + Master Strategist (internal arbitration).**

**Weeks 16-20: Three V1 surfaces (Digest + In-Meeting Alert + Phase-Tracking) with continuity-of-reference contract tests.**

**Weeks 18-22: On-device edge-capture agent (one OS, matched to founder stack). Auto-update mechanism (Sparkle for macOS or Squirrel for Windows), Sigstore-signed, kill-switch tuple.** Parallel with surfaces — different engineer if Option A resourcing, otherwise sequential.

**Month 4: Replay-parity Spike-2** on accumulated NYC DOT traces (≥40 real calls expected). Swap synthetic 11th-call fixture for real. If Spike-1 semantics held, lock; if not, publicly downgrade to citation-superset.

**Month 5: Self-hosted reference build** (docker-compose + Helm chart, 4-6 eng-weeks, runnable with integration parity declared).

**Month 6: FOIA Export CLI + Section 508 VPAT + Anchor ship readiness.**

**Month 6+: Compliance-track acceleration** — SOC 2 Type I scoping, 3PAO engagement, continuous-monitoring setup. StateRAMP Ready calendar-math honest: Ready designation lags engagement by 6-7 months.

### Risk Mitigation Strategy (updated)

**Technical risks:**

- **Replay-parity semantics uncertainty** — two-pass spike (Spike-1 public benchmark weeks 8-10, Spike-2 NYC DOT month 4); public downgrade to citation-superset if Spike-1 fails citation-set-identical
- **11th-call test corpus dependency** — synthetic bridge fixture at week 6; swap for real at month 3-4; next-call-in-chronology criterion; multiple 11th-calls over engagement
- **Continuity-of-reference staleness** — staleness SLO per surface; "memory syncing" glyph graceful degradation
- **Authz availability (post-ReBAC migration)** — authz-cache + fail-closed mode
- **Edge-capture binary distribution** — auto-update via Sparkle/Squirrel, Sigstore-signed, kill-switch tuple, crash telemetry, rollback path
- **Microsoft Graph API throttling** — batched + delta queries + per-user token pools

**Market risks:**

- **Dogfood-window closure** (founder attention scales away): time-boxed dogfood window, re-calibration cadence published
- **Pricing anchor re-anchoring** (design-partner closes reset List comp): pricing-validation documented; List comp justified from independent evidence
- **Framework non-adoption** — seed 2-3 non-DeployAI users at publication; 18-month adoption check
- **Category-creation failure** — Gainsight-2011 analog; success predicted by lighthouse + framework + 3-5 reference deployments in 24 months
- **Integration catalog perception** (Gong has 100+) — positioning: "FOIA-bound and security-reviewed integrations municipal buyers actually use; bot-join sprawl is what benched incumbents"

**Resource risks:**

- **Single-founder engineering bandwidth** — explicit resource-path decision required by M2 (Option A/B/C above); default Option C with timeline renegotiation
- **Compliance-track resourcing** — vCISO contracted M1 (Option A or B); SOC 2 Type I scoping M8; 3PAO engagement M4 (with M10-11 Ready if M4 engagement, not M6)
- **Documentation resource collision** — three V1 docs (Glossary + Compliance Brief + VPAT); two deferred to M4; founder-quality writing time budgeted or Paige staffed at M2
- **Hidden OAuth integration maintenance tail** — ~0.5 em/year per integration; seven V1 integrations = 3.5 em/year ongoing baseline; factor into post-V1 resourcing

### Scope Cut-List Under Resource Slip (genuine cuts, in order)

If resource path is Option C and timeline pressure exceeds capacity, cuts in this order:

1. Innovation #6 pull-primary → remains push-with-persistent-card through V1.5
2. Innovation #7 Class C → remains 2-tier through V2
3. Replay-parity gate-report → manual-only through V1.5
4. Master Strategist internal arbitration → stub (Oracle picks top-3 without arbitration) through V1.5
5. Phase & Task Tracking → collapses into Digest phase-header + Action Queue list (no dedicated surface) through V1.5
6. Self-hosted reference runnable build → deferred to M9-10 from M5

### Open Confirmations (for user review at next milestone)

- NYC DOT stack: M365/Teams + Windows (Mary assumed) — confirm
- Founder stack: macOS or Windows — confirm (determines V1 edge-capture OS)
- Resource path (A / B / C) — decide by M2
- FOIA CLI open-sourcing — confirm (Mary + Winston recommend yes for auditability)
- OpenFGA deferral accepted — confirm (this section supersedes Step 7 commitment)

## Design Philosophy & Non-Negotiable Commitments

This section captures qualitative design commitments that govern how DeployAI's capabilities FEEL to end-users and how agents are permitted to BEHAVE, distinct from the capability contract (§Functional Requirements) and the quality attributes (§Non-Functional Requirements). These commitments originate in the brainstorming session's Key Design Commitments list and are binding on UX design, agent-prompt construction, and every downstream product surface. Violating any of these invalidates the differentiator even when FRs and NFRs are technically satisfied.

### DP1. Senior-Strategist Mindset as Agent Design Constraint

Every agent output — Cartographer's extraction, Oracle's surfacing, Master Strategist's ranking — is constructed as if reviewed by a senior deployment strategist. The test: would an experienced strategist find this output useful, non-condescending, and non-obvious? Agents are not tutors and not coaches; they are peers whose value comes from substrate depth (what no human can hold in memory across 11 months of deployment) not from pedagogy. Output voice is peer-level, not instructive.

### DP2. Surfaces Evidence and Named Patterns — Does Not Script

Oracle surfaces *what is known*: cited facts, solidified learnings, named patterns from the evidence. Oracle does NOT generate the strategist's meeting language, prescribe exact phrasing, or offer "say this" coaching. The strategist owns the conversation; Oracle owns the memory. In-meeting alerts reference the learning ("data-ops liaisons prefer async for schedule changes"), not the utterance ("you should tell them to email instead"). Prescriptive phrasing is architecturally excluded from agent outputs.

### DP3. Symbiotic Posture — Surface, Don't Authorize

Agents propose; humans authorize. Above-confidence-threshold extractions auto-commit to canonical memory; below-threshold outputs queue for human validation. No agent-initiated action has customer-visible consequence without human confirmation. Phase transitions are agent-proposed, human-confirmed. Action Queue items are agent-ranked, human-executed. This posture is violated by any feature that lets an agent unilaterally act on external systems, customer data, or user-facing communication.

### DP4. Teammate Hand-Off Is the Test of Knowledge Relay

The canonical memory substrate is validated by the successor scenario: a second strategist, with zero prior exposure to the account, should be able to pick up the account using only the memory substrate and perform competently within days. If the substrate cannot support this handoff, the substrate is incomplete. This test governs what counts as "solidified" (must be teammate-legible, not operator-internal shorthand) and what citation envelopes must include (why-now trace, not just evidence pointer). Journey 4 (Inherited Account Day 1) is the operationalized form of this commitment.

### DP5. Learning-Card Never Paraphrases the Trigger Utterance

When Oracle's In-Meeting Alert fires, the learning card shows the *learning* (the belief, evidence, and phase-tuned confidence) — NOT a summary of what the stakeholder just said that triggered the alert. The strategist is already in the conversation; they do not need to be told what was said. Paraphrasing the trigger adds cognitive load and signals coaching intent (violating DP2). Trigger detection is invisible; learning retrieval is visible.

### DP6. Retrieval-Only In-Meeting; Generation Only in Evening Synthesis with Human Gate

During live meetings, agents operate in retrieval-only, solidified-only, private-only mode. No new claims are generated during meetings. New claim generation — candidate learnings, pattern proposals, phase-transition proposals — occurs only in Evening Synthesis, with a human gate on high-impact candidates (Class B review queue). This separation enforces the correctness boundary between "what we already know, retrieved" and "what might be true, proposed."

### DP7. Documentation Is Part of the Product

Agent logic docs, surface docs, Deployment Framework walkthrough, scope manifest, ingestion docs, Compliance-Architecture Brief, VPAT, Glossary, and Ranking Spec are all first-class product deliverables shipped alongside code. Documentation is versioned, schema-tested where possible, and treated as evidence of the substrate — not as marketing. See §V1 Documentation Deliverables in Domain Requirements.

### DP8. Real Data Dictates Real Design — Don't Over-Engineer

V1 is intentionally under-architected in areas where real deployment data will force revision. Open questions (ranker weights, phase-tuned confidence floors, tier-promotion thresholds, silence calibration defaults, weekly-review cadence) use educated defaults in V1 and are calibrated from NYC DOT deployment signal in the first quarter post-launch. Architecture for scale DOES NOT precede evidence of scale. This commitment is the reason the PRD explicitly defers the Timeline surface, Blocker-as-separate-agent, cross-corpus statistical promotion, and advanced User Validation Queue workflows to post-V1.

### DP9. Third Bin: Proposals and Hypotheses Are Retained as Signal

Agent-generated candidate learnings that are neither confirmed nor rejected are NOT discarded — they live in a third bin (Class B weekly review queue at V1, expanded classifier at V1.5) as retained signal. This bin feeds future solidification when additional evidence accrues and feeds the "what I ranked out" footer in digests. Discarding unconfirmed proposals is a silent information loss; retaining them with provenance preserves the adaptive-learning loop.

### DP10. Master Strategist Is an Integration Layer, Not a UI Surface (V1)

At V1, Master Strategist coordinates agent proposals, arbitrates conflicts, and ranks the Action Queue — all internally. No user-facing UI surface for Master Strategist's reasoning trace at V1. This commitment prevents premature UI on internal mechanics that real deployment signal may invalidate. V1.5+ may expose surface if dogfood evidence warrants.

### DP11. Person = Stable Identity with Time-Versioned Attributes

A person retains a single canonical identity across role changes, title changes, email changes, organization changes. Attribute history is tracked as time-versioned evolution, not as duplicate-entity fragmentation. Citation resolution across time uses supersession-aware lookup: "who was Director of X at as-of-timestamp T" resolves to the correct person even if that person later became VP of Y. This commitment is embedded in FR2 and FR3 but governs how Cartographer thinks about identity broadly.

### DP12. Not-to-Build: Competitive Intelligence, External-Threat Mapping, Autonomous Action

DeployAI is a deployment strategist tool. It is NOT a competitive intelligence platform, NOT an external-threat mapper, NOT an autonomous agent acting on external systems. No feature that crosses into these categories ships at any phase. This is a permanent scope boundary, not a V1 deferral. The founder's own deployment experience (NYC DOT) dictates the category; competitive/threat work is a different product with different ethical posture.

---

These twelve commitments are referenced by downstream PRD sections (§Functional Requirements, §Non-Functional Requirements) and will be re-referenced by UX Design and Architecture specifications. They are immutable without explicit brainstorming revisit.

## Functional Requirements

**This section is the capability contract.** UX designers will only design what's listed here; architects will only support what's listed here; epics and stories will only implement what's listed here. Capabilities not listed here will not exist in the final product.

Organized by eight capability areas. Actors named explicitly throughout (no bare "System"):

- **Deployment Strategist** (primary user)
- **Successor Strategist** (V1.5-active)
- **Platform Admin** (DeployAI internal)
- **Customer Records Officer** (no login — CLI user)
- **External Auditor** (JIT scoped)
- **Customer Admin** (V1.5-active)
- **Customer** (entity — SSO provisioner)
- **Cartographer / Oracle / Master Strategist** (agents)
- **Data Plane / Control Plane / Edge Agent / CI Pipeline** (internal system components)

Legend: V1 (default), `[V1.5]`, `[List tier]` where tier-gated.

### Memory & Canonical Record

- **FR1:** Data Plane captures every ingested event (email, meeting transcript, calendar entry, voice/meeting upload, field note, agent output, user override) as an immutable append-only event node with a signed timestamp from a trusted authority.
- **FR2:** Data Plane maintains a time-versioned identity graph where a person retains a stable identity across role or attribute changes, with evolving attributes tracked as history and not overwritten.
- **FR3:** Data Plane resolves duplicate identity candidates (same person, alternate roles or aliases) to a single canonical identity with supersession-aware citation resolution across time.
- **FR4:** Data Plane maintains a solidified-learning library where learnings are structured as {Belief, Evidence, Application Trigger} with lifecycle states (candidate, solidified, overridden, tombstoned).
- **FR5:** Data Plane emits a tombstone record sufficient to preserve citation integrity and auditability when underlying evidence is destroyed under retention contract. (Tombstone schema specified in Domain §5 and Innovation §.)
- **FR6:** Data Plane resolves any citation deep-link to the exact evidence-set available at the time the cited claim was made (as-of-timestamp resolution), not merely current evidence.
- **FR7:** Data Plane enforces bifurcated record-of-truth across separate failure domains and separate operational control planes — customer-tenant artifacts and DeployAI observational derivatives are never co-resident in the same data-plane instance.
- **FR8:** Control Plane enforces retention contracts on schedule — scheduled retention jobs execute per-tenant retention policy, emit audit events on destruction, and produce tombstones per FR5.

### Capture & Ingestion

- **FR9:** Deployment Strategist can ingest calendar events from Microsoft 365 Calendar via authenticated OAuth.
- **FR10:** Deployment Strategist can ingest email from Exchange / M365 via authenticated OAuth.
- **FR11:** Deployment Strategist can import Microsoft Teams meeting transcripts.
- **FR12:** Deployment Strategist can upload voice or meeting recording files directly; capture occurs at the endpoint with no server-side meeting-join, no bot-join capture, and no cloud-hosted recording intermediary in the data path.
- **FR13:** Deployment Strategist can capture on-device via a signed Edge Agent binary (one OS at V1, second at V1.5) that produces tamper-evident local transcripts verifiable without the authoring agent.
- **FR14:** Platform Admin can remotely disable any deployed Edge Agent binary via a kill-switch that revokes trust and halts capture.
- **FR15:** Cartographer performs mission-relevance triage before extraction, where "mission" is defined as the account's active deployment phase plus declared objectives; relevance is computed by Cartographer, not declared by user.
- **FR16:** Cartographer treats the email thread or meeting session as the unit of extraction, not individual messages.
- **FR17:** Deployment Strategist or Platform Admin can toggle any integration's kill-switch, revoking the integration's access token, purging in-flight queue, and emitting an audit event.
- **FR18:** Data Plane tolerates transient upstream failures on integration pulls with bounded-retry and idempotent-write semantics; duplicate deliveries produce at-most-once canonical events.
- **FR19:** Data Plane applies throttling-aware backpressure on upstream integration pulls, batching and respecting provider rate limits (e.g., Microsoft Graph throttling) without data loss.

### Intelligence, Retrieval & Phase Management

- **FR20:** Cartographer extracts entities, relationships, blockers, and candidate learnings from captured events, grounded exclusively in canonical memory with no external inference.
- **FR21:** Oracle surfaces phase-appropriate suggestions via proactive Morning Digest, reactive In-Meeting Alert, and reflective Evening Synthesis.
- **FR22:** Oracle ranks candidate surface items by contextual fit to the account's current deployment phase and available evidence (specific signal weighting specified in the Ranking Spec appendix; the contextual-fit capability is the FR-level contract) and enforces a 3-item hard budget on In-Meeting Alerts.
- **FR23:** Oracle suppresses phase-inappropriate suggestions; at phase-ambiguity (defined in Glossary — account state that qualifies for multiple phases under the 7-phase framework), Oracle returns a union of phase-eligible results with phase labels attached rather than guessing.
- **FR24:** Oracle renders a Corpus-Confidence Marker, displays Null-Result Retrieval explicitly when no phase-appropriate learnings exist, and appends a "What I Ranked Out" footer naming suppressed candidates.
- **FR25:** Oracle surfaces named patterns as suggestions only; no action is auto-executed on the user's behalf without explicit confirmation.
- **FR26:** Master Strategist arbitrates agent proposals, ranks the Action Queue, escalates low-confidence items to the User Validation Queue, and proposes phase transitions (V1: internal-only, no user-facing UI; V1.5+: UI surfaced).
- **FR27:** Each agent output carries a citation envelope with {node_id, graph_epoch, evidence_span, retrieval_phase, confidence_score, signed_timestamp}; outputs lacking required envelope fields are rejected at the agent boundary by the Control Plane and not emitted to the user.
- **FR28:** Control Plane enforces a tiered solidification classifier — V1: two tiers (Class A auto-solidify for high-confidence structured-source extractions; Class B weekly review queue for medium-confidence pattern extractions). `[V1.5]` Class C noise-suppression classifier added.
- **FR29:** Deployment Strategist can manually promote or demote learnings between solidification classes.
- **FR30:** Control Plane tracks each account's current deployment phase across the seven phases of the DeployAI Deployment Framework (Pre-sale/Scoping, Preparation, Integration/Data Collection, User Training, Value Creation, Preparing for Expansion, Expansion).
- **FR31:** Cartographer or Oracle proposes phase transitions with evidence; Deployment Strategist confirms or rejects with reason.
- **FR32:** Control Plane modulates retrieval ranking, digest priorities, and alert confidence thresholds based on current phase context.
- **FR33:** Deployment Strategist reviews items in the User Validation Queue and confirms, modifies, or rejects each with a reason string that feeds agent re-ranking.

### User Surfaces

- **FR34:** Deployment Strategist receives a Morning Digest at start-of-day containing phase-contextualized priorities, delivered with emotional pacing (signal-dense without cognitive overload) and a hard-capped 3-item top-of-digest format with a "What I Ranked Out" footer.
- **FR35:** Deployment Strategist receives an Evening Synthesis surface at end-of-day, parallel to Morning Digest — backward-looking reconciliation of the day's captured events, solidification candidates surfaced from the Class B queue, and any cross-account patterns.
- **FR36:** Deployment Strategist receives an In-Meeting Alert as a persistent-card notification rendered within 8 seconds of agent trigger, with lazy-loaded citation payload that loads asynchronously after glyph render.
- **FR37:** In-Meeting Alert architecturally separates correction from dismissal as non-confusable actions; correction and dismissal error-rate under timed conditions is measurable and gated in usability testing (0 silent-mislearning events on the validation protocol).
- **FR38:** Alert items not attended during a meeting persist as Action Queue items post-meeting rather than silently expiring.
- **FR39:** Deployment Strategist views Phase & Task Tracking showing current deployment phase, phase-required tasks, outstanding blockers, pending Action Queue items, and (for V1.5-active inherited accounts) inheritance status per account.
- **FR40:** `[V1.5]` Deployment Strategist views a Timeline surface showing account history at week-level zoom with landmark-bloom annotations and presenter-mode for demo contexts.
- **FR41:** Any citation clicked in any surface resolves to the same canonical-memory node across all active surfaces (continuity-of-reference guarantee); node identity resolves identically across surfaces within a session; visual token treatment remains stable across navigation. Citation resolution default is expand-inline with an explicit "navigate to source" option; citations never force a surface switch unless requested.
- **FR42:** All active surfaces preserve context-neighborhood continuity — the relationship context surrounding a cited node (stakeholder peers, active blockers, recent events) is the same set on each surface, minus explicit zoom-level collapses documented in the UX spec.
- **FR43:** All active surfaces present node chips, confidence affordances, evidence icons, and resolved/overridden state markers using a shared visual token set such that a node renders consistently across surfaces.
- **FR44:** All active surfaces support keyboard and screen-reader navigation with task-completion parity on the top-N user journeys (not subjective equivalence), conforming to WCAG 2.1 AA as a floor; screen-reader-primary is a first-class design target; accessibility is a11y-first in the design process, not retrofit.
- **FR45:** All active surfaces present an explicit empty state (pre-ingestion, new-account onboarding, post-offboarding) with a clear next-step affordance.
- **FR46:** All active surfaces degrade gracefully when Cartographer, Oracle, or Master Strategist fails — agent-error state is explicit (not silent), with a user-visible retry affordance and a fallback to canonical-memory-only rendering where possible.
- **FR47:** All active surfaces indicate ingestion-in-progress state during long extraction (e.g., multi-message thread processing) with progress signaling.
- **FR48:** All active surfaces render a memory-syncing glyph when staleness exceeds the per-surface SLO, rather than showing stale state as current.

### Override & Trust Management

- **FR49:** Deployment Strategist can retrospectively override a solidified learning by attaching new evidence and a reason string.
- **FR50:** Override events are recorded as first-class entries in the canonical memory event log carrying {override_id, user_id, learning_id, override_evidence_event_ids, reason_string, timestamp}.
- **FR51:** Future agent reasoning trails that cite an overridden learning surface an override-applied sub-citation linking to the override event.
- **FR52:** Deployment Strategist can attach private-scope annotations to their own overrides; private annotations are not visible to Successor Strategists inheriting the account.
- **FR53:** Deployment Strategist can reject or defer an Action Queue item; rejection with reason and deferral with reason are both captured and feed Oracle re-ranking.
- **FR54:** Deployment Strategist views an override review-history surface showing their own overrides and non-private overrides by others on accounts they have access to — distinct from personal-audit view, scoped to override events only.
- **FR55:** Oracle surfaces a trust-earn-back confidence cue on subsequent surfaces citing a corrected learning, explicitly signaling that the system has applied the prior override to current reasoning.

### Action Queue Lifecycle

- **FR56:** Deployment Strategist can claim an Action Queue item (assign-to-self).
- **FR57:** Deployment Strategist can mark an Action Queue item in-progress.
- **FR58:** Deployment Strategist can resolve an Action Queue item with a resolution state from the allowed set ({resolved, deferred, rejected_with_reason}) and can link resolution evidence (canonical-memory event IDs) to the resolved item.
- **FR59:** Deployment Strategist views the User Validation Queue and the Solidification Review Queue as dedicated surfaces with promote/demote/defer actions; these are distinct from the Action Queue and Digest.

### Compliance, Evidence, Security & Audit

- **FR60:** Customer Records Officer produces a timestamped, cryptographically-verifiable FOIA export of all customer-tenant records for a specified account and date range via an open-source signed CLI, without engineering support.
- **FR61:** Any third-party verifier can validate the signature and chain-of-custody of a FOIA export bundle using only the open-source CLI and public trust-authority keys.
- **FR62:** CI Pipeline enforces a replay-parity suite on every LLM model-version upgrade, adjudicating divergent citation sets via a rule-based → LLM-judge → human cascade. Escalation triggers: (a) rule-based auto-approves if new citation-set is a strict superset of old or all differing citations have strictly-higher phase-affinity score; (b) rule-based escalates to LLM-judge when diffs are not rule-decidable; (c) LLM-judge escalates to human when LLM-judge disagrees with rule-layer.
- **FR63:** Control Plane produces a quarterly customer-visible Replay-Parity Gate Report naming false-regression-rate, false-acceptance-rate, and human-disagreement-rate.
- **FR64:** Platform Admin tenant-data access exists as a privileged override capability that is multi-party-authorized, fully audited, time-boxed, and customer-notified before session opens with an explicit objection window. (Exact procedure and timing thresholds in operations runbook, per Domain §5.)
- **FR65:** External Auditor (3PAO / SOC 2) is granted just-in-time, time-bounded, read-only access to audit log and controls evidence bucket only, with watermarked exports and no canonical memory access.
- **FR66:** Deployment Strategist views a personal audit surface showing their own overrides, actions, corrections, and integration kill-switch toggles on accounts they have access to — distinct from admin audit-log access (FR64-65).
- **FR67:** `[List tier, V1.5]` Customer IT/Security consumes customer-owned SIEM egress from DeployAI (syslog/CEF/OCSF push + pull-API fallback with 72-hour replay buffer).
- **FR68:** Control Plane emits operational metrics, distributed traces, and structured audit logs sufficient for internal incident response, third-party audit, and customer transparency requirements.
- **FR69:** Data Plane supports backup and disaster-recovery operations meeting RPO ≤ 5 min and RTO ≤ 4 hr for shared-tenant canonical memory per Domain §5.

### Identity, Tenancy, Access & Provisioning

- **FR70:** Platform Admin provisions a new account, assigns the initial Deployment Strategist, and establishes an empty canonical memory baseline with tenant-scoped encryption context.
- **FR71:** Customer can provision DeployAI users via SAML/OIDC single sign-on (Entra ID primary at V1) and SCIM provisioning.
- **FR72:** Data Plane enforces tenant isolation via a per-tenant-keyed datastore with no shared canonical-memory instance at V1 — cross-tenant canonical-memory reads are architecturally impossible because no shared read path exists. `[V1.5]` Cross-account queries within a single tenant (one vendor across their own customer portfolio) are supported.
- **FR73:** Deployment Strategist's authorization is tenant-scoped; the same role type governs Anchor, Design-Partner, Successor, and future List-tier strategists across their respective tenants.
- **FR74:** `[V1.5]` Successor Strategist inherits an account's canonical memory, Action Queue, and public-scope annotations on assignment but cannot read predecessor's private-scope annotations (data model ships V1; active role V1.5).
- **FR75:** `[V1.5]` Platform Admin assigns a Successor Strategist to an inherited account, triggering the Inherited Account Onboarding flow per Journey 8.
- **FR76:** Platform Admin approves or rejects Cartographer-proposed schema evolutions; Cartographer writes proposed new fields to a staging area until Platform Admin promotes them to the canonical schema.
- **FR77:** `[V1.5]` Customer Admin can manage their own organization's DeployAI users (add, remove, re-assign) without DeployAI CS involvement — placeholder capability acknowledged at V1 so the tenancy model supports it.
- **FR78:** Data Plane supports a reference self-hosted deployment topology with customer-owned key management (BYOK/HSM) for enterprise customers at the List tier.
- **FR79:** Control Plane produces a procurement-package artifact set on demand (line-item pricing breakdown, standards-conformance summary, vendor-security documentation, data-sharing contract shape draft) supporting Sourcewell cooperative-purchasing primary path per Domain §6.

### Deferred to Epic 0 / Launch Checklist (NOT FRs)

Previously drafted as FRs but reclassified per John's scope-discipline review — these are delivery commitments, not product capabilities:

- Publish canonical documentation artifacts at V1 (Glossary, Compliance-Architecture Brief with three named diagrams, VPAT). Data-Sharing Contract Shape and FOIA Export Runbook by M4.
- Publish the DeployAI Deployment Framework as an open methodology artifact.

These deliverables are tracked in the launch checklist and referenced by the compliance matrix; they are not user-facing capabilities and will not appear in UX designs or architecture diagrams.

### Deferred to NFRs (Step 10)

Previously drafted as FRs but reclassified per Winston's altitude review:

- **CI Pipeline runs the 11th-call test** on every merge to main gating releases (verification/release NFR).
- **Shared-tenant SaaS operates in a single US region at V1** (deployment-constraint NFR).

## Non-Functional Requirements

NFRs define HOW WELL the system must perform the capabilities in §Functional Requirements. Each NFR is specific, measurable, and testable, organized across ten categories. Following Party Mode review (Winston + Amelia + Paige), this section opens with **measurement conventions** so every percentile, threshold, and scope term has a single interpretation. Thresholds are calibrated to V1 capacity (single-founder-or-small-team build, 18–20 engineering-month envelope) with staged uplift at StateRAMP Ready (M6+) and post-StateRAMP (M12+). **Full glossary of undefined terms will be drafted in §Polish (Step 11).**

**Numbering:** NFR1–NFR78. FR↔NFR traceability listed where an NFR binds to specific FRs or domain commitments.

### Measurement Conventions (apply to all NFRs)

- **Percentile windows.** All `p95` / `p99` metrics are measured over a **rolling 7-day window** of production requests, excluding synthetic probes, unless an NFR states otherwise. All `monthly` metrics use **calendar month UTC**.
- **Scope terms.** `Account` = billing entity (one customer deployment). `Tenant` = isolation boundary (one account-or-multi-account per customer, per customer contract). `Customer` = account's designated point of contact for security, billing, and escalation. `Strategist` = end-user inside an account (Deployment Strategist role).
- **Latency origins (t₀ table).** Clock starts at the following events:
  - *In-Meeting Alert glyph render* (NFR1): from Oracle's **decision-to-surface** timestamp (post-retrieval, pre-render).
  - *Morning Digest delivery* (NFR2): from scheduled digest-generation-job start.
  - *Evening Synthesis delivery* (NFR3): from scheduled synthesis-job start.
  - *Citation resolution inline-expand* (NFR4): from user-click event receipt at frontend.
  - *Surface staleness ceilings* (NFR5): per-surface — Digest: from last-ingested-event-commit to canonical memory; In-Meeting: from transcript-caption receipt at ingest boundary; Phase & Task Tracking: from upstream-provider-notification receipt; Timeline (V1.5): from last-ingested-event-commit.
  - *Cartographer end-to-end* (NFR48): from ingest-boundary commit (upload-complete or provider-push acknowledged) to extraction-outputs-written to canonical memory.
  - *FOIA export* (NFR7): from CLI-authorization-complete to signed-bundle-available.
  - *Kill-switch* (NFR24): from toggle-event-receipt at Control Plane backend.
- **Severity taxonomy** (used in NFR60/61): **Sev-1** = customer-visible platform outage or data-loss risk; **Sev-2** = correctness or compliance regression (e.g., citation accuracy, phase-gate failure); **Sev-3** = single-user-visible surface degradation; **Sev-4** = internal observability regression. Full runbook in Step 11 polish.
- **"Up" definition** (for NFR10 availability): successful responses to three synthetic probes — Digest generation, In-Meeting alert delivery, Phase-Tracking surface read — measured every 60 seconds. Excluded: pre-announced maintenance windows ≥72h notice, customer-side network issues, upstream LLM provider outages (governed separately by NFR70).

### Performance & Responsiveness

- **NFR1: In-Meeting Alert glyph-render latency.** Oracle's In-Meeting Alert glyph renders ≤ 8 seconds (p95) from agent decision-to-surface, measured under nominal load (≥ 50 concurrent accounts and ≥ 20 in-progress meetings per shared-tenant instance). Lazy-loaded citation payload may arrive asynchronously after glyph render. [Binds FR36.]
- **NFR2: Morning Digest delivery window.** Digest is generated and delivered ≤ 15 minutes (p95) from scheduled digest-job start, targeted to land in the strategist's inbox/app by 07:00 **strategist-local time**. [Binds FR34.]
- **NFR3: Evening Synthesis delivery window.** Evening Synthesis delivered by 19:00 strategist-local time (p95). [Binds FR35.]
- **NFR4: Citation resolution latency.** Citation deep-link expand-inline completes ≤ 1.5 seconds (p95) from user-click event receipt. [Binds FR41.]
- **NFR5: Surface freshness SLOs.** Per-surface staleness ceilings (measurement origins per conventions): Morning Digest ≤ 30 min; **In-Meeting Alert ≤ 60 s** (binding constraint for backpressure); Phase & Task Tracking ≤ 5 min; Timeline (V1.5) ≤ 5 min. When exceeded, memory-syncing glyph surfaces per FR48. [Binds FR48.]
- **NFR6: Ingestion throughput — sustained and peak.** Data Plane sustains ingestion of ≥ **500 events/account/day** (30-day average, UTC calendar day) and absorbs peak bursts of ≥ **2,500 events/account/hour** without violating NFR5 In-Meeting Alert (≤60 s). Event types counted: calendar, email, meeting-transcript-chunk. [Binds FR1, FR9–FR12.]
- **NFR7: FOIA export throughput.** `[V1 revised]` Customer Records Officer produces a signed FOIA export bundle for an account with ≤ 10 GB of canonical memory within ≤ **4 hours** of CLI invocation at V1, improving to ≤ 30 min post-StateRAMP Ready. [Binds FR60.] *Rationale (Party Mode): ≤30 min on solo ops capacity is infeasible; 4h covers the Anchor case and is tightened as engineering scales.*

### Availability, Reliability & Disaster Recovery

- **NFR8: Shared-tenant canonical memory RPO.** Recovery Point Objective ≤ 5 minutes for shared-tenant canonical memory. **Internal target, not customer-SLA-backed at V1.** [Binds Domain §5, FR69.]
- **NFR9: Shared-tenant canonical memory RTO.** Recovery Time Objective ≤ 4 hours for shared-tenant canonical memory under single-AZ or component failure. Full-region-loss DR uses cross-region restore-from-backup within ≤ 24 hours at V1 (single-region), improving to ≤ 4 hours cross-region post-StateRAMP. **Internal target, not customer-SLA-backed at V1.** [Binds Domain §5, FR69.]
- **NFR10: Platform availability.** `[V1 revised]` Shared-tenant control/data planes maintain ≥ **99.0% monthly availability at V1**, scaling to ≥ 99.5% at StateRAMP Ready (M6–M9), and ≥ 99.9% post-StateRAMP (M12+). Availability measured per Measurement Conventions. *Rationale (Party Mode): 99.5% solo on-call with 3.6h/month downtime budget is a breach waiting to happen; 99.0% is honest for V1, uplifted with ops maturity.*
- **NFR11: Agent failure graceful degradation.** When Cartographer, Oracle, or Master Strategist is unavailable, surfaces remain usable in canonical-memory-only mode with explicit agent-error state per FR46. **Maximum agent-outage duration before customer Security-contact communication: 2 hours at V1, reducing to 1 hour post-StateRAMP.** [Binds FR46.]
- **NFR12: Integration retry & backpressure.** Integration pulls retry transient failures with exponential backoff (base 2s, max 5 min) and honor provider rate-limit headers. **No ingest data loss on upstream provider outages ≤ 72 hours.** [Binds FR18, FR19.]
- **NFR13: SIEM egress replay buffer.** `[List tier, V1.5]` SIEM push retains ≥ 72 hours of events for replay after customer-side SIEM outage. [Binds FR67.]

### Security & Data Protection

- **NFR14: Cryptographic modules.** All cryptographic operations (at-rest, in-transit, signing) use FIPS 140-2 validated modules. [Binds Domain §5.]
- **NFR15: Encryption at rest.** All canonical memory, audit logs, and evidence artifacts encrypted at rest with AES-256 (or FIPS-equivalent successor).
- **NFR16: Encryption in transit.** All network traffic between DeployAI components and between DeployAI and customer systems uses TLS 1.3 or higher.
- **NFR17: Key custody (shared-tenant).** Shared-tenant SaaS uses cloud-provider-managed KMS (FIPS-validated, US region).
- **NFR18: Key custody (self-hosted).** Reference self-hosted topology supports customer-owned keys via BYOK/HSM. [Binds FR78.]
- **NFR19: Trusted timestamp source.** Signed timestamps on audit log events, canonical-memory event nodes, and FOIA exports use an RFC 3161 TSA backed by an independent public trust chain.
- **NFR20: Tamper evidence (edge agent).** Edge Agent local transcripts produce tamper-evident output verifiable offline without the authoring agent. [Binds FR13.]
- **NFR21: Break-glass dual-approval.** Platform Admin privileged-override access requires two independent authenticated users (hardware-backed authentication). [Binds FR64.] *V1 resource prerequisite: requires staffed security function (Option B vCISO or Option A +1 eng with security cross-train).*
- **NFR22: Break-glass customer notification.** Platform Admin privileged-override access notifies the customer's designated Security contact before session opens, with a 15-minute objection window for non-emergency access. **"Emergency access" = documented Sev-1 incident with live customer data-loss risk; all other access is non-emergency.** Session auto-expires ≤ 4 hours; transcript delivered post-hoc. [Binds FR64.]
- **NFR23: Tenant isolation model.** `[V1 revised]` **Shared-instance Postgres with tenant-scoped envelope encryption (per-tenant data encryption keys, KMS-wrapped) + Row-Level Security + mandatory tenant_id on every row.** Physical database-instance-per-tenant is NOT required at V1; it is deferred to post-StateRAMP for customers contracting dedicated-instance topology. Cross-tenant read paths must not exist in production code; enforced by authorization layer and CI-gate fuzz harness (see NFR52). *Rationale (Party Mode): physical-instance-per-tenant at V1 is operationally prohibitive at solo capacity; envelope-encryption + RLS + audit-gated queries is the V1 isolation boundary.* [Binds FR72.]
- **NFR24: Integration kill-switch latency.** Per-integration kill-switch toggles complete token revocation + in-flight queue purge + audit event within ≤ 30 seconds of toggle-event receipt. [Binds FR14, FR17.]
- **NFR25: Bifurcated record-of-truth isolation.** `[V1 revised]` **V1: Logical bifurcation — customer-tenant artifacts and DeployAI observational derivatives reside in separate database clusters with separate encryption domains and separate backup policies, sharing an operational control plane.** Physical bifurcation (separate control planes, separate compute pools) is a V1.5 / post-StateRAMP commitment documented in the Compliance-Architecture Brief migration path. *Rationale (Party Mode): two fully-separated control planes operated by a solo-or-duo team at 99.0%+ availability is infeasible; logical bifurcation preserves the data-governance contract while staying shippable.* [Binds FR7.]
- **NFR26: Network isolation (shared-tenant enterprise).** PrivateLink or VPC-endpoint connectivity available for enterprise shared-tenant customers. [Binds Domain §5.]
- **NFR27: Network isolation (self-hosted).** VPC-peering or equivalent private connectivity required for self-hosted topology. [Binds Domain §5.]

### Compliance & Privacy

- **NFR28: Section 508 + WCAG 2.1 AA conformance.** All V1 active surfaces conform to Section 508 + WCAG 2.1 AA; VPAT published at launch. [Binds FR44.]
- **NFR29: FOIA export verifiability.** Any third-party verifier validates signatures and chain-of-custody using only the open-source CLI and public trust-authority keys. [Binds FR60, FR61.]
- **NFR30: SOC 2 Type II.** `[Staged revised]` Audit kickoff by M12; Type II report target by M15–18 (12-month observation window from SOC 2 readiness declaration). *Rationale (Party Mode): concurrent-with-V1-build audit under solo capacity is infeasible; push to post-V1-ship with appropriate observation window.*
- **NFR31: StateRAMP Ready.** 3PAO engagement letter signed no later than 6 months before Ready-designation target. **Ready-designation target is customer-driven: set by Anchor (NYC DOT) commit timing.** (If engagement at M0, Ready at M6; if engagement at M4, Ready at M10–11.)
- **NFR32: NIST AI RMF mapping.** V1-relevant controls mapped to NIST AI RMF functions: citation envelope → MEASURE; replay-parity → MANAGE; override-in-reasoning-trail → GOVERN. Mapping documented in Compliance-Architecture Brief.
- **NFR33: Retention — per data class.** `[Revised for precision]` Retention defaults per canonical-memory class: **Event log: 7-year minimum; Solidified-learning library: 7-year minimum; Annotations & overrides: 7-year minimum; Edge-captured raw transcripts: 90 days** (summarized extractions retained 7 years; raw deleted); **Action Queue historical records: 7-year minimum**. All classes modifiable per-account by explicit customer contract. [Binds FR8.]
- **NFR34: Retention — audit log.** Audit logs retained 7 years minimum, immutable, independently attestable. **Not customer-override-configurable below 7 years** (in contrast to NFR33 which permits per-account customization). [Binds Domain §5.]
- **NFR35: Data residency.** V1: single US AWS region (us-east-2 primary, multi-AZ within region), no cross-border data transfer. Multi-region availability post-StateRAMP Ready.
- **NFR36: Internationalization.** V1: English only, US-only locale. i18n deferred — no i18n requirement at V1 or V1.5.
- **NFR37: Privacy-scope enforcement.** Private-scope annotations enforced by authorization-layer check preceding every query, with private annotations stored in a logically-separate store (distinct encryption key). Row-level filters alone do not satisfy this NFR. [Binds FR52.]
- **NFR38: FOIA-export tombstone completeness.** FOIA exports include tombstone records for any evidence destroyed during the requested range, with attestation of destruction authority and timestamp. [Binds FR5, FR60.]
- **NFR39: Two-party consent.** Voice/meeting capture workflows enforce two-party consent where required by jurisdiction (default US all-party-consent-states). [Binds FR12.]

### Accessibility

- **NFR40: Task-completion parity.** Screen-reader-primary user completes the top-5 V1 journeys (Morning Digest review, In-Meeting Alert review, Phase & Task Tracking, Override-with-Evidence, FOIA workflow as Records Officer) within ≤ 1.5× sighted-user completion time. [Binds FR44.]
- **NFR41: Keyboard equivalence.** Every interactive capability on every active surface is reachable and operable via keyboard alone. **Includes drag operations (offered as keyboard move-alternative), context-menus (keyboard-triggered), and all state changes.** No capability is mouse-exclusive.
- **NFR42: Screen-reader semantic structure.** Every surface exposes the canonical memory node/citation/relationship model as **WAI-ARIA semantic structure** (not only visual layout). Node chips announce identity + confidence + state; zoom transitions announce as state changes.
- **NFR43: A11y-first design process.** Design artifacts (wireframes, prototypes, usability scripts) demonstrate screen-reader walk-throughs pre-implementation, not retrofit. [Binds FR44.]
- **NFR44: Pre-V1 usability study.** **First-pass gate** at minimum n = 5 users including at least n = 1 screen-reader-primary user, pre-V1-ship. **Post-ship: second-pass study at n ≥ 8 within 6 months of V1 launch.** Findings published per Innovation §8 validation path.

### Scalability & Capacity

- **NFR45: Accounts per shared-tenant instance.** Shared-tenant SaaS supports ≥ **50 provisioned-and-active accounts** per instance at V1 without architecture change. ("Active" = at least one strategist login in trailing 7 days.)
- **NFR46: Canonical memory per account.** Single account canonical memory scales to ≥ 10 GB of event-node storage over the 7-year retention default without degraded NFR1/NFR4/NFR5 performance.
- **NFR47: Strategist-session concurrency.** A single strategist's active session supports ≥ 10 concurrently-open accounts without surface refresh-rate degradation. **Platform-wide: ≥ 25 strategists concurrently logged in at V1.**
- **NFR48: Agent throughput.** `[V1 aspirational — calibrate in M3 prototype]` Cartographer processes a 40-message email thread OR a 60-minute meeting transcript end-to-end within ≤ 5 minutes (p95), via **chunked-extract + map-reduce aggregate architecture** (monolithic extraction explicitly rejected). Each modality independently, not combined. *If M3 prototype evidence shows sustained > 8 min p95, NFR revised to ≤ 8 min with Compliance-Architecture-Brief note.*
- **NFR49: Post-StateRAMP scale.** Post-StateRAMP Ready, shared-tenant scales to ≥ 500 concurrent accounts and ≥ 50 concurrent strategists without re-architecture; multi-region deployment enables this.

### Verification & Release Quality

- **NFR50: 11th-call test CI gate.** CI Pipeline runs the 11th-call test on every merge to `main`. Release is blocked unless **per-release-candidate**: 100% citation-presence on all agent outputs, ≥ 95% citation-correctness on the frozen golden set (golden set ≥ 200 queries, frozen per release with documented version), and **zero hallucinated citations** — where "hallucinated" = *a citation whose `node_id` does not resolve in canonical memory at query time*. Self-consistent-but-wrong `evidence_span` citations are correctness defects tracked separately by NFR56. [Binds FR50.]
- **NFR51: Replay-parity gate.** CI Pipeline runs the replay-parity suite on every LLM model-version upgrade. Gate is rule-layer-primary with LLM-judge + human adjudication cascade per FR62. [Binds FR62, FR63.]
- **NFR52: Continuity-of-reference contract tests.** Four contract tests (same-node-resolution, visual-token parity, context-neighborhood, state-propagation) pass on every release against all V1 active surfaces. **Cross-tenant-isolation fuzz harness runs within this gate, attempting unauthorized cross-tenant reads and failing CI on any success.** [Binds FR41, FR42, FR43, NFR23.]
- **NFR53: Phase-retrieval audit matrix.** 21-cell audit matrix (7 phases × 3 stakeholder-topology variants) passes on every release with 100% suppression of phase-inappropriate surfaces and union-with-labels on phase-ambiguous queries. [Binds FR23.]
- **NFR54: Deterministic-path test coverage.** `[V1 revised]` Deterministic paths (canonical-memory writes, citation envelope schema, FOIA export construction, authorization checks) maintain ≥ **85% branch coverage at V1**, scaling to ≥ 95% branch + ≥ 80% mutation coverage at StateRAMP Ready. *Rationale (Party Mode): 95% on everything ships nothing in solo capacity; 85% V1 with uplift is credible.*
- **NFR55: Schema contract tests.** Citation envelope schema, canonical-memory event-node schema, tombstone schema, Action Queue schema, and override-event schema enforced by contract tests in CI, rejecting any output or database write that violates the schema.
- **NFR56: Replay-parity semantics choice audit.** Citation-set-identical semantics choice is reviewed quarterly; false-regression-rate and false-acceptance-rate published in the quarterly gate report. [Binds FR63.]

### Observability & Operability

- **NFR57: Operational metrics emission.** Control Plane emits metrics for ingestion rates, agent latency (p50/p95/p99), surface freshness, integration-pull health, error rates, and authz-check rates. [Binds FR68.]
- **NFR58: Distributed tracing.** Every user-originated request and every inter-agent call is traced end-to-end with correlation IDs. Traces retained ≥ 30 days for incident response.
- **NFR59: Structured audit log.** All authorization decisions, override events, schema-evolution events, break-glass sessions, FOIA exports, and kill-switch toggles emit structured audit entries with RFC 3161 signed time. [Binds FR68.]
- **NFR60: Incident-response RTO (availability).** Sev-1 availability incident (per Severity Taxonomy above) has response-start within 15 minutes and customer communication within 1 hour. *V1 resource prerequisite: 24/7 paging coverage requires Option A +1 eng or Option B vCISO contract at minimum.*
- **NFR61: Sev-2 citation-accuracy workflow.** Sev-2 citation-accuracy regression triggers customer notification + inclusion in next quarterly compliance packet with root-cause analysis. Packet scope: all in-contract customers.

### Supply Chain Integrity

- **NFR62: SBOM generation.** Every release artifact ships with a Software Bill of Materials in SPDX and CycloneDX formats. [Binds Domain §5.]
- **NFR63: Signed artifacts.** All release binaries (edge agent, FOIA CLI, service containers) are signed via Sigstore/cosign with reproducible-build verification.
- **NFR64: SLSA provenance.** Build provenance attestation meets SLSA Level 2 minimum at V1, SLSA Level 3 post-StateRAMP Ready.
- **NFR65: Dependency scanning.** CI Pipeline blocks any release with a known critical CVE in runtime dependencies; known high CVEs trigger compensating-control review.

### Deployment & Operational Constraints

- **NFR66: V1 region.** Shared-tenant SaaS operates in a single US AWS region (us-east-2 primary, multi-AZ within region) at V1. Multi-region post-StateRAMP.
- **NFR67: Dual topology parity.** Every V1 capability operating on shared-tenant also operates on the self-hosted reference topology OR has an explicit parity declaration (🟢 fully-parity / 🟡 degraded-parity / 🔴 not-in-self-hosted) in the self-hosted build documentation. [Binds FR78.]
- **NFR68: Self-hosted reference build form-factor.** `[V1 revised]` **V1: docker-compose reference build** runnable with documented prerequisites in ≤ 1 engineering-day by an enterprise IT team. **Helm chart deferred to V1.5.** *Rationale (Party Mode): Helm chart maturity is ~3 eng-weeks; docker-compose is sufficient for Anchor + design-partner self-hosted beta.* [Binds FR78.]
- **NFR69: Cooperative-purchasing artifact set.** Control Plane produces procurement-package artifact set (line-item pricing, standards-conformance summary, vendor-security docs, data-sharing contract shape) on demand to support Sourcewell cooperative-purchasing path. [Binds FR79.]

### LLM-Dependency, Cost, & Runtime Reliability (added in Party Mode Pass)

- **NFR70: LLM-provider failover.** Primary LLM provider (Claude Sonnet-class) with documented secondary provider (GPT-4-class or equivalent). Switchover time ≤ 10 minutes from primary-provider outage detection. Capability-parity matrix documented per agent (Cartographer / Oracle / Master Strategist) with known degradations. LLM-provider outage does NOT count against NFR10 platform availability.
- **NFR71: Cost-per-account envelope.** Infrastructure + LLM inference cost per active account ≤ **$400/account/month at V1** (mean over rolling 30 days). Exceeding this threshold triggers cost-review before onboarding additional accounts. Designed to preserve $30K Anchor-tier unit economics.
- **NFR72: Time-to-first-value.** Post-provisioning, strategist sees first useful Morning Digest (minimum: ≥ 3 citations from ≥ 2 distinct source threads) within ≤ **48 hours** of integration activation. [Binds FR15–FR22 integration onboarding.]
- **NFR73: Agent-runtime MTBF/MTTR.** Cartographer, Oracle, and Master Strategist each maintain MTBF ≥ 30 days between customer-visible agent-layer failures, with MTTR ≤ 4 hours post-detection at V1. MTTR ≤ 1 hour post-StateRAMP.

### Engineering Operability (added in Party Mode Pass)

- **NFR74: Migration safety.** Schema migrations follow expand-contract pattern, backward-compatible for ≥ 1 release. Canonical-memory migrations are append-only verified — no in-place mutation of historical event-nodes. Migration dry-run required for every release touching canonical-memory schema.
- **NFR75: Deploy cadence & rollback.** Maximum ≤ 2 production deploys per day. Rollback ≤ 5 minutes via feature-flag toggle or image revert. Canary deploy to ≤ 10% traffic required for any change touching agent-layer or citation assembler.
- **NFR76: Secrets rotation.** KMS data keys rotate ≤ 90 days. OAuth refresh tokens rotate per-integration-provider cadence. API keys rotate ≤ 180 days. Break-glass admin credentials rotated after every use and ≤ 30 days minimum.
- **NFR77: Dev-environment parity.** A new engineer stands up the full canonical-memory + 3-agent stack locally via `docker-compose up` (single command) in ≤ 30 minutes, with seeded fixture data enabling end-to-end Digest generation against synthetic events.
- **NFR78: Chaos / failure-injection cadence.** Monthly fault-injection drills (pod kill, DB failover, LLM API timeout, upstream integration rate-limit storm) with documented runbooks. Drill outcomes tracked against NFR10 availability target.

---

**Flagged for V1 Resource-Path Dependency (per M2 decision):** NFR10 (99.0% V1 target), NFR11 (2-hour agent-outage comm), NFR21 (dual-approval requires staffed security function), NFR30 (SOC 2 Type II timeline), NFR60 (24/7 paging coverage). Under Option C (solo, 12–15-month V1 ship), these thresholds remain valid but staffing gaps must be explicitly tracked in the Compliance-Architecture Brief as known compensating-control areas.

**Glossary appendix (Step 11 deliverable):** "nominal load," "deterministic paths," "frozen golden set," "semantic structure," "emergency access," "compute instance," "agent trigger," plus full Severity Taxonomy runbook entries.

```

```

