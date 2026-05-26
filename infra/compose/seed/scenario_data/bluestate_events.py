"""BlueState Health 26-week scenario event corpus.

Each ``ScenarioEvent`` is one ledger row to emit. Time is expressed as
``(week, day, hour)`` relative to ``W1_MONDAY`` and resolved at seed time
so the timeline floats with ``datetime.now(UTC)``: W26 always ends ~14d
before the wall-clock so the trailing-silence + last-24h decision design
both have room.

Source kinds chosen to match the analyzer queries — see
``docs/test-scenarios/bluestate-health.md`` for the ground-truth mapping.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioEvent:
    """One ledger event to seed.

    ``week``/``day``/``hour`` resolve to a timestamp at seed time. ``kind``
    is the ledger source_kind. ``node_type`` is used for stakeholder /
    risk events whose analyzer reads ``detail.node_type``.
    """

    week: int
    day: int
    hour: int
    kind: str  # ledger source_kind
    summary: str
    body: str
    actor_kind: str = "user"
    actor_id: str | None = None
    node_type: str | None = None  # for matrix_node_* and insight_* rows
    title: str | None = None  # for matrix nodes / insights
    cluster: str | None = None  # tags for cross-referencing (e.g. "decision-w3-vendor")
    accept_decision: bool = False  # If True, the matching extracted proposal becomes a decision accept
    rejects_acceptance: bool = False  # If True, a proposal_rejected is emitted at this slot
    risk_close_of: str | None = None  # If set, closes the risk node with this cluster id


# Stakeholder churn events — matrix_node_created / matrix_node_deleted for node_type=stakeholder.
STAKEHOLDERS: list[ScenarioEvent] = [
    # W1 — initial 3 stakeholders
    ScenarioEvent(
        week=1,
        day=1,
        hour=10,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Patricia Vance (CMO)",
        summary="stakeholder added: Patricia Vance, Chief Medical Officer",
        body="Initial stakeholder identified during pre-engagement scoping with BlueState Health. "
        "Patricia Vance is Chief Medical Officer and the executive sponsor for the member-portal "
        "modernization. She owns the clinical-experience side of the success criteria and will "
        "chair the steering committee.",
        cluster="stakeholder-vance",
    ),
    ScenarioEvent(
        week=1,
        day=1,
        hour=11,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Tom Reyes (VP Product)",
        summary="stakeholder added: Tom Reyes, VP Product",
        body="Tom Reyes runs the product side at BlueState and is the day-to-day decision-maker "
        "for portal feature scope. He pushed back early on a phased rollout and wants the "
        "full member experience live by Q3.",
        cluster="stakeholder-reyes",
    ),
    ScenarioEvent(
        week=1,
        day=1,
        hour=12,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Lisa Wong (Eng Dir)",
        summary="stakeholder added: Lisa Wong, Engineering Director",
        body="Lisa Wong leads the BlueState platform engineering team. Owns integration with the "
        "claims and eligibility services. Will assign two engineers to pair with our FDE.",
        cluster="stakeholder-wong",
    ),
    # W3-4 — compliance + procurement additions (2 — low churn)
    ScenarioEvent(
        week=3,
        day=2,
        hour=14,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Raj Patel (Compliance)",
        summary="stakeholder added: Raj Patel, Compliance Lead",
        body="Compliance lead pulled in after Patricia flagged HIPAA exposure on the member-message "
        "feature. Raj will own the BAA review and the data-handling sign-off before any PHI "
        "field enters the new portal.",
        cluster="stakeholder-patel",
    ),
    ScenarioEvent(
        week=4,
        day=3,
        hour=10,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Maya Singh (Procurement)",
        summary="stakeholder added: Maya Singh, Procurement",
        body="Procurement owner — Maya Singh from BlueState supply chain. Required for the master "
        "services agreement and any change orders. Conservative on language around data "
        "ownership and exit clauses.",
        cluster="stakeholder-singh",
    ),
    # W14 — churn cluster: Tom Reyes departs, Lisa Wong rotates off the program, plus
    # a procurement deputy ages out. 3 departures in W14 window vs ~1 prior 30d ⇒ ratio > 2x
    # triggers the stakeholder_churn analyzer (which counts departures only — see
    # control_plane/intelligence/stakeholder_churn.py:_fetch_churn_events).
    ScenarioEvent(
        week=14,
        day=2,
        hour=9,
        kind="matrix_node_deleted",
        node_type="stakeholder",
        title="Tom Reyes (VP Product) — departed",
        summary="stakeholder removed: Tom Reyes left BlueState",
        body="Tom Reyes resigned to take a CPO role at a competitor. His exit was announced "
        "internally Friday; his accounts are being deactivated this week. Critical loss — "
        "he was the day-to-day product decision-maker and his replacement is not yet named.",
        cluster="stakeholder-reyes-out",
    ),
    ScenarioEvent(
        week=14,
        day=3,
        hour=10,
        kind="matrix_node_deleted",
        node_type="stakeholder",
        title="Lisa Wong — rotated off program",
        summary="stakeholder removed: Lisa Wong rotated off the portal program",
        body="Lisa Wong was rotated off the portal program by Patricia after the W14 reorg. "
        "She remains Eng Director but a deputy (Priya Subramanian) takes the day-to-day "
        "engineering interface for the rest of the engagement.",
        cluster="stakeholder-wong-out",
    ),
    ScenarioEvent(
        week=14,
        day=4,
        hour=9,
        kind="matrix_node_deleted",
        node_type="stakeholder",
        title="Maya Singh — handed off to deputy",
        summary="stakeholder removed: Maya Singh transferred procurement work to Carla Diaz",
        body="Maya Singh accepted a stretch role on another modernization program and handed "
        "the portal procurement over to her deputy Carla Diaz. Hand-off completed "
        "Thursday.",
        cluster="stakeholder-singh-out",
    ),
    ScenarioEvent(
        week=14,
        day=3,
        hour=14,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Sandra Kim (VP Product, replacing Tom)",
        summary="stakeholder added: Sandra Kim, new VP Product",
        body="Sandra Kim takes over the VP Product role from Tom. Joining from a Medicare "
        "Advantage plan where she ran member experience. Wants a re-baseline meeting before "
        "she signs off on the in-flight scope — risk of mid-stream pivot.",
        cluster="stakeholder-kim",
    ),
    ScenarioEvent(
        week=14,
        day=4,
        hour=11,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="David Liu (VP IT Security)",
        summary="stakeholder added: David Liu, VP IT Security",
        body="New role on the customer side — VP IT Security. David Liu was promoted from "
        "Security Architect after a recent ransomware near-miss prompted the org to "
        "create a VP-level security function. He'll re-review our SOC2 attestation and "
        "the pen-test schedule before pilot launch.",
        cluster="stakeholder-liu",
    ),
    ScenarioEvent(
        week=14,
        day=5,
        hour=10,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Priya Subramanian (Eng Deputy)",
        summary="stakeholder added: Priya Subramanian, engineering deputy taking Lisa's day-to-day",
        body="Priya Subramanian steps in as the day-to-day engineering counterpart while Lisa "
        "is rotated off the program. Strong engineer; not yet read into the integration "
        "decisions made in W5-12.",
        cluster="stakeholder-priya",
    ),
    ScenarioEvent(
        week=14,
        day=5,
        hour=14,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Carla Diaz (Procurement Deputy)",
        summary="stakeholder added: Carla Diaz takes procurement from Maya",
        body="Carla Diaz takes over procurement. Less experienced than Maya but eager. Will "
        "need extra cycles on the post-pilot expansion order.",
        cluster="stakeholder-carla",
    ),
    # W22 — single add (CDO)
    ScenarioEvent(
        week=22,
        day=1,
        hour=10,
        kind="matrix_node_created",
        node_type="stakeholder",
        title="Mark Thompson (Chief Data Officer)",
        summary="stakeholder added: Mark Thompson, Chief Data Officer",
        body="Mark Thompson — newly hired CDO at BlueState. Wants to use the portal launch as a "
        "forcing function for member-data normalization. Helpful long-term, scope creep "
        "short-term.",
        cluster="stakeholder-thompson",
    ),
]


# Decision events — paired llm_proposal_created + proposal_accepted, with the
# accept time controlling the analyzer's cycle measurement.
# 4 decisions in W1-4, 6 in W5-12, 2 in W13-16, 0 in W17-19 silence, ~3 in W20-26.
DECISIONS: list[ScenarioEvent] = [
    # ---- W1-4 Discovery — 4 decisions, fast cycle (~1-2 days) ----
    ScenarioEvent(
        week=1,
        day=2,
        hour=14,
        kind="decision",
        title="Engagement model: 26-week phased build",
        summary="decision proposed: 26-week phased delivery vs big-bang",
        body="Sarah pitched a 26-week phased delivery to Patricia. Phase 1 (discovery, weeks "
        "1-4), Phase 2 (design, 5-12), Phase 3 (build, 13-16), Phase 4 (pilot, 20-24), "
        "Phase 5 (launch prep, 25-26). Patricia preferred big-bang but conceded after "
        "Lisa's team raised integration concerns. Decision: phased.",
        cluster="decision-w1-engagement-model",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=2,
        day=2,
        hour=16,
        kind="decision",
        title="Identity provider: Okta over Auth0",
        summary="decision proposed: Okta selected as IDP",
        body="Marcus walked the team through identity options. BlueState already runs Okta for "
        "employee SSO so reusing it for member identity reduced new vendor surface. Auth0 "
        "rejected for cost and the BAA gap. Decision: Okta.",
        cluster="decision-w2-okta",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=3,
        day=4,
        hour=11,
        kind="decision",
        title="Data residency: us-east-1 + us-west-2 active/passive",
        summary="decision proposed: dual-region active/passive in us-east-1 / us-west-2",
        body="Raj's first major call after joining: he insisted on dual-region for the PHI "
        "store. Marcus proposed us-east-1 primary, us-west-2 passive. Patricia agreed "
        "given the regulatory exposure of a single-region outage. Decision: us-east-1 + "
        "us-west-2 active/passive with RPO < 5 min.",
        cluster="decision-w3-regions",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=4,
        day=3,
        hour=14,
        kind="decision",
        title="Member-message channel: in-portal first, no SMS in v1",
        summary="decision proposed: in-portal messaging only in v1; SMS deferred",
        body="Tom wanted SMS at launch. Raj pushed back on the PHI exposure of any out-of-band "
        "channel without explicit member consent flow. Compromise: in-portal messaging in "
        "v1, SMS deferred to v2 once consent infrastructure is in place. Decision: "
        "in-portal only for v1.",
        cluster="decision-w4-messaging",
        accept_decision=True,
    ),
    # ---- W5-12 Design — 6 decisions, ~3d cycle ----
    ScenarioEvent(
        week=5,
        day=2,
        hour=10,
        kind="decision",
        title="Frontend stack: Next.js + Tailwind",
        summary="decision proposed: Next.js + Tailwind for member portal frontend",
        body="Lisa's team had a slight preference for SvelteKit but Marcus's experience and the "
        "available hiring market argued for Next.js. Tailwind for design-system speed. "
        "Decision: Next.js 15 + Tailwind 4.",
        cluster="decision-w5-frontend",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=6,
        day=4,
        hour=15,
        kind="decision",
        title="Eligibility cache: 4h TTL with manual invalidation",
        summary="decision proposed: 4h eligibility cache TTL with admin-triggered invalidation",
        body="Eligibility lookups against the back-office mainframe are slow (~800ms) and rate-"
        "limited. Lisa's team proposed an in-portal cache. Raj required a manual-"
        "invalidation hook for compliance corrections. Decision: 4h TTL + admin endpoint to "
        "purge per-member.",
        cluster="decision-w6-cache",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=8,
        day=3,
        hour=11,
        kind="decision",
        title="Claims viewer: read-only at launch",
        summary="decision proposed: claims viewer ships read-only in v1; dispute flow in v2",
        body="Sandra/Tom debate (pre-Sandra) over the claims-viewer scope. Initial spec had a "
        "dispute-initiate flow. Marcus estimated 4-6 extra weeks for the dispute workflow "
        "plus integration with the claims-management system. Tom agreed to defer. "
        "Decision: read-only at launch.",
        cluster="decision-w8-claims",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=9,
        day=2,
        hour=14,
        kind="decision",
        title="Find-a-doctor: reuse existing provider directory API",
        summary="decision proposed: reuse existing PD-API rather than rebuild",
        body="Two paths: (a) build a new search service over our own index, or (b) reuse the "
        "existing provider-directory API the call-center uses. (b) wins on time-to-launch "
        "despite the legacy API's brittleness. Lisa committed to standing up a freshness "
        "monitor. Decision: reuse PD-API with monitoring.",
        cluster="decision-w9-pdapi",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=11,
        day=3,
        hour=10,
        kind="decision",
        title="Pilot cohort: 500 employer-group members from one large account",
        summary="decision proposed: pilot with 500 members from one employer group",
        body="Patricia and Tom converged on starting with a single large employer-group "
        "(NorthStar Manufacturing, ~3k members total) and inviting 500 to the pilot. "
        "Better signal than a broad random sample at the cost of generalizability. "
        "Decision: pilot cohort = 500 NorthStar members.",
        cluster="decision-w11-cohort",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=12,
        day=4,
        hour=15,
        kind="decision",
        title="Pen-test vendor: Bishop Fox",
        summary="decision proposed: Bishop Fox engaged for pre-launch pen test",
        body="Three vendors quoted. Bishop Fox came in highest but had the strongest healthcare "
        "track record and could fit the W23-W24 window. David Liu (after his W14 onboard) "
        "endorsed. Decision: Bishop Fox, scope = portal + 3 integrations, $85k.",
        cluster="decision-w12-pentest",
        accept_decision=True,
    ),
    # ---- W13-16 Build — 2 decisions, cycle creeping to 5d ----
    ScenarioEvent(
        week=13,
        day=2,
        hour=11,
        kind="decision",
        title="Observability: Datadog over OpenTelemetry self-host",
        summary="decision proposed: Datadog APM + logs, defer self-host",
        body="Lisa preferred a self-hosted OTel collector + Grafana stack. Marcus argued the "
        "build phase couldn't absorb the infrastructure work. Datadog wins for speed-to-"
        "value with a 12-month buyout if needed. Decision: Datadog.",
        cluster="decision-w13-observability",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=15,
        day=4,
        hour=16,
        kind="decision",
        title="Accessibility audit: Level Access engaged",
        summary="decision proposed: Level Access for WCAG 2.2 AA audit",
        body="Decision dragged for ~5d as Sandra (newly onboarded) wanted to re-scope. Final "
        "call: Level Access for the WCAG 2.2 AA audit, with one mid-build review and one "
        "pre-launch. Decision: Level Access, $42k.",
        cluster="decision-w15-a11y",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=15,
        day=2,
        hour=11,
        kind="decision",
        title="Eligibility cache hot-cohort warming",
        summary="decision proposed: pre-warm eligibility cache for pilot cohort",
        body="To shave latency on the pilot cohort logins, Marcus proposed a nightly pre-warm "
        "job for the 500 NorthStar members. Lisa concerned about job duration; agreed to "
        "incremental warming. Decision: nightly incremental pre-warm, exclusive to pilot "
        "cohort for v1.",
        cluster="decision-w15-cache-warm",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=16,
        day=3,
        hour=10,
        kind="decision",
        title="Support runbook ownership: BlueState call-center",
        summary="decision proposed: BlueState call-center owns tier-1 portal support",
        body="Tier-1 support ownership clarified: BlueState's existing call-center handles "
        "tier-1 portal questions; DeployAI on-call rotation covers tier-2 incidents. "
        "Marcus to draft runbook by W20. Decision: BlueState owns tier-1.",
        cluster="decision-w16-support-ownership",
        accept_decision=True,
    ),
    # ---- W17-19 SILENCE — 0 decisions ----
    # ---- W20-24 Pilot prep — decisions slow to ~8d ----
    ScenarioEvent(
        week=20,
        day=3,
        hour=11,
        kind="decision",
        title="Pilot start delayed by 2 weeks",
        summary="decision proposed: pilot launch slipped from W22 to W24",
        body="Combination of the W14 stakeholder churn (Sandra's re-scope), the W17-19 "
        "contractor handoff silence, and Bishop Fox's late finding pushed the pilot "
        "launch back. Patricia signed off after a long Friday call. Decision: pilot "
        "launches W24, not W22.",
        cluster="decision-w20-pilot-slip",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=22,
        day=2,
        hour=14,
        kind="decision",
        title="Member-message PHI scope: opt-in required for clinical notes",
        summary="decision proposed: clinical-note delivery requires explicit opt-in",
        body="Raj + David Liu converged on a tighter opt-in model than the spec originally "
        "called for. Tom (pre-departure) had wanted clinical notes by default. Sandra "
        "agreed with Raj. Cycle was ~8 days because Mark Thompson (CDO) was looped in late. "
        "Decision: explicit opt-in for clinical notes.",
        cluster="decision-w22-phi-scope",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=23,
        day=1,
        hour=10,
        kind="decision",
        title="Pilot-cohort communications cadence approved",
        summary="decision proposed: pre-pilot, invite, follow-up cadence ratified",
        body="Comms cadence ratified by Patricia + Sandra: pre-pilot heads-up 5d out, invite "
        "24h before access, follow-up 48h post. Cycle was ~8 days as comms team and Raj "
        "had to align on PHI-handling language for the email body. Accepted.",
        cluster="decision-w23-comms-cadence",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=24,
        day=1,
        hour=10,
        kind="decision",
        title="Bishop Fox finding remediation acceptance",
        summary="decision proposed: accept proposed remediation plan for 2 high + 4 medium findings",
        body="David walked the remediation plan for the Bishop Fox findings. Accepted with the "
        "3 lows documented as accepted-risk. Cycle ~8 days due to retest scheduling.",
        cluster="decision-w24-pentest-remediation",
        accept_decision=True,
    ),
    # Rejected proposals concentrated in W23-24 to drive extractor_acceptance_drift.
    # 14d window @ end W24 catches these 6 rejects + the W23-24 accepts (low rate);
    # 30d baseline reaches back to W21 + earlier W22 accepts (high rate). Drop > 25pp.
    ScenarioEvent(
        week=23,
        day=1,
        hour=11,
        kind="decision",
        title="(REJECTED) Auto-enroll all 3k NorthStar members at pilot",
        summary="decision proposed: auto-enroll entire 3k NorthStar block",
        body="Tom's old plan resurfaced — auto-enroll the full NorthStar employer group rather "
        "than the 500-member pilot cohort. Sandra and Raj rejected on the consent risk and "
        "the spike in support load. Rejected.",
        cluster="decision-w23-auto-enroll",
        rejects_acceptance=True,
    ),
    ScenarioEvent(
        week=23,
        day=1,
        hour=14,
        kind="decision",
        title="(REJECTED) Add Spanish-language member intake at pilot",
        summary="decision proposed: ship Spanish UI at pilot",
        body="Sandra raised adding Spanish member intake at pilot. Rejected as out-of-scope for "
        "v1 — translation QA cannot fit the window. Logged as v2 P0.",
        cluster="decision-w23-spanish",
        rejects_acceptance=True,
    ),
    ScenarioEvent(
        week=23,
        day=3,
        hour=10,
        kind="decision",
        title="(REJECTED) Skip dual-region failover drill before launch",
        summary="decision proposed: defer DR drill to post-launch",
        body="Lisa's team was overcommitted in W23 and proposed deferring the disaster-recovery "
        "failover drill. David Liu and Raj rejected — given the W22 PHI-scope decision the "
        "DR validation cannot slip. Rejected.",
        cluster="decision-w23-dr-skip",
        rejects_acceptance=True,
    ),
    ScenarioEvent(
        week=23,
        day=4,
        hour=11,
        kind="decision",
        title="(REJECTED) Loosen MFA to once-per-30-day",
        summary="decision proposed: relax MFA enforcement from every-session to 30d",
        body="Engineering noticed a friction signal in the staging UX and proposed weakening "
        "MFA. David Liu and Raj rejected immediately; MFA cadence stays per-session.",
        cluster="decision-w23-mfa-loosen",
        rejects_acceptance=True,
    ),
    ScenarioEvent(
        week=24,
        day=1,
        hour=10,
        kind="decision",
        title="(REJECTED) Replace claims-viewer with embedded iframe",
        summary="decision proposed: embed legacy claims UI via iframe at launch",
        body="Engineering raised an iframe shortcut at the W24 status review. The team rejected "
        "it on UX consistency and the security review burden. Rejected.",
        cluster="decision-w24-iframe",
        rejects_acceptance=True,
    ),
    ScenarioEvent(
        week=24,
        day=2,
        hour=11,
        kind="decision",
        title="(REJECTED) Add provider-rating widget in v1",
        summary="decision proposed: provider 1-5 star rating widget at launch",
        body="Mark Thompson (CDO) proposed a provider-rating widget for v1 to start data "
        "capture early. Sandra rejected — adds a regulatory review cycle the launch "
        "window cannot absorb.",
        cluster="decision-w24-ratings",
        rejects_acceptance=True,
    ),
    # ---- W25-26 Pre-launch ----
    ScenarioEvent(
        week=25,
        day=3,
        hour=10,
        kind="decision",
        title="Launch comms: pre-pilot member email 5 days before invite",
        summary="decision proposed: send pre-pilot heads-up email 5 days before invite",
        body="Communications cadence locked: pre-pilot heads-up email 5 days before the invite, "
        "invite link 24h before access opens, follow-up at 48h post-access. Decision: "
        "approved.",
        cluster="decision-w25-comms",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=26,
        day=2,
        hour=15,
        kind="decision",
        title="Go/no-go: GO for pilot launch",
        summary="decision proposed: GO decision for pilot launch",
        body="All seven launch criteria green (pen-test, DR drill, accessibility audit, "
        "monitoring, opt-in flow, support runbooks, member-comms). Decision: GO.",
        cluster="decision-w26-go",
        accept_decision=True,
    ),
]


# Extractor noise — small extractor-emitted proposals (not full decisions) that
# represent the matrix-extractor flagging system/stakeholder additions automatically.
# Concentrated W20-21 and accepted at high rate so the trailing 30d baseline for
# extractor_acceptance_drift sits well above the W22-24 reject cluster.
EXTRACTOR_NOISE: list[ScenarioEvent] = [
    ScenarioEvent(
        week=20,
        day=2,
        hour=11,
        kind="extractor_proposal",
        title="System node proposed: Acme Build (contractor)",
        summary="extractor proposed: add Acme Build as system/contractor node",
        body="Matrix extractor flagged the contractor handoff narrative. Auto-proposed adding "
        "Acme Build as a system-relationship node.",
        cluster="extractor-w20-acme",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=20,
        day=3,
        hour=14,
        kind="extractor_proposal",
        title="Stakeholder edge proposed: David Liu → Bishop Fox engagement",
        summary="extractor proposed: David Liu owns pen-test scope",
        body="Extractor surfaced an edge between David Liu (W14 add) and the Bishop Fox pen-test commitment.",
        cluster="extractor-w20-david-edge",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=20,
        day=5,
        hour=10,
        kind="extractor_proposal",
        title="Commitment node proposed: Pilot launch by W24",
        summary="extractor proposed: pilot-by-W24 as commitment node",
        body="Extractor flagged the slip-decision narrative and proposed the new W24 pilot "
        "date as a tracked commitment.",
        cluster="extractor-w20-commitment",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=21,
        day=1,
        hour=11,
        kind="extractor_proposal",
        title="Stakeholder node proposed: Mark Thompson (CDO)",
        summary="extractor proposed: Mark Thompson stakeholder node",
        body="Extractor surfaced Patricia's email and proposed adding the new CDO as a stakeholder.",
        cluster="extractor-w21-mark",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=21,
        day=2,
        hour=15,
        kind="extractor_proposal",
        title="Risk node proposed: identity migration data quality",
        summary="extractor proposed: identity-quality risk node",
        body="Extractor pulled this risk from Marcus's dry-run field note.",
        cluster="extractor-w21-identity-risk",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=21,
        day=3,
        hour=11,
        kind="extractor_proposal",
        title="System edge proposed: cache → eligibility-API",
        summary="extractor proposed: cache→eligibility edge",
        body="Extractor refining matrix edges flagged a missing dependency.",
        cluster="extractor-w21-cache-edge",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=21,
        day=4,
        hour=14,
        kind="extractor_proposal",
        title="Stakeholder edge proposed: Sandra → product scope",
        summary="extractor proposed: Sandra Kim owns scope decisions",
        body="Extractor surfaced repeated Sandra references and proposed an ownership edge.",
        cluster="extractor-w21-sandra-edge",
        accept_decision=True,
    ),
    ScenarioEvent(
        week=21,
        day=5,
        hour=10,
        kind="extractor_proposal",
        title="Risk node proposed: shared ArcGIS dependency",
        summary="extractor proposed: shared infra dependency risk",
        body="Extractor flagged a passing mention of shared infra and proposed a tracking risk node.",
        cluster="extractor-w21-arcgis-risk",
        accept_decision=True,
    ),
]


# Risks: insight_opened / insight_closed with detail.node_type=risk
RISKS_OPENED: list[ScenarioEvent] = [
    # W5-12 — 3 risks opened
    ScenarioEvent(
        week=6,
        day=2,
        hour=14,
        kind="risk_opened",
        title="Eligibility API rate-limit shortfall",
        summary="risk opened: eligibility-API rate limit too low for portal scale",
        body="Existing eligibility endpoint is capped at 50 rps. Portal traffic modeling shows "
        "a peak of 180 rps at member-login bursts (e.g. enrollment season). Need rate "
        "headroom or aggressive caching.",
        cluster="risk-eligibility-rate",
    ),
    ScenarioEvent(
        week=8,
        day=3,
        hour=11,
        kind="risk_opened",
        title="Provider directory data staleness",
        summary="risk opened: PD-API monthly refresh cadence too slow",
        body="The provider-directory API refreshes monthly. Members who get incorrect in-"
        "network info could be a regulatory exposure. Need a freshness monitor and a "
        "stronger upstream-update SLA.",
        cluster="risk-pd-staleness",
    ),
    ScenarioEvent(
        week=11,
        day=4,
        hour=10,
        kind="risk_opened",
        title="Pilot cohort generalizability",
        summary="risk opened: pilot cohort is single employer group, may not represent broader member base",
        body="The 500-member NorthStar pilot cohort is one employer group — younger-skewing "
        "manufacturing workforce. Results may not generalize to the broader member base "
        "(more retirees, more chronic conditions). Need a sensitivity analysis before "
        "general launch.",
        cluster="risk-cohort-bias",
    ),
    # W13-16 build phase — 2 added
    ScenarioEvent(
        week=14,
        day=4,
        hour=15,
        kind="risk_opened",
        title="Tom Reyes departure leaves spec gaps",
        summary="risk opened: stakeholder churn (Tom departure) leaves unresolved scope items",
        body="Tom departed mid-flight. Three open scope decisions were live in his queue: SMS "
        "fallback, dispute-flow re-look, and claims-export format. Need Sandra to re-"
        "ratify or close.",
        cluster="risk-tom-spec-gap",
    ),
    ScenarioEvent(
        week=16,
        day=2,
        hour=11,
        kind="risk_opened",
        title="Datadog cost overrun trajectory",
        summary="risk opened: observability spend trending above budget",
        body="One month into Datadog and the log volume is already at 60% of the annual "
        "contract. Need a sampling strategy or we hit the contract cap by W20.",
        cluster="risk-datadog-cost",
    ),
    # W20-22 risk burst — 8 risks tightly clustered in W21-22 so a 14d analyzer
    # window @ end of W22 catches all 8 (need > 5 net for risk_open_rate).
    ScenarioEvent(
        week=22,
        day=1,
        hour=10,
        kind="risk_opened",
        title="HIPAA member-message audit-log gap",
        summary="risk opened: message audit-log retention shorter than HIPAA minimum",
        body="Raj's review of the message subsystem flagged that the audit log defaults to 90d "
        "retention. HIPAA requires 6 years for PHI access logs. Need to extend retention "
        "or move to a long-term archive before pilot.",
        cluster="risk-hipaa-audit",
    ),
    ScenarioEvent(
        week=22,
        day=1,
        hour=14,
        kind="risk_opened",
        title="Pen-test schedule vs pilot launch window",
        summary="risk opened: pen-test results may not land before pilot go-live",
        body="Bishop Fox finishes the pen test in W24. Pilot was originally W22. Cannot launch "
        "with un-remediated findings. (This is why pilot slipped — see decision-w20-pilot-"
        "slip.)",
        cluster="risk-pentest-slip",
    ),
    ScenarioEvent(
        week=22,
        day=1,
        hour=16,
        kind="risk_opened",
        title="Member identity migration data quality",
        summary="risk opened: identity migration found ~3% dirty records",
        body="The identity-data migration dry-run surfaced ~3% of member records with "
        "duplicates, missing date-of-birth, or invalid email. Need a remediation pass or "
        "those members can't log in to the portal.",
        cluster="risk-identity-quality",
    ),
    ScenarioEvent(
        week=22,
        day=2,
        hour=10,
        kind="risk_opened",
        title="DR drill not yet scheduled",
        summary="risk opened: disaster-recovery failover drill not scheduled",
        body="Per the dual-region decision (decision-w3-regions), we owe a documented DR "
        "failover drill before launch. Not on the calendar yet. Needs to happen in W23 or "
        "W24.",
        cluster="risk-dr-drill",
    ),
    ScenarioEvent(
        week=22,
        day=2,
        hour=14,
        kind="risk_opened",
        title="Eligibility cache invalidation hook untested",
        summary="risk opened: admin-triggered cache invalidation has no test coverage",
        body="The 4h eligibility cache (decision-w6-cache) has a manual-invalidation endpoint "
        "for compliance corrections. Coverage report shows no integration tests on that "
        "path. Raj wants validation before a member's eligibility change is held in stale "
        "cache.",
        cluster="risk-cache-invalidate",
    ),
    ScenarioEvent(
        week=22,
        day=3,
        hour=10,
        kind="risk_opened",
        title="Sandra Kim re-baseline may reopen v1 scope",
        summary="risk opened: new VP Product re-baseline may slip scope",
        body="Sandra Kim has signaled she wants to re-baseline the v1 scope after she's been on "
        "the ground for 8 weeks. That review lands W22-23. Risk of late additions that "
        "push beyond the W24 pilot date.",
        cluster="risk-sandra-rebaseline",
    ),
    ScenarioEvent(
        week=22,
        day=4,
        hour=14,
        kind="risk_opened",
        title="Performance regression in claims-viewer pagination",
        summary="risk opened: claims-viewer p95 latency exceeds 2s SLA at 50+ claims",
        body="Performance test on a member with 80 historical claims shows p95 latency of "
        "3.4s — over the 2s SLA. Likely query plan issue. Engineering investigating but "
        "may need an index change in production.",
        cluster="risk-claims-perf",
    ),
    ScenarioEvent(
        week=22,
        day=5,
        hour=10,
        kind="risk_opened",
        title="Support-team training behind schedule",
        summary="risk opened: BlueState call-center hasn't begun portal training",
        body="Customer-support training was scheduled to start W19 but the contractor handoff "
        "(W17-19 silence period) delayed kickoff. Currently 0% trained. Need at least 50% "
        "of the pilot-supporting reps trained before launch.",
        cluster="risk-support-training",
    ),
]

RISKS_CLOSED: list[ScenarioEvent] = [
    # W5-12 — 2 risks closed (cohort + PD staleness mitigated)
    ScenarioEvent(
        week=10,
        day=2,
        hour=14,
        kind="risk_closed",
        title="Eligibility API rate-limit shortfall — mitigated",
        summary="risk closed: eligibility cache decision absorbs rate-limit risk",
        body="After the W6 cache decision, the modeled peak rate against the live API drops "
        "from 180rps to ~28rps. Within the 50rps cap with headroom. Closing.",
        risk_close_of="risk-eligibility-rate",
    ),
    ScenarioEvent(
        week=12,
        day=3,
        hour=10,
        kind="risk_closed",
        title="PD-staleness — mitigated by freshness monitor",
        summary="risk closed: PD-API freshness monitor in production",
        body="Lisa's team shipped a freshness monitor that alerts when the PD-API last-refresh "
        "drifts >35 days. Plus we negotiated a 7-day worst-case refresh SLA with the "
        "upstream team. Closing.",
        risk_close_of="risk-pd-staleness",
    ),
    # W25-26 — 3 risks closed
    ScenarioEvent(
        week=25,
        day=2,
        hour=11,
        kind="risk_closed",
        title="DR drill — passed",
        summary="risk closed: DR failover drill completed successfully",
        body="W24 DR drill ran end-to-end. Failover to us-west-2 took 7m32s, recovery 11m. "
        "Within the < 30m target. Closing.",
        risk_close_of="risk-dr-drill",
    ),
    ScenarioEvent(
        week=25,
        day=4,
        hour=14,
        kind="risk_closed",
        title="Pen-test findings — remediated",
        summary="risk closed: Bishop Fox findings remediated, retest clean",
        body="All Bishop Fox findings (2 high, 4 medium, 11 low) closed. Retest scan clean. Closing.",
        risk_close_of="risk-pentest-slip",
    ),
    ScenarioEvent(
        week=26,
        day=2,
        hour=10,
        kind="risk_closed",
        title="Support training — completed",
        summary="risk closed: call-center training at 78% — above threshold",
        body="78% of pilot-supporting reps completed portal training, exceeding the 50% bar. Closing.",
        risk_close_of="risk-support-training",
    ),
]


# Narrative/intake events — emails, meeting notes, manual captures.
# These supply the bulk of source_kind counts (~78 email_ingest, ~24 meeting_webhook,
# ~18 manual_capture) and provide upstream causal-chain anchors for decisions.
NARRATIVE: list[ScenarioEvent] = [
    # ============================================================
    # W1-4 DISCOVERY — ~25 emails, 4 meetings, 3 captures
    # ============================================================
    ScenarioEvent(
        week=1,
        day=1,
        hour=9,
        kind="email_ingest",
        summary="Jamie → Patricia: BlueState kickoff intro",
        body="From: Jamie Park <jamie.park@deployai.com>\n"
        "To: Patricia Vance <patricia.vance@bluestatehealth.com>\n"
        "Subject: BlueState member-portal modernization — kickoff next week\n\n"
        "Patricia,\n\nGreat to reconnect after the AHIP panel. Confirming our kickoff "
        "for Monday 9am ET. Sarah Chen (deployment strategist) and Marcus Rivera (FDE) "
        "will join. We're proposing a 26-week phased build with a pilot in week 22 — "
        "we'll walk you through the rationale on the call.\n\nDeck attached. Looking "
        "forward.\n\nJamie",
        cluster="email-w1-jamie-intro",
    ),
    ScenarioEvent(
        week=1,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Kickoff meeting — BlueState x DeployAI",
        body="Meeting: BlueState Health x DeployAI — kickoff\n"
        "Attendees: Patricia Vance (CMO), Tom Reyes (VP Product), Lisa Wong (Eng Dir), "
        "Sarah Chen, Marcus Rivera, Jamie Park\n\n"
        "Patricia opened with the business context: member-portal NPS has been "
        "underwater for 3 years, and CMS-issued star-ratings now weight digital "
        "experience. Target: portal NPS +15 by end of FY27.\n\nTom pushed for a big-"
        "bang launch by Q3. Sarah laid out the phased model: 4w discovery, 8w design, "
        "4w build, 3w silence (planned contractor handoff), 5w pilot prep, 2w launch "
        "prep. Tom conceded after Lisa raised the eligibility/claims integration "
        "complexity.\n\nDecision: phased model. Next: scoping deep-dive Thursday.",
        cluster="meeting-w1-kickoff",
    ),
    ScenarioEvent(
        week=1,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Lisa → Marcus: integration inventory",
        body="From: Lisa Wong <lisa.wong@bluestatehealth.com>\n"
        "To: Marcus Rivera <marcus.rivera@deployai.com>\n"
        "Subject: Integration inventory — first cut\n\n"
        "Marcus,\n\nPer Monday's kickoff, here are the integrations we'll need to "
        "touch:\n\n1. Eligibility (mainframe, MQ Series, ~800ms latency)\n2. Claims "
        "(Oracle-backed, REST API since 2023)\n3. Provider directory (third-party "
        "SaaS, monthly refresh)\n4. Member identity (Okta, our SSO)\n5. Member "
        "messaging (in-house, currently web-only)\n\nThe eligibility one is the "
        "scariest. Rate-limited at 50rps, mainframe owners are conservative about "
        "any volume increase. We'll need to talk caching early.\n\nLisa",
        cluster="email-w1-integration-inventory",
    ),
    ScenarioEvent(
        week=1,
        day=4,
        hour=14,
        kind="meeting_webhook",
        summary="Scoping deep-dive — feature inventory",
        body="Meeting: Scoping deep-dive\n"
        "Attendees: Sarah, Marcus, Tom, Lisa, Patricia (partial)\n\n"
        "Walked the proposed v1 feature set: identity + login, eligibility view, "
        "claims read-only, find-a-doctor, member messaging (in-portal). Tom wanted "
        "SMS for messages; Sarah flagged the PHI consent gap.\n\nPatricia (joined "
        "for last 30m) approved the v1 scope on the condition that pen-test happens "
        "before the pilot, and accessibility (WCAG 2.2 AA) is non-negotiable.\n\n"
        "Action items: Marcus to draft integration spike plan. Sarah to pull a vendor "
        "shortlist for pen-test + a11y audit.",
        cluster="meeting-w1-scoping",
    ),
    ScenarioEvent(
        week=1,
        day=5,
        hour=10,
        kind="email_ingest",
        summary="Marcus → Lisa: identity-provider tradeoffs",
        body="From: Marcus Rivera\nTo: Lisa Wong\nSubject: Okta vs Auth0 — quick read\n\n"
        "Lisa,\n\nQuick note before our Tuesday call. Both Okta and Auth0 will work "
        "for member identity. Okta wins on three things for BlueState: (1) you already "
        "run it for employees so the ops model is known, (2) Okta has a signed BAA on "
        "file already with you, (3) the price delta is meaningful at 2M members.\n\n"
        "Auth0 would win on customizability of the login flow but I don't think that "
        "matters for this v1.\n\nProposing we lock Okta on Tuesday.\n\nMarcus",
        cluster="email-w1-okta-tradeoff",
    ),
    ScenarioEvent(
        week=2,
        day=1,
        hour=9,
        kind="manual_capture",
        summary="Field note: BlueState data center tour",
        body="Field note — Marcus, BlueState ops center tour\n\n"
        "Spent 4 hours with the eligibility-mainframe team. Two takeaways:\n\n"
        "1. The 50rps cap is real and not negotiable. Their backplane saturates at "
        "~70rps and they've had two incidents in 18 months at that level. They will "
        "not raise the cap for our launch.\n\n2. The team is run by Hector Diaz "
        "(eligibility platform lead). He's been there 24 years and is the only one "
        "who actually understands the message-format quirks. Key-person risk on the "
        "BlueState side, parallel to our own dependency.\n\nCaching is the answer. "
        "Going to propose 4h TTL with manual purge — should keep us comfortably "
        "under the cap.",
        cluster="capture-w2-datacenter",
    ),
    ScenarioEvent(
        week=2,
        day=2,
        hour=16,
        kind="meeting_webhook",
        summary="Identity-provider decision call",
        body="Meeting: Identity provider selection\n"
        "Attendees: Lisa Wong, Marcus Rivera, Tom Reyes (partial)\n\n"
        "Reviewed Marcus's Okta-vs-Auth0 memo. Lisa confirmed Okta is already the "
        "employee SSO and the existing BAA covers a wider scope than Auth0 would. "
        "Tom asked about migration cost — Lisa said zero net-new infra.\n\n"
        "Decision: Okta. Lisa to provision a member-realm tenant by W4.",
        cluster="meeting-w2-okta-decision",
    ),
    ScenarioEvent(
        week=2,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Patricia → Sarah: weekly check-in cadence",
        body="From: Patricia Vance\nTo: Sarah Chen\nSubject: Weekly check-in cadence\n\n"
        "Sarah,\n\nLet's lock a recurring weekly check-in. I'd like Fridays 8am ET, "
        "30 min, just you and me, no slides. Plus the full steering committee biweekly "
        "starting W3.\n\nPatricia",
        cluster="email-w2-cadence",
    ),
    ScenarioEvent(
        week=2,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: weekly status W2",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Weekly status — W2\n\n"
        "Patricia,\n\nW2 summary:\n- Okta locked for identity (Lisa provisioning)\n"
        "- Marcus on-site at the eligibility data center, recommending 4h cache\n"
        "- Integration inventory complete (5 systems)\n- Pen-test vendor RFP going "
        "out tomorrow\n\nNo blockers. Steering committee meeting next Wednesday.\n\n"
        "Sarah",
        cluster="email-w2-status",
    ),
    ScenarioEvent(
        week=2,
        day=5,
        hour=10,
        kind="email_ingest",
        summary="Tom → Sarah: SMS push-back",
        body="From: Tom Reyes\nTo: Sarah Chen\nCc: Patricia Vance\nSubject: SMS in v1 — "
        "let's revisit\n\nSarah,\n\nI've been thinking about the SMS deferral. Half "
        "our members are over 55 and email engagement is poor. Can we look at a "
        "limited SMS rollout for appointment reminders only? PHI-light. Open to a "
        "narrower scope.\n\nTom",
        cluster="email-w2-tom-sms",
    ),
    ScenarioEvent(
        week=3,
        day=1,
        hour=9,
        kind="email_ingest",
        summary="Sarah → Tom: SMS PHI scope concerns",
        body="From: Sarah Chen\nTo: Tom Reyes\nSubject: Re: SMS in v1 — let's revisit\n\n"
        "Tom,\n\nFair point on the over-55 cohort. Appointment reminders are arguably "
        "PHI-adjacent though (the existence of an appointment implies care). Want to "
        "pull Raj into a quick call before W4 to scope what 'PHI-light' actually "
        "means here?\n\nSarah",
        cluster="email-w3-sarah-sms-reply",
    ),
    ScenarioEvent(
        week=3,
        day=2,
        hour=14,
        kind="email_ingest",
        summary="Patricia → all: compliance lead joining",
        body="From: Patricia Vance\nTo: project-bluestate@deployai.com; tom.reyes@...; "
        "lisa.wong@...\nSubject: Adding Raj Patel (compliance) to the working group\n\n"
        "Team,\n\nPulling Raj Patel in as compliance lead. He'll own the BAA, the "
        "HIPAA review, and the data-handling sign-off. Effective today.\n\nPatricia",
        cluster="email-w3-raj-add",
    ),
    ScenarioEvent(
        week=3,
        day=3,
        hour=11,
        kind="meeting_webhook",
        summary="Compliance kickoff with Raj",
        body="Meeting: Compliance kickoff — Raj Patel + DeployAI\n"
        "Attendees: Raj Patel, Sarah Chen, Marcus Rivera, Tom Reyes\n\n"
        "Raj's first formal session. Three big asks:\n1. Dual-region for PHI store "
        "(non-negotiable)\n2. Member-messaging PHI scope to be defined explicitly "
        "before any build\n3. Audit log retention >= 6 years for PHI access\n\n"
        "On SMS: Raj's read is that appointment reminders are PHI and require "
        "explicit opt-in. Tom's compromise position not viable without a consent "
        "infrastructure that doesn't exist yet.\n\nDecision implied: SMS deferred to "
        "v2 (formal call to come Thursday).",
        cluster="meeting-w3-compliance",
    ),
    ScenarioEvent(
        week=3,
        day=4,
        hour=11,
        kind="email_ingest",
        summary="Raj → Marcus: regions formal proposal",
        body="From: Raj Patel\nTo: Marcus Rivera\nSubject: Dual-region PHI store — formal "
        "proposal\n\nMarcus,\n\nFormalizing my Wednesday ask. us-east-1 primary, "
        "us-west-2 passive, RPO < 5 min, RTO < 30 min. Documented runbook for "
        "failover, drilled at least quarterly post-launch and once before launch.\n\n"
        "Patricia is aligned. Need your formal sign-off + cost impact by end of week.\n\n"
        "Raj",
        cluster="email-w3-raj-regions",
    ),
    ScenarioEvent(
        week=3,
        day=5,
        hour=14,
        kind="email_ingest",
        summary="Sarah → Patricia: weekly status W3 + regions",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Weekly status — W3\n\n"
        "Patricia,\n\nW3 summary:\n- Raj onboarded; compliance kickoff Wednesday\n"
        "- Regions decision pending (dual-region us-east-1 + us-west-2 — Raj's "
        "proposal). Marcus drafting cost analysis.\n- SMS deferred to v2 (call "
        "Thursday)\n- Maya Singh (procurement) joining W4 per Tom\n\nNo blockers.\n\n"
        "Sarah",
        cluster="email-w3-status",
    ),
    ScenarioEvent(
        week=4,
        day=1,
        hour=10,
        kind="manual_capture",
        summary="Field note: Raj 1:1 — compliance posture",
        body="Field note — Sarah, 1:1 with Raj Patel\n\n"
        "Raj is sharp and conservative. He's been burned twice (previous employer + "
        "BlueState's last vendor) by under-scoped HIPAA work. Wants every PHI "
        "decision in writing.\n\nHe's not anti-velocity but he'll be the loudest "
        "voice against shortcuts. Sandra (if she joins later) will need to be "
        "aligned with him from day one or there will be friction.\n\nKey signal: he "
        "specifically asked about our exit plan if we end the engagement. Wants the "
        "data-portability story documented in the MSA.",
        cluster="capture-w4-raj-1on1",
    ),
    ScenarioEvent(
        week=4,
        day=2,
        hour=14,
        kind="meeting_webhook",
        summary="Steering committee — first formal session",
        body="Meeting: Steering committee #1\n"
        "Attendees: Patricia, Tom, Lisa, Raj, Sarah, Marcus, Jamie\n\n"
        "Reviewed and ratified four decisions: engagement model (phased), Okta IDP, "
        "dual-region PHI store, in-portal messaging only for v1 (SMS deferred).\n\n"
        "Patricia approved all four. Tom dissented on SMS but accepted the call.\n\n"
        "Next: Maya Singh joining for procurement. Phase 2 (design) kicks off W5.",
        cluster="meeting-w4-steering",
    ),
    ScenarioEvent(
        week=4,
        day=3,
        hour=14,
        kind="email_ingest",
        summary="Patricia → Sarah: messaging decision formal",
        body="From: Patricia Vance\nTo: Sarah Chen\nCc: Tom Reyes, Raj Patel\nSubject: "
        "Messaging scope — formal call\n\nSarah,\n\nFormalizing the call from yesterday's "
        "steering: in-portal messaging only for v1. SMS deferred to v2. Tom is on board "
        "even though it's not his preferred outcome.\n\nLet's start design Monday.\n\n"
        "Patricia",
        cluster="email-w4-msg-formal",
    ),
    ScenarioEvent(
        week=4,
        day=4,
        hour=10,
        kind="email_ingest",
        summary="Maya → Jamie: procurement intake",
        body="From: Maya Singh\nTo: Jamie Park\nSubject: MSA + procurement intake\n\n"
        "Jamie,\n\nMaya from BlueState supply chain. I'll be your procurement "
        "counterpart. To start: I need (1) your current MSA template, (2) any "
        "deviations you've negotiated with similar payer clients, (3) the standard "
        "data-handling addendum.\n\nLet's target signed MSA by W8.\n\nMaya",
        cluster="email-w4-maya-intake",
    ),
    ScenarioEvent(
        week=4,
        day=5,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: weekly status W4 + phase 1 wrap",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Weekly status — W4 (Phase 1 wrap)\n\n"
        "Patricia,\n\nPhase 1 wrap:\n- 4 decisions ratified at steering (engagement model, "
        "IDP, regions, messaging)\n- 5 stakeholders engaged (you, Tom, Lisa, Raj, Maya)\n"
        "- 5 integration systems inventoried\n- MSA conversation kicked off with Maya\n\n"
        "Phase 2 (design) kicks off Monday. First design session: eligibility cache.\n\n"
        "Sarah",
        cluster="email-w4-phase1-wrap",
    ),
    # Filler emails to reach ~25 events in W1-4
    ScenarioEvent(
        week=1,
        day=3,
        hour=15,
        kind="email_ingest",
        summary="Marcus → Lisa: integration spike plan",
        body="From: Marcus Rivera\nTo: Lisa Wong\nSubject: Integration spike plan\n\n"
        "Lisa,\n\nProposing the spike order: (1) Okta (1 week, low risk), "
        "(2) eligibility (2 weeks, highest risk), (3) claims (1 week, REST is "
        "clean), (4) PD-API (1 week, vendor docs are OK), (5) messaging (in-house, "
        "treat as build not spike). Start Monday W2.\n\nMarcus",
        cluster="email-w1-spike-plan",
    ),
    ScenarioEvent(
        week=2,
        day=1,
        hour=14,
        kind="email_ingest",
        summary="Lisa → Marcus: Hector's calendar",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Time with Hector\n\n"
        "Marcus,\n\nHector Diaz (eligibility lead) blocked 4h Tuesday for your data "
        "center visit. He's old-school — bring printed materials. No screen.\n\nLisa",
        cluster="email-w2-hector-cal",
    ),
    ScenarioEvent(
        week=2,
        day=2,
        hour=11,
        kind="email_ingest",
        summary="Marcus → Sarah: post-datacenter recap",
        body="From: Marcus Rivera\nTo: Sarah Chen\nSubject: Datacenter recap\n\n"
        "Sarah,\n\nQuick recap: Hector confirmed 50rps cap is firm. Hector himself "
        "is a single point of failure on the protocol quirks. Caching is the only "
        "credible path. Drafting the 4h-TTL proposal for W6 design.\n\nMarcus",
        cluster="email-w2-recap",
    ),
    ScenarioEvent(
        week=3,
        day=2,
        hour=9,
        kind="email_ingest",
        summary="Jamie → Patricia: pen-test RFP",
        body="From: Jamie Park\nTo: Patricia Vance\nSubject: Pen-test RFP shortlist\n\n"
        "Patricia,\n\nShortlist for the pre-launch pen test: Bishop Fox, NCC, "
        "Trail of Bits. Quotes due by W6. We'll bring you a recommendation in W12.\n\n"
        "Jamie",
        cluster="email-w3-pentest-rfp",
    ),
    ScenarioEvent(
        week=3,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Raj → Patricia: BAA status",
        body="From: Raj Patel\nTo: Patricia Vance\nCc: Maya Singh\nSubject: BAA — status\n\n"
        "Patricia,\n\nReviewed DeployAI's BAA template. Clean. Maya will redline "
        "and we should sign with the MSA in W8.\n\nRaj",
        cluster="email-w3-baa",
    ),
    ScenarioEvent(
        week=4,
        day=1,
        hour=14,
        kind="email_ingest",
        summary="Tom → Marcus: claims-system credentials",
        body="From: Tom Reyes\nTo: Marcus Rivera\nSubject: Claims API credentials\n\n"
        "Marcus,\n\nLisa will get you read-only API creds for claims by Friday. "
        "Sandbox first. Production access requires Raj sign-off and a separate "
        "ticket.\n\nTom",
        cluster="email-w4-claims-creds",
    ),
    ScenarioEvent(
        week=4,
        day=2,
        hour=11,
        kind="manual_capture",
        summary="Field note: Patricia 1:1 — leadership read",
        body="Field note — Jamie, 1:1 with Patricia\n\n"
        "Patricia is invested. She specifically said this engagement determines "
        "whether DeployAI gets the broader digital-experience rebuild contract "
        "next FY. Tom is enthusiastic but impatient. Lisa is competent and quiet — "
        "the engineering call is hers and she's reliable. Raj is the slow-down "
        "vector but for the right reasons.\n\nWatch Tom on scope creep. Watch Raj "
        "on velocity. Patricia is balancing both internally.",
        cluster="capture-w4-patricia-1on1",
    ),
    ScenarioEvent(
        week=4,
        day=4,
        hour=14,
        kind="email_ingest",
        summary="Sarah → Marcus: phase 2 design kickoff agenda",
        body="From: Sarah Chen\nTo: Marcus Rivera\nSubject: Phase 2 design kickoff agenda\n\n"
        "Marcus,\n\nMonday W5: kick off design phase. First topic — eligibility "
        "cache. Block 90 minutes with Lisa, Hector (if he'll come), Raj.\n\nSarah",
        cluster="email-w4-p2-kickoff",
    ),
    # ============================================================
    # W5-12 DESIGN — ~20 emails, 8 meetings, 6 captures
    # ============================================================
    ScenarioEvent(
        week=5,
        day=1,
        hour=10,
        kind="meeting_webhook",
        summary="Design kickoff — frontend stack debate",
        body="Meeting: Phase 2 kickoff — frontend stack\n"
        "Attendees: Sarah, Marcus, Lisa, Tom\n\n"
        "Lisa proposed SvelteKit (her team has experience). Marcus countered with "
        "Next.js based on hiring market and the existing component library. Tom "
        "neutral.\n\nDecision: Next.js + Tailwind. Lisa accepted with the caveat "
        "that her team gets training budget for the ramp-up.",
        cluster="meeting-w5-frontend",
    ),
    ScenarioEvent(
        week=5,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Lisa → Marcus: frontend ramp training budget",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Next.js training budget\n\n"
        "Marcus,\n\nPatricia approved $12k for Next.js training for my team. "
        "Three engineers will go through Vercel's enterprise course. Won't impact "
        "the W12 design-phase exit gate.\n\nLisa",
        cluster="email-w5-training",
    ),
    ScenarioEvent(
        week=5,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: weekly status W5",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Weekly status — W5\n\n"
        "Patricia,\n\nW5:\n- Frontend stack locked (Next.js + Tailwind)\n- "
        "Eligibility cache design session scheduled for W6\n- Lisa training "
        "budget approved\n- MSA redline in progress with Maya\n\nNo blockers.\n\n"
        "Sarah",
        cluster="email-w5-status",
    ),
    ScenarioEvent(
        week=6,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Eligibility cache design session",
        body="Meeting: Eligibility cache design\n"
        "Attendees: Marcus, Lisa, Raj, Sarah\n\n"
        "Walked through 4h TTL + admin-purge proposal. Raj insisted on the manual-"
        "purge hook for compliance corrections (e.g., a member's eligibility flips "
        "and we can't wait 4h). Lisa OK on infra burden.\n\nDecision: 4h TTL, "
        "admin-triggered per-member invalidation endpoint. Open: invalidation hook "
        "needs integration tests (logged as risk).",
        cluster="meeting-w6-cache",
    ),
    ScenarioEvent(
        week=6,
        day=3,
        hour=14,
        kind="email_ingest",
        summary="Raj → Sarah: cache invalidation MUST be tested",
        body="From: Raj Patel\nTo: Sarah Chen\nSubject: Cache invalidation — testing\n\n"
        "Sarah,\n\nThe 4h cache is fine but the invalidation hook is critical. If "
        "a member's eligibility changes due to a compliance correction and the "
        "system holds the stale value, that's a regulatory exposure for us.\n\n"
        "Please make sure the invalidation hook has explicit integration test "
        "coverage and that we exercise it in QA before launch.\n\nRaj",
        cluster="email-w6-raj-cache",
    ),
    ScenarioEvent(
        week=6,
        day=5,
        hour=11,
        kind="meeting_webhook",
        summary="Claims integration design",
        body="Meeting: Claims integration design\n"
        "Attendees: Marcus, Lisa, Tom\n\n"
        "Tom wanted full dispute-initiate flow at launch. Marcus estimated 4-6 "
        "weeks additional. Lisa flagged claims-management integration as messy. "
        "Tom agreed to defer dispute flow to v2. Read-only at launch.\n\n"
        "Open: claims-data export format (Tom wants CSV; Lisa wants Parquet for "
        "downstream analytics; punted to W8 follow-up).",
        cluster="meeting-w6-claims",
    ),
    ScenarioEvent(
        week=7,
        day=2,
        hour=10,
        kind="email_ingest",
        summary="Maya → Jamie: MSA redline returned",
        body="From: Maya Singh\nTo: Jamie Park\nSubject: MSA redline\n\n"
        "Jamie,\n\nRedline attached. Main asks:\n- 90-day data return + certified "
        "deletion (per Raj's compliance ask)\n- LD cap raised to $2M (your template "
        "had $500k)\n- 12-month notice for any PHI subprocessor change\n\nLet's "
        "discuss Thursday.\n\nMaya",
        cluster="email-w7-msa-redline",
    ),
    ScenarioEvent(
        week=7,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Jamie → Maya: redline response",
        body="From: Jamie Park\nTo: Maya Singh\nSubject: Re: MSA redline\n\n"
        "Maya,\n\nResponses:\n- 90-day return + deletion: agreed\n- LD cap $2M: "
        "agreed for direct damages, $5M aggregate\n- Subprocessor 12-month notice: "
        "agreed for PHI subprocessors only\n\nReady to sign W8 if you are.\n\nJamie",
        cluster="email-w7-redline-response",
    ),
    ScenarioEvent(
        week=8,
        day=2,
        hour=10,
        kind="email_ingest",
        summary="Sarah → all: phase 2 mid-point",
        body="From: Sarah Chen\nTo: Patricia, Tom, Lisa, Raj, Maya\nSubject: Phase 2 "
        "mid-point\n\nTeam,\n\nHalfway through design phase. Status:\n- 6 of 6 "
        "design sessions on track\n- Claims viewer decision (read-only) ratified\n"
        "- MSA signing W8\n- Pen-test vendor evaluation kicked off (decision W12)\n"
        "- No open risks beyond the W6 cache-invalidation test gap\n\nSarah",
        cluster="email-w8-midpoint",
    ),
    ScenarioEvent(
        week=8,
        day=3,
        hour=11,
        kind="meeting_webhook",
        summary="Claims viewer scope decision",
        body="Meeting: Claims viewer scope\n"
        "Attendees: Tom, Marcus, Lisa, Sarah\n\n"
        "Formalized the read-only decision. Tom asked one more time if dispute "
        "could fit; Marcus walked through the workflow integration cost. Tom "
        "accepted the deferral. Read-only at launch, dispute flow in v2.",
        cluster="meeting-w8-claims-scope",
    ),
    ScenarioEvent(
        week=8,
        day=5,
        hour=14,
        kind="email_ingest",
        summary="Maya → Jamie: MSA signed",
        body="From: Maya Singh\nTo: Jamie Park\nSubject: MSA — signed\n\nJamie,\n\nMSA "
        "and BAA both signed as of today. PDFs en route from procurement portal.\n\n"
        "Maya",
        cluster="email-w8-msa-signed",
    ),
    ScenarioEvent(
        week=9,
        day=2,
        hour=14,
        kind="meeting_webhook",
        summary="Find-a-doctor design session",
        body="Meeting: Provider directory / find-a-doctor design\n"
        "Attendees: Marcus, Lisa, Tom\n\n"
        "Two paths: rebuild over our own index (~8 weeks) vs reuse the existing "
        "PD-API the call center uses (~2 weeks but legacy). Reuse wins on speed. "
        "Lisa to stand up a freshness monitor as mitigation. Decision: reuse PD-API "
        "with monitoring.",
        cluster="meeting-w9-pd",
    ),
    ScenarioEvent(
        week=9,
        day=4,
        hour=10,
        kind="manual_capture",
        summary="Field note: Tom's frustration signals",
        body="Field note — Sarah, walking out of the W9 design review\n\n"
        "Tom is increasingly frustrated with the deferral of his preferred features "
        "(SMS, dispute flow). He's accepting the calls but his tone is shifting. He "
        "mentioned 'we should have hired CivicSoft instead' at one point as a joke "
        "that wasn't really a joke.\n\nPatricia is aware. We need to find Tom a win "
        "in W10-12 — maybe accelerate the find-a-doctor UX work he cares about.",
        cluster="capture-w9-tom-signals",
    ),
    ScenarioEvent(
        week=10,
        day=2,
        hour=10,
        kind="email_ingest",
        summary="Sarah → Tom: find-a-doctor UX acceleration",
        body="From: Sarah Chen\nTo: Tom Reyes\nSubject: Find-a-doctor UX — accelerating\n\n"
        "Tom,\n\nGiven you've championed the find-a-doctor experience from day one, "
        "we're going to pull the UX prototype forward into W11 (originally W14). "
        "Lisa's team has bandwidth. You'll see clickable Figma by W11.\n\nSarah",
        cluster="email-w10-tom-pd-ux",
    ),
    ScenarioEvent(
        week=10,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Tom → Sarah: thank you on PD acceleration",
        body="From: Tom Reyes\nTo: Sarah Chen\nSubject: Re: Find-a-doctor UX\n\n"
        "Sarah,\n\nAppreciate this. Makes a real difference. Let me know if the "
        "Figma needs a review session before W12 steering.\n\nTom",
        cluster="email-w10-tom-thanks",
    ),
    ScenarioEvent(
        week=11,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Pilot cohort design session",
        body="Meeting: Pilot cohort selection\n"
        "Attendees: Patricia, Tom, Sarah, Marcus\n\n"
        "Three options: (a) random 500-member cohort, (b) one employer group, "
        "(c) volunteer cohort. Patricia + Tom both leaned (b) NorthStar (their "
        "biggest single employer, ~3k members). Better signal at the cost of "
        "generalizability (raised as risk).\n\nDecision: 500 NorthStar members.",
        cluster="meeting-w11-cohort",
    ),
    ScenarioEvent(
        week=11,
        day=4,
        hour=11,
        kind="manual_capture",
        summary="Field note: PD-API vendor call",
        body="Field note — Marcus, call with PD-API vendor (HealthwayDirect)\n\n"
        "They confirmed the monthly refresh cadence is firm — engineering team has "
        "no roadmap for higher-frequency updates. We negotiated a 7-day worst-case "
        "manual refresh SLA for emergency corrections. Better than nothing.\n\n"
        "Recommendation: build the freshness monitor, log staleness > 35d, and "
        "treat the SLA call as the escalation path.",
        cluster="capture-w11-pd-vendor",
    ),
    ScenarioEvent(
        week=12,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Pen-test vendor decision",
        body="Meeting: Pen-test vendor selection\n"
        "Attendees: Jamie, Sarah, Marcus, Raj\n\n"
        "Bishop Fox: $85k, strong healthcare history, fits W23-24. NCC: $62k, "
        "broader scope, can't fit calendar. Trail of Bits: $94k, mostly cloud "
        "infra, weaker on app pen-test.\n\nDecision: Bishop Fox. Schedule W23-24.",
        cluster="meeting-w12-pentest",
    ),
    ScenarioEvent(
        week=12,
        day=3,
        hour=10,
        kind="email_ingest",
        summary="Sarah → Patricia: phase 2 wrap",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Phase 2 wrap\n\nPatricia,\n\n"
        "Design phase complete:\n- 6 design decisions ratified\n- 3 risks opened, 2 "
        "closed (eligibility-rate, PD-staleness)\n- MSA + BAA signed\n- Pen-test "
        "vendor locked\n- Acceptance/Stub-extract rate ~90%\n\nBuild kicks off "
        "Monday. Three risks remain (cohort generalizability, cache-invalidation "
        "testing, claims-export format).\n\nSarah",
        cluster="email-w12-phase2-wrap",
    ),
    # filler design phase
    ScenarioEvent(
        week=5,
        day=2,
        hour=14,
        kind="email_ingest",
        summary="Lisa → Marcus: Okta tenant provisioned",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Okta member-realm provisioned\n\n"
        "Marcus,\n\nMember-realm Okta tenant up. Sending you admin creds via 1Pass.\n\n"
        "Lisa",
        cluster="email-w5-okta-prov",
    ),
    ScenarioEvent(
        week=6,
        day=4,
        hour=10,
        kind="manual_capture",
        summary="Field note: cache TTL discussion w/ Hector",
        body="Field note — Marcus, follow-up call with Hector Diaz\n\n"
        "Walked Hector through the 4h cache proposal. He was initially nervous — "
        "had been burned by a previous portal vendor caching too aggressively. "
        "Walked through the admin-purge hook and the freshness implications.\n\n"
        "He's OK with 4h. Wanted 8h. We compromised at 4h with the admin endpoint.",
        cluster="capture-w6-hector",
    ),
    ScenarioEvent(
        week=7,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Lisa → Marcus: eligibility sandbox latency report",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Sandbox latency numbers\n\n"
        "Marcus,\n\nSandbox eligibility-API latency report attached. p50 = 720ms, "
        "p95 = 1.4s, p99 = 2.8s. Worse than production for some reason. We'll "
        "treat production at p95=800ms as the design number.\n\nLisa",
        cluster="email-w7-sandbox",
    ),
    ScenarioEvent(
        week=8,
        day=4,
        hour=11,
        kind="manual_capture",
        summary="Field note: steering committee dynamics",
        body="Field note — Sarah, post-W8 steering\n\n"
        "Group dynamic is solidifying. Patricia chairs efficiently. Tom argues "
        "vigorously then accepts decisions cleanly. Lisa is quiet but her "
        "implementation comments carry weight. Raj is the brake; respected but "
        "tiring for Tom. Maya is transactional.\n\nNo dysfunction visible. Watch "
        "Tom over Phase 3 (build) — that's where his preferred features get "
        "their final yes/no.",
        cluster="capture-w8-dynamics",
    ),
    ScenarioEvent(
        week=10,
        day=2,
        hour=14,
        kind="email_ingest",
        summary="Raj → all: HIPAA training reminder",
        body="From: Raj Patel\nTo: project-bluestate@deployai.com\nSubject: HIPAA training "
        "reminder\n\nTeam,\n\nReminder: anyone touching the eligibility/claims/"
        "messaging code needs current HIPAA training. Sending the link. Need "
        "certificates by W12.\n\nRaj",
        cluster="email-w10-hipaa-train",
    ),
    ScenarioEvent(
        week=11,
        day=3,
        hour=10,
        kind="email_ingest",
        summary="Patricia → Sarah: pilot launch date confirmation",
        body="From: Patricia Vance\nTo: Sarah Chen\nSubject: Pilot launch date\n\n"
        "Sarah,\n\nConfirming we're targeting W22 for pilot launch. NorthStar "
        "members. 500 invites. Communications team is preparing the heads-up "
        "message.\n\nPatricia",
        cluster="email-w11-pilot-date",
    ),
    ScenarioEvent(
        week=12,
        day=4,
        hour=14,
        kind="email_ingest",
        summary="Sarah → Marcus: build phase plan",
        body="From: Sarah Chen\nTo: Marcus Rivera\nSubject: Build phase plan\n\n"
        "Marcus,\n\nBuild kicks off Monday. 4 weeks for the v1 feature set. Light "
        "schedule (3 days/wk) — engineering needs heads-down time and the "
        "contractor handoff in W17 means we plan a quiet zone after.\n\nSarah",
        cluster="email-w12-build-plan",
    ),
    # ============================================================
    # W13-16 BUILD — ~15 emails, 4 meetings, 4 captures, cycle creeping
    # ============================================================
    ScenarioEvent(
        week=13,
        day=2,
        hour=11,
        kind="meeting_webhook",
        summary="Observability decision meeting",
        body="Meeting: Observability decision\n"
        "Attendees: Lisa, Marcus, Sarah\n\n"
        "Lisa wanted self-hosted OTel + Grafana. Marcus argued the build phase "
        "can't absorb the infra work. Compromise: Datadog now with a 12-month "
        "buyout flag if costs run away. Decision: Datadog.",
        cluster="meeting-w13-observability",
    ),
    ScenarioEvent(
        week=13,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Lisa → Marcus: Datadog onboarding",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Datadog onboarding\n\nMarcus,\n\n"
        "Datadog trial account created. APM agents will roll out to staging next "
        "week. Watching the log volume — first signal of cost risk.\n\nLisa",
        cluster="email-w13-datadog-onboard",
    ),
    ScenarioEvent(
        week=14,
        day=1,
        hour=9,
        kind="email_ingest",
        summary="Patricia → all: Tom departure announcement",
        body="From: Patricia Vance\nTo: project-bluestate@deployai.com; "
        "exec-team@bluestatehealth.com\nSubject: Tom Reyes — moving on\n\nTeam,\n\n"
        "Tom Reyes has accepted a CPO role at another organization and is leaving "
        "BlueState end of next week. His last day on the portal project is Friday.\n\n"
        "Sandra Kim joins as VP Product on the 12th to backfill. She's coming "
        "from another payer where she ran member experience and will need a "
        "re-onboarding from each of you.\n\nThank Tom on the way out — he's been "
        "central to this from kickoff.\n\nPatricia",
        cluster="email-w14-tom-departure",
    ),
    ScenarioEvent(
        week=14,
        day=2,
        hour=14,
        kind="meeting_webhook",
        summary="Tom's transition handoff",
        body="Meeting: Tom transition handoff\n"
        "Attendees: Tom, Sarah, Marcus, Patricia\n\n"
        "Tom walked his open items: SMS scope (was going to push again post-pilot), "
        "dispute flow re-look (he wanted to lobby Sandra), claims-export format "
        "(still open from W8 — leaning Parquet for analytics).\n\nLogged each as a "
        "risk for Sandra to ratify or close.",
        cluster="meeting-w14-tom-handoff",
    ),
    ScenarioEvent(
        week=14,
        day=3,
        hour=14,
        kind="manual_capture",
        summary="Field note: Sandra Kim intro",
        body="Field note — Sarah, intro session with Sandra Kim\n\n"
        "Sandra is sharp. She comes from a Medicare Advantage plan where she ran "
        "member experience. She'll be more disciplined than Tom on scope but she "
        "also wants 8 weeks to evaluate before signing off on any in-flight "
        "decisions.\n\nRisk: she may re-baseline in W22-23 and force late scope "
        "moves. Need to onboard her fast and get her bought in.",
        cluster="capture-w14-sandra-intro",
    ),
    ScenarioEvent(
        week=14,
        day=4,
        hour=11,
        kind="email_ingest",
        summary="Patricia → Sarah: David Liu joining for security",
        body="From: Patricia Vance\nTo: Sarah Chen\nSubject: David Liu — new VP IT Security\n\n"
        "Sarah,\n\nAdding David Liu as VP IT Security. New role created after the "
        "ransomware near-miss in March. He'll re-review your SOC2 attestation and "
        "the pen-test scope before pilot.\n\nPatricia",
        cluster="email-w14-david-add",
    ),
    ScenarioEvent(
        week=15,
        day=2,
        hour=10,
        kind="email_ingest",
        summary="David → Sarah: security re-review request",
        body="From: David Liu\nTo: Sarah Chen\nSubject: SOC2 + pen-test scope review\n\n"
        "Sarah,\n\nIn the role 3 days. Per Patricia, I'll re-review your SOC2 Type "
        "2 attestation and the Bishop Fox pen-test scope. Want to walk through "
        "both Tuesday W16.\n\nDavid",
        cluster="email-w15-david-review",
    ),
    ScenarioEvent(
        week=15,
        day=4,
        hour=16,
        kind="meeting_webhook",
        summary="Accessibility audit vendor selection",
        body="Meeting: A11y audit vendor\n"
        "Attendees: Sarah, Marcus, Sandra (first session)\n\n"
        "Sandra wanted to defer the audit to v2. Sarah walked her through "
        "Patricia's hard requirement on WCAG 2.2 AA. Sandra accepted. Vendor: "
        "Level Access, $42k.\n\nDecision delayed ~5 days from original target "
        "while Sandra re-scoped.",
        cluster="meeting-w15-a11y",
    ),
    ScenarioEvent(
        week=16,
        day=2,
        hour=11,
        kind="meeting_webhook",
        summary="David's security re-review",
        body="Meeting: Security re-review with David\n"
        "Attendees: David Liu, Marcus, Lisa, Raj\n\n"
        "David reviewed SOC2 attestation — passed. Pen-test scope: he wants two "
        "additions (out-of-band token verification on the message subsystem, and "
        "an extended fuzz pass on the eligibility cache invalidation endpoint). "
        "Bishop Fox can absorb both.\n\nNo blockers.",
        cluster="meeting-w16-david-review",
    ),
    ScenarioEvent(
        week=16,
        day=3,
        hour=14,
        kind="manual_capture",
        summary="Field note: Datadog log volume",
        body="Field note — Marcus, Datadog cost analysis\n\n"
        "First month of Datadog and the log volume is already at 60% of the annual "
        "contract. Two causes: (1) verbose request logging in the eligibility "
        "adapter, (2) the messaging subsystem dumps full payloads on every "
        "delivery.\n\nProposing sampling + payload-truncation. Should drop to "
        "~30% trajectory.",
        cluster="capture-w16-datadog",
    ),
    ScenarioEvent(
        week=16,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: phase 3 wrap (build complete)",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Build phase wrap\n\n"
        "Patricia,\n\nBuild phase complete. v1 feature set in staging. Two "
        "decisions landed (Datadog, Level Access). Tom's departure absorbed without "
        "scope slip. Sandra onboarded and will re-baseline W22-23.\n\nW17-19 is "
        "the planned contractor handoff quiet period. We'll be dark for ~3 weeks. "
        "Pilot prep resumes W20.\n\nSarah",
        cluster="email-w16-phase3-wrap",
    ),
    # filler
    ScenarioEvent(
        week=13,
        day=3,
        hour=14,
        kind="email_ingest",
        summary="Marcus → Lisa: build cadence",
        body="From: Marcus Rivera\nTo: Lisa Wong\nSubject: Build cadence\n\nLisa,\n\n3 "
        "engineering-heavy days per week (Tue-Thu), Mon for planning, Fri for "
        "review/docs. Keeps focus deep.\n\nMarcus",
        cluster="email-w13-cadence",
    ),
    ScenarioEvent(
        week=14,
        day=5,
        hour=10,
        kind="manual_capture",
        summary="Field note: Sandra's first standup",
        body="Field note — Sarah, watching Sandra's first standup\n\n"
        "Sandra ran her first standup with the BlueState product team Friday. "
        "Engaging but more directive than Tom was. Asked the team to send her "
        "their top-3 open scope questions by Monday. Signal that the W22 re-"
        "baseline is real.",
        cluster="capture-w14-sandra-standup",
    ),
    ScenarioEvent(
        week=15,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Lisa → Marcus: eligibility cache impl complete",
        body="From: Lisa Wong\nTo: Marcus Rivera\nSubject: Eligibility cache — implemented\n\n"
        "Marcus,\n\n4h TTL cache live in staging. Admin-purge endpoint exposed. "
        "Test coverage on the happy path; integration tests on invalidation TBD "
        "(per Raj's W6 ask).\n\nLisa",
        cluster="email-w15-cache-impl",
    ),
    ScenarioEvent(
        week=16,
        day=1,
        hour=10,
        kind="email_ingest",
        summary="Raj → Lisa: where are the invalidation tests",
        body="From: Raj Patel\nTo: Lisa Wong\nCc: Sarah Chen\nSubject: Invalidation tests\n\n"
        "Lisa,\n\nFollowing up on the W6 ask — invalidation hook integration "
        "tests. Coverage report still shows zero on that path. Need them in place "
        "before pilot or this becomes a launch blocker.\n\nRaj",
        cluster="email-w16-raj-tests",
    ),
    # ============================================================
    # W17-19 SILENCE — 0 events. Holiday + contractor handoff.
    # ============================================================
    # ============================================================
    # W20-24 PILOT PREP — ~12 emails, 6 meetings, 3 captures
    # decisions slow to ~8d cycle; 8 risks opened W20-22
    # ============================================================
    ScenarioEvent(
        week=20,
        day=1,
        hour=9,
        kind="email_ingest",
        summary="Sarah → all: pilot prep restart",
        body="From: Sarah Chen\nTo: Patricia, Sandra, Lisa, Raj, David, Maya\n"
        "Subject: Pilot prep restart\n\nTeam,\n\nReturning from the contractor "
        "handoff quiet period. New contractor (Acme Build) is onboarded. Pilot "
        "prep restarting today.\n\nThis week's focus: pen-test scheduling, DR "
        "drill scheduling, identity migration dry-run. Sandra re-baseline starts "
        "Wednesday.\n\nSarah",
        cluster="email-w20-restart",
    ),
    ScenarioEvent(
        week=20,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Pilot prep — gap review",
        body="Meeting: Pilot prep gap review\n"
        "Attendees: Sarah, Marcus, Lisa, Sandra, Raj, David\n\n"
        "Walked through every launch criterion. Surfaced: HIPAA audit-log "
        "retention is set to 90d, not the 6yr required. Identity migration dry-"
        "run flagged ~3% dirty records. DR drill not scheduled. Cache "
        "invalidation tests still missing.\n\nSandra raised her re-baseline asks: "
        "wants to re-look at SMS, dispute flow, and member-message PHI scope.",
        cluster="meeting-w20-gap-review",
    ),
    ScenarioEvent(
        week=20,
        day=3,
        hour=11,
        kind="email_ingest",
        summary="Sarah → Patricia: pilot date slip recommended",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Pilot date — recommending slip "
        "to W24\n\nPatricia,\n\nThree factors converging:\n- Pen-test runs W23-24; "
        "remediation can't all happen pre-launch if pilot is W22\n- Sandra's re-"
        "baseline lands W22-23; risk of late scope change\n- Acme handoff means "
        "build velocity is rebuilding\n\nRecommend slipping pilot to W24. Patricia, "
        "your call.\n\nSarah",
        cluster="email-w20-slip-rec",
    ),
    ScenarioEvent(
        week=20,
        day=4,
        hour=14,
        kind="email_ingest",
        summary="Patricia → Sarah: pilot slip approved",
        body="From: Patricia Vance\nTo: Sarah Chen\nSubject: Re: Pilot date\n\nSarah,\n\n"
        "Agreed. Slipping pilot to W24. I'll communicate to the steering. Note "
        "this against the W26 launch-prep complete date — that holds.\n\nPatricia",
        cluster="email-w20-slip-ok",
    ),
    ScenarioEvent(
        week=21,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="Sandra re-baseline session 1",
        body="Meeting: Sandra re-baseline — session 1\n"
        "Attendees: Sandra, Sarah, Marcus\n\n"
        "Sandra walked her three asks. On SMS: she agrees with Raj, deferred to "
        "v2. On dispute flow: agrees with W8 decision, defer to v2. On member-"
        "message PHI scope: wants tighter opt-in than spec. That last one will "
        "become the W22 decision.",
        cluster="meeting-w21-rebaseline-1",
    ),
    ScenarioEvent(
        week=21,
        day=3,
        hour=14,
        kind="manual_capture",
        summary="Field note: identity dry-run results",
        body="Field note — Marcus, identity migration dry-run\n\n"
        "Ran the migration against the full member set in staging. Results:\n- "
        "97% clean migration\n- ~3% (~60k members) have one of: duplicate "
        "records, missing DOB, invalid email\n\nProposed remediation: dedupe + "
        "DOB inference from claims data + email-bounce sweep. ~2 weeks of work, "
        "fits in W22-23.",
        cluster="capture-w21-identity",
    ),
    ScenarioEvent(
        week=21,
        day=4,
        hour=11,
        kind="email_ingest",
        summary="David → Marcus: pen-test kickoff confirmed",
        body="From: David Liu\nTo: Marcus Rivera\nSubject: Pen-test kickoff confirmed\n\n"
        "Marcus,\n\nBishop Fox kickoff Monday W23. Scope as discussed (portal + "
        "3 integrations + the two W16 adds). Findings expected W24 mid-week.\n\n"
        "David",
        cluster="email-w21-pentest-kick",
    ),
    ScenarioEvent(
        week=22,
        day=1,
        hour=10,
        kind="email_ingest",
        summary="Patricia → all: Mark Thompson joining as CDO",
        body="From: Patricia Vance\nTo: project-bluestate@deployai.com\nSubject: Adding "
        "Mark Thompson (CDO) to working group\n\nTeam,\n\nWe've hired Mark Thompson "
        "as our first Chief Data Officer. He starts Monday and will sit on the "
        "portal steering as an observer for now. Long-term he'll own data "
        "normalization across our digital surfaces.\n\nPatricia",
        cluster="email-w22-mark-add",
    ),
    ScenarioEvent(
        week=22,
        day=2,
        hour=14,
        kind="meeting_webhook",
        summary="PHI scope decision — opt-in",
        body="Meeting: Member-message PHI scope decision\n"
        "Attendees: Sandra, Raj, David, Marcus, Sarah, Mark Thompson (first session)\n\n"
        "Sandra, Raj, David converged on explicit opt-in for clinical notes "
        "delivery. Mark Thompson arrived late and had questions that dragged "
        "discussion ~30 min. Cycle was ~8 days from original proposal in W21.\n\n"
        "Decision: explicit opt-in for clinical notes via portal messaging.",
        cluster="meeting-w22-phi-scope",
    ),
    ScenarioEvent(
        week=23,
        day=2,
        hour=10,
        kind="meeting_webhook",
        summary="W23 status review",
        body="Meeting: W23 status review\n"
        "Attendees: Patricia, Sandra, Sarah, Marcus, Lisa, Raj, David\n\n"
        "Pen-test in progress. Identity remediation 70% complete. DR drill "
        "scheduled W24 day-2. Audit-log retention extended to 6y on Wednesday. "
        "Datadog log volume back under control after sampling change.\n\n"
        "Sandra raised whether iframe shortcut for claims-viewer could shave time. "
        "Group rejected on UX + security review burden.",
        cluster="meeting-w23-status",
    ),
    ScenarioEvent(
        week=23,
        day=4,
        hour=11,
        kind="email_ingest",
        summary="Lisa → Sarah: DR drill scheduled",
        body="From: Lisa Wong\nTo: Sarah Chen\nSubject: DR drill — W24 Tuesday\n\nSarah,\n\n"
        "DR failover drill scheduled W24 Tuesday 2am ET (low-traffic window). All "
        "ops will be on the bridge. Failback by 6am.\n\nLisa",
        cluster="email-w23-dr-cal",
    ),
    ScenarioEvent(
        week=24,
        day=2,
        hour=11,
        kind="manual_capture",
        summary="Field note: DR drill ran clean",
        body="Field note — Marcus, post DR drill\n\n"
        "Drill ran 2am-6am as planned. Failover to us-west-2 in 7m32s. Recovery "
        "to us-east-1 primary at 5:11am. Total drill window 11 minutes. Within "
        "the < 30 minute target.\n\nOne soft finding: the failover alert pager "
        "rotation routed to the wrong on-call. Will fix this week.",
        cluster="capture-w24-dr",
    ),
    ScenarioEvent(
        week=24,
        day=3,
        hour=15,
        kind="email_ingest",
        summary="David → Sarah: pen-test findings draft",
        body="From: David Liu\nTo: Sarah Chen\nCc: Marcus, Lisa\nSubject: Pen-test "
        "findings — draft\n\nSarah,\n\nBishop Fox draft delivered. 2 high, 4 "
        "medium, 11 low. Highs:\n- Eligibility-cache invalidation endpoint missing "
        "rate-limit (Raj called this in W6 — addressing now)\n- Member-message "
        "subsystem missing strict-transport-security on a legacy endpoint\n\n"
        "Remediation work this week + retest scan W25.\n\nDavid",
        cluster="email-w24-pentest-findings",
    ),
    ScenarioEvent(
        week=24,
        day=4,
        hour=14,
        kind="meeting_webhook",
        summary="Pen-test remediation walkthrough",
        body="Meeting: Pen-test remediation walkthrough\n"
        "Attendees: David, Marcus, Lisa\n\n"
        "Walked the 17 findings + remediation plan. All 2 highs and 4 mediums "
        "remediated. Of the 11 lows, 8 remediated and 3 accepted with risk "
        "documentation. Retest Monday W25.",
        cluster="meeting-w24-pentest-remediate",
    ),
    # filler W20-24
    ScenarioEvent(
        week=20,
        day=5,
        hour=15,
        kind="email_ingest",
        summary="Raj → Lisa: audit-log retention extension",
        body="From: Raj Patel\nTo: Lisa Wong\nSubject: Audit-log retention — extending\n\n"
        "Lisa,\n\nNeed to extend message audit-log retention from 90d to 6y. "
        "Glacier-class storage is fine. Need it in production before pilot.\n\n"
        "Raj",
        cluster="email-w20-raj-retention",
    ),
    ScenarioEvent(
        week=21,
        day=5,
        hour=10,
        kind="email_ingest",
        summary="Sandra → Sarah: weekly check-in",
        body="From: Sandra Kim\nTo: Sarah Chen\nSubject: Want a weekly\n\nSarah,\n\n"
        "Let's add a weekly 1:1, Fridays 4pm ET, 30 min. Patricia is at 8am — "
        "I want my own.\n\nSandra",
        cluster="email-w21-sandra-1on1",
    ),
    ScenarioEvent(
        week=22,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: weekly status W22",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Weekly status — W22\n\n"
        "Patricia,\n\nW22:\n- PHI-scope decision landed (opt-in for clinical notes)\n"
        "- 8 risks opened in last 2 weeks; 3 rejected proposals (Tom's old SMS "
        "resurfaced, DR-drill-skip, iframe-claims)\n- Pen-test starts Monday W23\n"
        "- Identity remediation 40% complete\n\nDecision cycle has stretched to "
        "~8 days from ~3 days in design phase.\n\nSarah",
        cluster="email-w22-status",
    ),
    ScenarioEvent(
        week=23,
        day=3,
        hour=14,
        kind="email_ingest",
        summary="Mark → Sarah: data normalization opportunity",
        body="From: Mark Thompson\nTo: Sarah Chen\nSubject: Data normalization — post-launch\n\n"
        "Sarah,\n\nLearning the org. Once portal launches I'd like to look at "
        "using it as a forcing function for member-data normalization. Not for "
        "v1, but worth flagging now so we don't regret v1 schema choices.\n\n"
        "Want to grab 30 min in W25?\n\nMark",
        cluster="email-w23-mark-norm",
    ),
    ScenarioEvent(
        week=24,
        day=5,
        hour=11,
        kind="email_ingest",
        summary="Sarah → Patricia: pilot launch tracking green",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Pilot launch tracking — green\n\n"
        "Patricia,\n\nAll launch criteria on track for Monday W26 GO/no-go:\n- "
        "Pen-test retest Monday W25\n- DR drill: pass\n- Accessibility audit: "
        "pass\n- Monitoring: in place\n- Opt-in flow: shipped\n- Support runbooks: "
        "drafted, training in progress\n- Member comms: pre-pilot heads-up "
        "scheduled\n\nSarah",
        cluster="email-w24-pilot-green",
    ),
    # ============================================================
    # W25-26 PRE-LAUNCH — ~6 emails, 2 meetings, 2 captures, 3 risks close
    # ============================================================
    ScenarioEvent(
        week=25,
        day=2,
        hour=11,
        kind="email_ingest",
        summary="David → Sarah: pen-test retest clean",
        body="From: David Liu\nTo: Sarah Chen\nSubject: Pen-test retest — clean\n\nSarah,\n\n"
        "Bishop Fox retest scan clean. All 2 highs + 4 mediums verified closed. "
        "We're good for launch.\n\nDavid",
        cluster="email-w25-retest",
    ),
    ScenarioEvent(
        week=25,
        day=3,
        hour=10,
        kind="meeting_webhook",
        summary="Launch comms cadence lock",
        body="Meeting: Launch comms cadence\n"
        "Attendees: Sandra, Patricia, Sarah, BlueState comms lead (Ali)\n\n"
        "Locked: pre-pilot heads-up email 5 days before invite. Invite link 24h "
        "before access opens. Follow-up email 48h post-access.\n\nDecision: "
        "approved cadence.",
        cluster="meeting-w25-comms",
    ),
    ScenarioEvent(
        week=25,
        day=4,
        hour=15,
        kind="email_ingest",
        summary="Sarah → Patricia: launch readiness summary",
        body="From: Sarah Chen\nTo: Patricia Vance\nSubject: Launch readiness summary\n\n"
        "Patricia,\n\nReadiness for Monday's GO/no-go:\n- Pen-test: PASS (clean "
        "retest)\n- DR drill: PASS\n- Accessibility: PASS (Level Access sign-off)\n"
        "- Identity remediation: COMPLETE (3% cleaned)\n- Support training: 78% "
        "complete (above 50% threshold)\n- All launch criteria: GREEN\n\n"
        "Recommendation: GO.\n\nSarah",
        cluster="email-w25-readiness",
    ),
    ScenarioEvent(
        week=26,
        day=1,
        hour=9,
        kind="manual_capture",
        summary="Field note: Sandra pre-launch read",
        body="Field note — Sarah, Sandra pre-launch read\n\n"
        "Sandra is calm, committed, supportive of GO. Long way from her W14 "
        "arrival when re-baseline felt like a risk. The Mark Thompson dynamic is "
        "interesting — he's already pushing for v2 data normalization to be the "
        "team's next thing.\n\nPatricia is steady. Lisa is exhausted but proud. "
        "Raj and David both green-light. Maya already negotiating the post-pilot "
        "expansion order.",
        cluster="capture-w26-sandra-read",
    ),
    ScenarioEvent(
        week=26,
        day=2,
        hour=15,
        kind="meeting_webhook",
        summary="GO/no-go meeting",
        body="Meeting: GO/no-go for pilot launch\n"
        "Attendees: Patricia, Sandra, Lisa, Raj, David, Mark Thompson, Maya, Sarah, "
        "Marcus, Jamie\n\nReviewed all 7 launch criteria. All green. Patricia "
        "asked each functional lead for their explicit go/no-go.\n- Sandra: GO\n"
        "- Lisa: GO\n- Raj: GO\n- David: GO\n- Mark: GO (observer)\n- Maya: GO\n\n"
        "Patricia: GO. Pilot launches tonight at 9pm ET.",
        cluster="meeting-w26-go",
    ),
    ScenarioEvent(
        week=26,
        day=3,
        hour=10,
        kind="manual_capture",
        summary="Field note: launch night",
        body="Field note — Marcus, launch night\n\n"
        "Pilot invites went out 9pm ET. 500 NorthStar members. First login at "
        "9:04pm. 47% activated within 12h. Zero P1 incidents. Eligibility cache "
        "hit rate 94% — comfortably under the rate-limit cap. Message subsystem "
        "delivered 312 in-portal messages overnight with zero PHI-handling "
        "issues.\n\nClean launch.",
        cluster="capture-w26-launch",
    ),
    ScenarioEvent(
        week=26,
        day=4,
        hour=11,
        kind="email_ingest",
        summary="Patricia → DeployAI team: thank you",
        body="From: Patricia Vance\nTo: Sarah, Marcus, Jamie\nSubject: Clean launch — "
        "thank you\n\nSarah, Marcus, Jamie,\n\nClean launch. Patricia is delighted. "
        "Next steps: 30-day pilot read-out, then expansion conversation.\n\n"
        "Patricia",
        cluster="email-w26-thanks",
    ),
]


# Convenience accumulator for total counts.
ALL_EVENTS: list[ScenarioEvent] = STAKEHOLDERS + DECISIONS + EXTRACTOR_NOISE + RISKS_OPENED + RISKS_CLOSED + NARRATIVE


__all__ = [
    "ALL_EVENTS",
    "DECISIONS",
    "EXTRACTOR_NOISE",
    "NARRATIVE",
    "RISKS_CLOSED",
    "RISKS_OPENED",
    "STAKEHOLDERS",
    "ScenarioEvent",
]
