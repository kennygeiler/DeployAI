---
title: "Product Brief: DeployAI"
status: "complete"
created: "2026-04-21"
updated: "2026-04-21"
inputs:
  - "_bmad-output/brainstorming/brainstorming-session-2026-04-21-150108.md"
review_lenses_applied:
  - "Skeptic"
  - "Opportunity"
  - "GTM & Launch Risk"
strategic_decisions_made:
  - "Dual positioning → internal utility first; graduation decision at N≥2 design partners"
  - "NYC DOT → priced bundled line item inside hardware SOW (~$30K/yr placeholder, pending procurement); anchor price for commercial model"
  - "Pricing → three-tier structure (Anchor ~$30K bundled; $0-$15K design-partner; $60K-$150K list post-StateRAMP Ready)"
  - "Docs → demo-first, docs after (not cold pre-sale artifact)"
  - "Category framing → 'Deployment System of Record' (external); 'Deployment Operating System' (vision)"
  - "Published the 7-phase DeployAI Deployment Framework as open methodology"
---

# Product Brief: DeployAI

*The Deployment System of Record for high-stakes, long-cycle customer accounts.*

## Executive Summary

Large municipal and enterprise deployments fail slowly, in ways no one wants to admit. A champion rotates out. A deputy commissioner's priorities shift after an election cycle. A calibration is skipped to "save time" in month three, and a $20,000 re-scan lands in month nine. An implementation lead carries the entire deal in their head — and when they leave, the deal resets. Every long-cycle deployment has a hidden operating system running in human memory; when that memory fails, so does the deployment.

**DeployAI is the Deployment System of Record: durable, cited, agentic memory for every long-cycle customer account.** It converts every meeting, email, call, and field note across a deployment into a *Living Digital Twin of the account* — a canonical store of events, stakeholders, and justifiable beliefs that an agentic system retrieves at exactly the moment a strategist needs them. Morning digests surface the three things that matter today. In-meeting alerts surface prior learnings at the moment they become relevant. A timeline view makes the account's trajectory visible. A phase tracker keeps the strategist oriented across **the seven-phase DeployAI Deployment Framework** — a named, published methodology spanning pre-sale through expansion.

**DeployAI's first deployment is its own.** The product is being built inside a live NYC DOT engagement — DeployAI's LiDAR pavement-analytics hardware deployment — where the tool ships as a **priced line item inside the hardware SOW (~$30K/year placeholder, pending procurement conversation)**. This is the first tool revenue and the anchor price the rest of the commercial model scales from. NYC DOT is a named reference deployment running on real data; **peer GovTech vendors** — whose deployment strategists face the same problem without the option of building the tool themselves — are the next customers. Dogfooded on a named blue-chip account, sold to vendors who can't dogfood it — this is the wedge.

## The Problem

**Long-cycle deployments lose their memory faster than they accumulate value.** For a deployment lead running an 18-to-36-month municipal account, the failure modes are consistent and expensive:

- **Stakeholder turnover resets the deal.** Client-side champion leaves, a deputy commissioner gets reassigned, or a new political cycle changes priorities. Industry data names this as the *#1 silent killer of long-cycle deployments* — value justification, requirements, and trust must be rebuilt from scratch, often without the strategist realizing the change has happened.
- **Meetings become islands.** Existing AI meeting assistants produce atomic, per-meeting summaries that live in different tools — CRM, project tracker, Slack, personal docs. A critical comment in month two becomes invisible by month eight. There is no single, queryable source of truth across an 18-month deployment.
- **Tribal knowledge doesn't transfer.** When a strategist leaves the account, so does the hard-won intuition — which stakeholders actually decide, which pitches landed, which blockers nearly killed the deal last time. New teammates inherit folders, not understanding.
- **In regulated environments, the usual tools are off-limits.** Bot-join meeting recorders (Gong, Fireflies, Otter, Fathom) are routinely blocked by InfoSec in government settings. Strategists are forced back to manual notes and personal memory — precisely the surface area that fails hardest under long-cycle stress.
- **Value creation is invisible to finance.** Strategists drive real expansion — faster phase transitions, averted re-scans, $20K mistakes that didn't happen — but without structured memory, those wins stay anecdotal and never bridge from champion to budget office.

The cost is measurable: municipal procurement cycles already run 12–24 months; a single lost champion or skipped calibration can add another six, or end the deal entirely. Agencies are paying more for deployment services every year (GovTech services spend growing 20% CAGR, outpacing solutions) — but the strategists doing the work have no operating system for it.

## The Solution

DeployAI is an agentic Deployment Operating System organized around four product surfaces — and nothing else. Every design decision is weighed against whether it makes these four better.

1. **Morning Digest.** Three items the strategist needs to walk in knowing today, ranked by leverage-at-this-moment, each citing the specific events and prior learnings that produced it. A transparency footer shows what DeployAI considered and ranked out. Scannable in 60 seconds.

2. **In-Meeting Alert.** During live calls, when an utterance matches a solidified prior learning — *"can we skip the on-site calibration this time?"* — DeployAI surfaces a single private card on the strategist's screen referencing the relevant learning with named alternative patterns (e.g., *"a 3-day Minimum Viable Calibration was accepted in 2/2 prior cases"*). Private, retrieval-only, within an eight-second latency budget. Never audible, never visible to the customer, never scripts what the strategist should say. **Live capture is consented and runs on the strategist's own device** (local transcription for supported meeting platforms; manual post-meeting upload as a fallback for platforms where local capture isn't viable). No bot joins the call — the compliance-native capture path is part of the product, not a workaround.

3. **Timeline / Visibility View.** A live visualization of the account: phases traversed, key events plotted on time, the stakeholder graph evolving as people enter, exit, and change roles, and landmark learnings surfaced at the moments they were solidified. The "Living Digital Twin" made tangible — the highest-leverage visual surface for prospective customers evaluating DeployAI's implementation rigor.

4. **Phase & Task Tracking.** At-a-glance indication of the deployment's current phase in the **DeployAI Deployment Framework** — seven phases spanning pre-sale, preparation, integration, user training, value creation, preparing-for-expansion, and expansion — the signals accruing toward the next transition, and the phase-specific tasks the strategist should be working on right now, including blocker-removal items surfaced automatically from communication signals. The framework itself is published as an open methodology; the tool makes it executable.

Underneath the surfaces, three agents do the work: a **Cartographer** passively extracts people, organizations, roles, committees, and relationships from every communication; an **Oracle** runs phase-gated retrieval to surface the right learning at the right moment; and a **Master Strategist** ranks, arbitrates, and proposes phase transitions as an integration layer (not a dashboard of its own). Every agent output carries a citation envelope back to primary evidence — no claim is ever made without a traceable trail.

## What Makes This Different

The category is crowded — and none of the incumbents solve the deployment strategist's actual problem.

| Category | Example | Why it doesn't solve this |
|---|---|---|
| Revenue intelligence | Gong, Chorus | Sales-cycle only; no post-sale memory, no deployment phases |
| Meeting assistants | Fireflies, Otter, Fathom | Atomic per-meeting output; bot-join blocked in government; no cross-meeting canonical memory |
| Relationship intelligence | Affinity, Clay | Built for outbound/VC sourcing; no deployment-phase dynamics or advocacy-over-time |
| Customer success platforms | Gainsight, Catalyst, Vitally | SaaS-telemetry-centric; weak for hardware+services multi-year government deployments |

**DeployAI's defensible position** is the combination no incumbent can replicate without cannibalizing their model:

- **Canonical memory as a single source of truth**, with anti-hallucination enforced at the agent boundary via mandatory citation envelopes. Every surfaced fact traces back to a specific event, identity node, or solidified learning in a persistent, auditable store. The product's moat is the memory, not the model — LLMs are swappable, the graph is not.
- **Phase-gated retrieval, not similarity search.** DeployAI retrieves learnings because they match *the current deployment phase and the current stakeholder context*, not because they're topically similar. This is the specific failure mode of RAG that the strategist use case demands fixing.
- **Compliance-native architecture.** No bot-join capture. Consented async upload and API-first ingestion. Immutable event log with attestation. Human-in-the-loop gating on every below-confidence output. This lands cleanly in government/regulated environments where incumbents get blocked at InfoSec review.
- **Documentation is part of the product, but sequenced correctly.** Agent logic docs, product surface docs, deployment logic walkthroughs, and scope manifests ship alongside code, traceable to design atoms in the product's brainstorming corpus. They go to prospects *after* a live demo on real deployment data — never as cold pre-sale marketing. The docs reinforce rigor after the buyer has seen the software work; they never substitute for it.
- **Dogfooded on a live municipal deployment.** The first deployment strategist using DeployAI is the founder, running DeployAI's own NYC DOT engagement. The product is shaped by real deployment reality, not imagined personas — and the real-deployment proof is named, not aspirational.

## Who This Serves

**Primary user: the deployment strategist** running a high-stakes, long-cycle account (12–36 months) for a hardware-enabled software company selling into municipal or enterprise government customers. They are simultaneously project manager, account manager, and customer success engineer; they live in meetings, emails, field visits, and calls; they carry the entire deal in their head because no existing tool does. Success for them is walking into a meeting knowing exactly what matters today, watching their stakeholder graph update itself, and proving to the budget office — with cited evidence, not anecdote — that the deployment created measurable value.

**Buyer vs. user distinctions matter here, because there are two different commercial motions:**

- **At DeployAI internally (and NYC DOT as the first external deployment):** the tool is a force-multiplier for the founding strategist and a **priced line item inside the hardware SOW (~$30K/year placeholder)** — generating the first tool revenue and anchoring the commercial model. NYC DOT is an existing DeployAI hardware customer; the *tool* relationship is ring-fenced from the hardware contract so tool underperformance never contaminates the core relationship. The tool is invoiced distinctly inside the SOW so the pricing is discoverable and scales cleanly — but it is not yet a standalone SaaS product.
- **At peer GovTech vendors (V2, after N ≥ 2 real deployments):** the buyer is the **founder-CEO, VP of Customer Success, or Head of Implementation** at a peer infrastructure-analytics company. They already pay for Gainsight or Gong, feel the gap, and recognize the deployment layer as where their company wins or loses accounts. The user is the deployment strategist on their team.

**Secondary beneficiaries:** the customer's own stakeholders (commissioners, field techs, budget office) experience a better-run deployment without ever using the software directly. DeployAI's internal team — engineering, future hires, investors — inherit a legible, traceable operational memory of every account rather than a folder of Slack threads.

**Design-partner commitment:** V1 is validated against at least two non-founder deployment strategists (target: one peer-vendor strategist, one large-account enterprise implementation lead) before external launch. The brief acknowledges that "built by the user" is a sample size of one until that validation lands.

## Technical Approach (High-Level)

DeployAI is built on a canonical-memory substrate: an immutable event log, a time-versioned identity graph, a solidified-learning library with evidence snapshots, and an action queue, all queryable with phase and identity as first-class keys. Agents are retrieval-bound — they cannot emit claims about identities, events, or learnings not already in the store; they can only propose additions, which route through tiered confidence gates. Every agent parameter is tunable through audited calibration events logged as first-class history, never through silent drift. The system ships with 100% test coverage on deterministic paths and replay tests that pin agent behavior across LLM model changes. Ingestion is API-first (email, calendar, meeting recordings uploaded post-hoc, Linear tasks, manual notes) — no bot joins the call.

## Compliance & Regulatory Posture

DeployAI is architected from day one for government-procurement reality: immutable audit logs, citation-envelope traceability, human-in-the-loop gating on agent output, two-party consent for all capture, FOIA-aware data-retention design, and no autonomous actions on government-adjacent data without explicit strategist authorization. This is the architectural foundation for FedRAMP / StateRAMP / CJIS readiness as customer procurement cycles require. No certification claim is made in V1; the first pilot establishes the real certification pathway.

## Success Criteria

**12-week pre-visualization milestone:** NYC DOT engages substantively with the DeployAI documentation package and seeded demo; pre-visualization conversation progresses into concrete pilot scoping.

**12-month product milestones:**
- DeployAI's own next deployment measurably benefits: shorter Phase 5 → 6 transition, zero surprise stakeholder-turnover losses, first traceable reuse of learnings across deployments once a second deployment runs.
- NYC DOT converts to a paid pilot.
- One additional municipal prospect enters active pre-visualization.

**Operational SLOs (ongoing, measurable):** test coverage on deterministic code paths maintained at ≥95% with replay tests pinning agent behavior across model changes; fewer than one severity-2 citation-accuracy incident per 1,000 customer-visible agent outputs per quarter; documentation schema tests pass on every release (doc claims match code behavior).

**Commercial milestones (revised for procurement reality):**
- **12-month:** NYC DOT SOW includes the tool at the anchor price (~$30K/year placeholder) as a discoverable line item — first tool revenue recognized; 2 named peer-vendor design partners in active discovery; first design-partner MOU signed; pricing-validation conversations complete with first 3 peer-vendor prospects.
- **24-month:** first recognized peer-vendor design-partner revenue; one additional municipal agency in bundled pricing scoping (aim: match or exceed NYC DOT anchor); cooperative-purchasing application (NASPO / GSA Schedule / Sourcewell) filed; StateRAMP Ready certification path engaged.

## Commercial Model

DeployAI commits to a **three-tier commercial structure**, published explicitly to prevent bad price anchoring and to signal integrity to buyers:

- **Anchor Tier — NYC DOT and future municipal pilots, ~$30K/year (placeholder, actuals set in procurement).** The tool is a priced line item inside the hardware SOW, ring-fenced from the hardware contract so tool performance cannot contaminate the hardware relationship. This is the anchor price: it establishes that the tool is a paid product, makes pricing discoverable to future procurement teams, and gives the rest of the commercial model something real to scale from. Not a free reference — a low-anchor reference.
- **Design-Partner Tier — $0 to $15K/year per vendor, capped at 3 slots.** Available to the first 2–3 peer-vendor customers in exchange for deep access, co-development rights, and a named public case-study commitment. Priced *below* the Anchor Tier because design-partners are trading strategic value (co-development + case-study rights); NYC DOT is not. These relationships produce the validation that earns the list tier.
- **List Tier — $60K to $150K ARR per vendor, activated only after the StateRAMP Ready (or equivalent) compliance gate is cleared.** Roughly 2x–5x the Anchor price, scaled by active deployment count and vendor size. DeployAI publicly commits to not closing at list before the compliance gate — this protects the reference price and the trust of the first paying customers.

**Scaling logic:** NYC DOT anchor ($30K) → Design-Partner peer vendors ($0–$15K, discounted for strategic trade) → post-StateRAMP List tier ($60K–$150K, 2–5x anchor). The anchor creates the reference; the compliance gate unlocks the multiple.

## Scope

**In for V1 (demo-ready in 12–16 weeks, seeded data):**

- Four product surfaces: Morning Digest, In-Meeting Alert, Timeline / Visibility, Phase & Task Tracking.
- Canonical memory: event log, time-versioned identity graph, learning library with evidence snapshots, action queue, User Validation Queue.
- Three-agent runtime: Cartographer, Oracle, Master Strategist. Blockers surface as typed events and action-queue items — no standalone Blocker dashboard.
- Seven-phase deployment state machine with agent-proposed, human-confirmed transitions.
- Ingestion paths: email, calendar, meeting recording upload, manual notes, Linear read-only.
- Documentation package: agent logic docs, product surface docs, deployment logic walkthrough, scope manifest, ingestion doc, documentation provenance trail.
- 100% test coverage with replay tests pinning demo behavior.

**Explicitly out of V1 (architected, not engineered):**

- Cross-deployment analytics dashboard — waits for N ≥ 3 real deployments.
- Live multi-agent negotiation trace UI — logic runs, trace UI deferred.
- Standalone Blocker dashboard.
- Web-aware verification as a standing surface — narrow use for identity disambiguation only.
- Advanced calibration-review tooling beyond a basic audit log.
- Cross-corpus statistical promotion machinery.

**Explicitly not-to-build — ever:** competitive intelligence, external-threat mapping, vendor-tracking surfaces. DeployAI is a deployment strategist tool, not a market-intelligence product.

## Structural Decision

DeployAI-the-tool is, **for V1, an internal utility of DeployAI-the-hardware-company**, bundled with hardware deployments as a priced line item (~$30K/year anchor at NYC DOT, placeholder pending procurement) and validated through that engagement as a reference deployment. External commercial activity (peer-vendor design-partner pilots) opens only after (a) two non-founder deployment strategists have used the product daily for ≥90 days, and (b) the tool's four V1 surfaces are stable on real deployment data — not seeded data.

The **graduation decision — product line of DeployAI, dedicated PM, or spinout with separate cap table — is made at N ≥ 2 validated design partners**, not before. This avoids the classic founder-tell of a premature external product, while preserving optionality for the stronger opportunities the product may earn. Until that decision, the tool has no independent fundraising, no independent hiring plan, and no independent roadmap.

## What We're Watching (Top Risks)

The brief acknowledges the real risks the team is managing against — each with an explicit mitigation commitment:

1. **Single-threaded pipeline.** NYC DOT is the only named prospect. *Mitigation:* generate a named list of 15–20 peer-vendor V2 prospects and book 5 discovery calls within 30 days of V1 build kickoff.
2. **Procurement reality vs. optimism.** Municipal procurement cycles run 12–24 months; first invoiced revenue is more likely in year 2 than year 1. *Mitigation:* 12-month milestone is MOU + pilot SOW, not revenue; cooperative-purchasing application filed early.
3. **Internal-tool vs. external-product tension.** Founder attention can be pulled fully into hardware GTM. *Mitigation:* explicit decision made on the tool's structure (internal utility / product line / spinout — see Open Strategic Choices, below).
4. **Builder-is-user N = 1.** Design decisions derived from a single strategist may not generalize. *Mitigation:* two non-founder design partners by end of V1 build.
5. **FOIA exposure of canonical memory.** Stakeholder observations on municipal employees may be discoverable. *Mitigation:* explicit data-boundary in customer MSAs; DeployAI-controlled observational data (sentiment, political read, advocacy scores) lives outside the customer tenant; customer-controlled data is scoped and retention-governed to FOIA standards.
6. **LLM data-handling InfoSec review.** The no-bot-join stance doesn't by itself answer the 2026 InfoSec concern about LLM data flows. *Mitigation:* data-flow diagram published before next agency conversation; single-tenant / self-hosted deployment option offered where shared-tenant LLM calls are blocked.

## Vision

Three years out, DeployAI is the **Deployment Operating System** for every long-cycle deployment at every hardware-enabled software company selling into regulated customers. A deployment strategist joining a peer-vendor company — whether in municipal infrastructure, utilities, defense, or healthcare IT — inherits not a folder of legacy docs but a queryable, versioned, cited deployment history going back years. The Living Digital Twin becomes the default way companies remember, learn from, and transfer knowledge about their most expensive customer relationships. The DeployAI Deployment Framework becomes the shared vocabulary — the way Agile and RACI became vocabulary — that the industry uses to talk about long-cycle deployments. Agents evolve to handle new decision classes (pricing proposals, contract-renewal risk, cross-account pattern learning once the corpus matures) — always through the same foundation: canonical memory, citation envelopes, human-in-the-loop, surface-don't-script. The product that proved itself getting NYC DOT across the finish line becomes the default substrate for how modern deployment teams actually work.
