"""BlueState-XL — procedurally generated 5-year ledger corpus.

The base BlueState scenario hand-authors ~150 events across 26 weeks. At 10x
scale this would be unmaintainable, so this module instead expands a small
set of templates over 260 weeks (5 years) with deterministic per-slot
parametrisation. The output is the same ``ScenarioEvent`` dataclass so the
builder can stay structurally close to ``bluestate/builder.py``.

Approximate generated volumes (see ``scope-v2.md`` §2.2):

- ~70 stakeholders (35 hires + 35 departures + 35 hires staggered)
- ~200 decisions (8 per quarter, ~25 quarters)
- ~130 risks opened
- ~2500 narrative events (emails / meetings / captures)

UUID determinism is delegated to the builder (uuid5 over ``cluster``), so
re-running the generator produces stable identifiers — re-seeds are
idempotent against ON CONFLICT DO NOTHING.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioEvent:
    """One ledger event to seed.

    Mirrors ``bluestate.events.ScenarioEvent`` so the builder helpers can
    consume both — but defined locally to avoid coupling the XL fixture to
    the small fixture's internals.
    """

    week: int
    day: int
    hour: int
    kind: str
    summary: str
    body: str
    actor_kind: str = "user"
    actor_id: str | None = None
    node_type: str | None = None
    title: str | None = None
    cluster: str | None = None
    accept_decision: bool = False
    rejects_acceptance: bool = False
    risk_close_of: str | None = None


TOTAL_WEEKS = 260  # 5 years

_PHASES: list[tuple[str, int, int]] = [
    ("discovery", 1, 8),
    ("design", 9, 26),
    ("build-v1", 27, 52),
    ("pilot-v1", 53, 78),
    ("launch-v1", 79, 104),
    ("expansion-y2", 105, 156),
    ("stabilise-y3", 157, 208),
    ("optimise-y4", 209, 234),
    ("renew-y5", 235, 260),
]


def _phase_for_week(week: int) -> str:
    for name, lo, hi in _PHASES:
        if lo <= week <= hi:
            return name
    return "renew-y5"


# Hand-curated stakeholder roster. ~85 distinct hires across the 5 years.
# Departures stay modest so the post-script surviving count lands near the
# scope-v2 target of ~70 stakeholders.
_STAKEHOLDER_ROSTER: list[tuple[str, str, int]] = [
    # (cluster_slug, title, hired_week)
    ("vance", "Patricia Vance (CMO)", 1),
    ("reyes", "Tom Reyes (VP Product)", 1),
    ("wong", "Lisa Wong (Eng Dir)", 1),
    ("park", "Jamie Park (Account Exec)", 1),
    ("chen", "Sarah Chen (Deployment Strategist)", 1),
    ("rivera", "Marcus Rivera (FDE)", 1),
    ("patel", "Raj Patel (Compliance)", 3),
    ("singh", "Maya Singh (Procurement)", 4),
    ("kim", "Sandra Kim (VP Product, replacing Reyes)", 14),
    ("liu", "David Liu (VP IT Security)", 14),
    ("priya", "Priya Subramanian (Eng Deputy)", 14),
    ("carla", "Carla Diaz (Procurement Deputy)", 14),
    ("thompson", "Mark Thompson (Chief Data Officer)", 22),
    ("okafor", "Ada Okafor (Member Experience Lead)", 35),
    ("nakamura", "Ken Nakamura (SRE Lead)", 42),
    ("morales", "Iris Morales (Data Engineering Manager)", 56),
    ("hernandez", "Diego Hernandez (Platform PM)", 68),
    ("singh-r", "Rahul Singh (Member Insights)", 80),
    ("walsh", "Kara Walsh (Customer Ops Lead)", 92),
    ("ali", "Sami Ali (Identity Architect)", 104),
    ("gonzalez", "Lina Gonzalez (Clinical Informatics)", 118),
    ("brody", "Eli Brody (Member-Facing Design)", 132),
    ("ahmed", "Yusuf Ahmed (Reliability PM)", 146),
    ("nair", "Anita Nair (Pharmacy Integrations)", 160),
    ("kowalski", "Kasia Kowalski (Risk and Audit)", 174),
    ("ramirez", "Lucia Ramirez (Provider Network)", 188),
    ("ito", "Hiroshi Ito (Mobile Platform Lead)", 200),
    ("forbes", "Margaret Forbes (Member Service)", 210),
    ("zhang", "Wei Zhang (Data Platform Architect)", 218),
    ("johansen", "Sven Johansen (Care Coordination)", 226),
    ("oduya", "Kemi Oduya (Vendor Management)", 234),
    ("ferreira", "Lia Ferreira (Privacy Officer)", 240),
    ("schultz", "Hans Schultz (Renewal Lead)", 244),
    ("dubois", "Camille Dubois (Member Growth)", 248),
    ("watanabe", "Aiko Watanabe (Renewal Architect)", 252),
    ("okonkwo", "Chidi Okonkwo (Member Trust)", 26),
    ("benoit", "Marc Benoit (Claims Ops)", 28),
    ("rossi", "Alessandra Rossi (Provider Liaison)", 30),
    ("alvarez", "Joaquin Alvarez (Eligibility Platform)", 34),
    ("oconnor", "Sean O'Connor (Pilot Comms)", 38),
    ("sandberg", "Britta Sandberg (Renewal Analyst)", 46),
    ("davies", "Owen Davies (Member Mobile Lead)", 50),
    ("kapoor", "Naveen Kapoor (Data Science)", 58),
    ("hassan", "Mona Hassan (Privacy Counsel)", 64),
    ("park-j", "Jihoon Park (Care Ops)", 72),
    ("rivera-l", "Liana Rivera (Member Service Coach)", 78),
    ("li", "Wenjun Li (Eligibility Architect)", 86),
    ("sokolov", "Mikhail Sokolov (SRE Manager)", 94),
    ("nguyen", "Trinh Nguyen (Claims Modernization Lead)", 100),
    ("petrov", "Anna Petrov (Y2 Expansion PM)", 108),
    ("santos", "Bruna Santos (Provider Integrations)", 114),
    ("yates", "Olivia Yates (Member Engagement)", 122),
    ("desai", "Anish Desai (Mobile Platform)", 128),
    ("bauer", "Heinrich Bauer (Compliance Y2)", 136),
    ("tanaka", "Yuki Tanaka (Renewal Analytics)", 142),
    ("ostrowski", "Marta Ostrowski (Vendor Ops)", 150),
    ("smith", "Adrian Smith (Eligibility Ops)", 156),
    ("hall", "Vivian Hall (Member Ops Director)", 162),
    ("varma", "Priti Varma (Telemetry Lead)", 168),
    ("greco", "Bianca Greco (Pharmacy Ops)", 178),
    ("ortega", "Felipe Ortega (Provider Audit)", 184),
    ("ulrich", "Karl Ulrich (Risk Architect)", 192),
    ("bishop", "Cassandra Bishop (Renewal Strategy)", 198),
    ("delarosa", "Esteban de la Rosa (Onboarding Ops)", 204),
    ("lin", "Tian Lin (Data Reliability)", 212),
    ("kowal", "Renata Kowal (Care Engineering)", 222),
    ("vass", "Anna Vass (Pilot Outcomes)", 228),
    ("torres", "Daniela Torres (Renewal Comms)", 246),
    ("fischer", "Greta Fischer (Y5 Strategy)", 250),
    ("nakata", "Kenji Nakata (Renewal Engineering)", 254),
    ("cole", "Mariam Cole (Renewal Member Experience)", 256),
    ("yamada", "Sora Yamada (Renewal SRE)", 258),
    ("singh-a", "Asha Singh (Privacy Y3)", 165),
    ("rios", "Patricio Rios (Care Ops Y3)", 172),
    ("lambert", "Sophie Lambert (Renewal Member Comms)", 182),
    ("dunn", "Theo Dunn (Renewal Risk)", 188),
    ("monroe", "Iris Monroe (Y4 Optimisation PM)", 214),
    ("cobb", "Walter Cobb (Y4 Strategy)", 220),
    ("paz", "Lucio Paz (Y5 Pre-Renewal)", 232),
    ("ahmadi", "Soraya Ahmadi (Renewal Member Mobile)", 238),
    ("griffin", "Henrietta Griffin (Renewal Strategy Y5)", 242),
    ("becker", "Tobias Becker (Renewal Engineering Lead)", 246),
    ("wei", "Min Wei (Y5 Reliability)", 252),
    ("nair-r", "Rohan Nair (Y5 Pharmacy)", 254),
]

# Departures: pair with a hire and apply a staggered offset so churn flows
# across the 5-year arc. Indexes refer to ``_STAKEHOLDER_ROSTER``.
# Kept smaller than the small fixture's ratio so the surviving roster
# lands close to the scope-v2 ~70 target after deletes apply.
_DEPARTURE_PLAN: list[tuple[int, int]] = [
    (1, 14),  # Reyes departs W14 (matches small fixture narrative)
    (2, 14),  # Wong rotates off W14
    (7, 24),  # Singh handed off W24
    (8, 120),  # Kim leaves Y3
    (11, 96),  # Carla rotates pre-pilot
    (15, 158),
    (16, 170),
    (19, 180),
    (22, 200),
    (24, 215),
    (26, 230),
    (27, 240),
    (33, 256),
    (34, 258),
]


def build_stakeholder_events() -> list[ScenarioEvent]:
    out: list[ScenarioEvent] = []
    for slug, title, week in _STAKEHOLDER_ROSTER:
        out.append(
            ScenarioEvent(
                week=min(week, TOTAL_WEEKS),
                day=1 + (hash(slug) % 4),
                hour=10 + (hash(slug) % 6),
                kind="matrix_node_created",
                node_type="stakeholder",
                title=title,
                summary=f"stakeholder added: {title}",
                body=(
                    f"Hire week {week} — {title}. Brought in to absorb the workstream "
                    f"appropriate to the {_phase_for_week(week)} phase. Steering "
                    "committee notes attached to the kickoff meeting record."
                ),
                cluster=f"stakeholder-{slug}",
            )
        )
    for idx, week in _DEPARTURE_PLAN:
        slug, title, _ = _STAKEHOLDER_ROSTER[idx]
        out.append(
            ScenarioEvent(
                week=min(week, TOTAL_WEEKS),
                day=2 + (idx % 3),
                hour=9 + (idx % 5),
                kind="matrix_node_deleted",
                node_type="stakeholder",
                title=f"{title} — departed",
                summary=f"stakeholder removed: {title}",
                body=(
                    f"Departure week {week} — {title}. Coverage handed to the "
                    "deputy named in the next hire entry; outstanding decisions "
                    "captured in the W-end status digest."
                ),
                cluster=f"stakeholder-{slug}-out",
            )
        )
    return out


# Decision templates: each phase contributes a thread of decisions. We
# generate ~200 by walking the 5-year arc and emitting 1-2 decisions per
# quarter, alternating between "accepted" and "rejected" so the extractor-
# acceptance-drift analyzer has signal to work with.
_DECISION_THEMES: list[tuple[str, str]] = [
    ("frontend-stack", "Frontend stack refresh"),
    ("identity-provider", "Identity provider rebid"),
    ("eligibility-cache", "Eligibility cache strategy"),
    ("claims-viewer", "Claims viewer scope"),
    ("pilot-cohort", "Pilot cohort selection"),
    ("pentest-vendor", "Pen-test vendor engagement"),
    ("observability", "Observability stack decision"),
    ("accessibility", "Accessibility audit cadence"),
    ("messaging-scope", "Member messaging scope"),
    ("dr-cadence", "DR drill cadence"),
    ("data-retention", "Audit data retention window"),
    ("hipaa-scope", "HIPAA scope ratification"),
    ("partner-add", "Partner integration approval"),
    ("region-expansion", "Region/footprint expansion"),
    ("budget-rebaseline", "Budget rebaseline"),
    ("vendor-renegotiation", "Vendor contract renegotiation"),
    ("kpi-rebaseline", "KPI rebaseline"),
    ("support-runbook", "Support runbook ownership"),
    ("comms-cadence", "Member communications cadence"),
    ("renewal-terms", "Renewal terms"),
]


def build_decision_events() -> list[ScenarioEvent]:
    out: list[ScenarioEvent] = []
    decisions_per_quarter = 11
    quarters = TOTAL_WEEKS // 13  # ~20 quarters
    counter = 0
    for q in range(quarters):
        for slot in range(decisions_per_quarter):
            week = q * 13 + 1 + (slot * 13 // decisions_per_quarter)
            if week > TOTAL_WEEKS:
                break
            theme_slug, theme_title = _DECISION_THEMES[counter % len(_DECISION_THEMES)]
            counter += 1
            is_reject = counter % 9 == 0
            cluster = f"decision-q{q + 1}-{theme_slug}-{counter}"
            phase = _phase_for_week(week)
            title = f"{theme_title} — {phase} cycle"
            body = (
                f"Quarter {q + 1} ({phase}) decision threading {theme_title.lower()}. "
                f"Counter {counter}. Re-baselined against the {phase} success criteria "
                "and ratified with the steering committee."
            )
            day = 1 + (counter % 5)
            hour = 9 + (counter % 8)
            out.append(
                ScenarioEvent(
                    week=week,
                    day=day,
                    hour=hour,
                    kind="decision",
                    title=title,
                    summary=f"decision proposed: {title}",
                    body=body,
                    cluster=cluster,
                    accept_decision=not is_reject,
                    rejects_acceptance=is_reject,
                )
            )
    return out


# Risks: opened in clusters of 5-7 per phase. ~130 total.
_RISK_THEMES: list[str] = [
    "rate-limit shortfall",
    "PD-API staleness",
    "pilot cohort generalizability",
    "stakeholder spec-gap",
    "Datadog cost overrun",
    "HIPAA audit-log gap",
    "DR drill not scheduled",
    "identity migration data quality",
    "cache-invalidation untested",
    "VP product re-baseline",
    "claims-viewer perf regression",
    "support-team training behind",
    "regulatory comment period",
    "vendor SLA degradation",
    "key-person concentration",
    "third-party CVE exposure",
    "TLS cert expiry watch",
    "back-pressure during enrolment",
    "EDI 834 batch lag",
    "mobile push deliverability",
]


def build_risk_events() -> tuple[list[ScenarioEvent], list[ScenarioEvent]]:
    opened: list[ScenarioEvent] = []
    closed: list[ScenarioEvent] = []
    n_opened = 130
    for i in range(n_opened):
        week = 2 + (i * 2) % (TOTAL_WEEKS - 4)
        theme = _RISK_THEMES[i % len(_RISK_THEMES)]
        cluster = f"risk-{i + 1}-{theme.replace(' ', '-')}"
        title = f"Risk: {theme} (W{week})"
        body = (
            f"Risk opened at week {week} during {_phase_for_week(week)}. "
            f"Tracking {theme}; mitigation owner TBA at the next steering review."
        )
        opened.append(
            ScenarioEvent(
                week=week,
                day=1 + (i % 5),
                hour=10 + (i % 6),
                kind="risk_opened",
                title=title,
                summary=f"risk opened: {theme}",
                body=body,
                cluster=cluster,
            )
        )
        if i % 3 == 0:
            close_week = min(week + 10 + (i % 25), TOTAL_WEEKS)
            closed.append(
                ScenarioEvent(
                    week=close_week,
                    day=1 + ((i + 1) % 5),
                    hour=11 + (i % 5),
                    kind="risk_closed",
                    title=f"Risk closed: {theme}",
                    summary=f"risk closed: {theme}",
                    body=f"Closed at week {close_week} after mitigation accepted.",
                    risk_close_of=cluster,
                )
            )
    return opened, closed


# Extractor noise — ~30 events. Same role as in the small fixture: provides
# the high-acceptance baseline so the reject cluster shows up as drift.
def build_extractor_noise() -> list[ScenarioEvent]:
    out: list[ScenarioEvent] = []
    n = 30
    for i in range(n):
        week = 5 + (i * 8) % (TOTAL_WEEKS - 5)
        cluster = f"extractor-noise-{i + 1}"
        title = f"Extractor proposal #{i + 1}: auto-add system node"
        out.append(
            ScenarioEvent(
                week=week,
                day=1 + (i % 5),
                hour=11 + (i % 4),
                kind="extractor_proposal",
                title=title,
                summary=f"extractor proposed: synthetic node #{i + 1}",
                body=f"Cartographer surfaced narrative drift at week {week}.",
                cluster=cluster,
                accept_decision=True,
            )
        )
    return out


# Narrative events: emails, meetings, captures. ~2500 total.
_EMAIL_TEMPLATES: list[str] = [
    "weekly status digest",
    "compliance review notes",
    "vendor risk update",
    "engineering retro summary",
    "executive briefing recap",
    "member-comms draft",
    "DR drill follow-up",
    "incident postmortem distilled",
    "renewal forecast",
    "partner integration checkpoint",
]
_MEETING_TEMPLATES: list[str] = [
    "steering committee",
    "engineering deep-dive",
    "compliance kickoff",
    "vendor QBR",
    "post-incident review",
    "member-experience workshop",
    "renewal planning",
]
_CAPTURE_TEMPLATES: list[str] = [
    "field note: data center walk",
    "field note: 1:1 with compliance",
    "manual capture: support ticket triage",
    "manual capture: regulator call",
]


def build_narrative_events() -> list[ScenarioEvent]:
    out: list[ScenarioEvent] = []
    target = 2500
    n_emails = int(target * 0.7)
    n_meetings = int(target * 0.2)
    n_captures = target - n_emails - n_meetings

    counter = 0
    for i in range(n_emails):
        week = 1 + (i % (TOTAL_WEEKS - 1))
        tpl = _EMAIL_TEMPLATES[i % len(_EMAIL_TEMPLATES)]
        cluster = f"email-{i + 1}-w{week}"
        out.append(
            ScenarioEvent(
                week=week,
                day=1 + (i % 5),
                hour=8 + (i % 9),
                kind="email_ingest",
                summary=f"email: {tpl} (w{week})",
                body=(
                    f"From: ops@bluestatehealth.com\nTo: ops@deployai.com\n"
                    f"Subject: {tpl}\n\nWeek {week} ({_phase_for_week(week)}) — {tpl}. "
                    "Routine cadence message preserving the timeline narrative for "
                    "Agent Kenny v2 to compound against."
                ),
                cluster=cluster,
            )
        )
        counter += 1

    for i in range(n_meetings):
        week = 1 + ((i * 3 + 2) % (TOTAL_WEEKS - 1))
        tpl = _MEETING_TEMPLATES[i % len(_MEETING_TEMPLATES)]
        cluster = f"meeting-{i + 1}-w{week}"
        out.append(
            ScenarioEvent(
                week=week,
                day=2 + (i % 4),
                hour=10 + (i % 7),
                kind="meeting_webhook",
                summary=f"meeting: {tpl} (w{week})",
                body=(
                    f"Meeting: {tpl}\nWeek {week} ({_phase_for_week(week)}).\n"
                    "Attendees: rotating steering set per the phase plan.\n"
                    "Output: action items routed to current owners."
                ),
                cluster=cluster,
            )
        )
        counter += 1

    for i in range(n_captures):
        week = 1 + ((i * 7 + 3) % (TOTAL_WEEKS - 1))
        tpl = _CAPTURE_TEMPLATES[i % len(_CAPTURE_TEMPLATES)]
        cluster = f"capture-{i + 1}-w{week}"
        out.append(
            ScenarioEvent(
                week=week,
                day=1 + (i % 5),
                hour=9 + (i % 8),
                kind="manual_capture",
                summary=f"capture: {tpl} (w{week})",
                body=(
                    f"{tpl}. Week {week} ({_phase_for_week(week)}). Field note "
                    "captured directly by the deployment strategist."
                ),
                cluster=cluster,
            )
        )
        counter += 1
    return out


STAKEHOLDERS: list[ScenarioEvent] = build_stakeholder_events()
DECISIONS: list[ScenarioEvent] = build_decision_events()
_RISK_OPENED, _RISK_CLOSED = build_risk_events()
RISKS_OPENED: list[ScenarioEvent] = _RISK_OPENED
RISKS_CLOSED: list[ScenarioEvent] = _RISK_CLOSED
EXTRACTOR_NOISE: list[ScenarioEvent] = build_extractor_noise()
NARRATIVE: list[ScenarioEvent] = build_narrative_events()


__all__ = [
    "DECISIONS",
    "EXTRACTOR_NOISE",
    "NARRATIVE",
    "RISKS_CLOSED",
    "RISKS_OPENED",
    "STAKEHOLDERS",
    "TOTAL_WEEKS",
    "ScenarioEvent",
    "build_decision_events",
    "build_narrative_events",
    "build_risk_events",
    "build_stakeholder_events",
]
