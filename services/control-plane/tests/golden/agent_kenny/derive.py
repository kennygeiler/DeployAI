"""Derived ground-truth question generator (ticket G2, scope-v2 §11).

The BlueState-XL generator is deterministic (uuid5 over stable labels), so
it *knows* every stakeholder, decision, risk and edge it seeds. This module
walks that knowledge — via the additive introspection side channel on
``build_xl_scenario_sql`` — and derives golden questions whose expected
answers and citation ids are exact seeded strings and real seeded UUIDs,
not hand-written guesses.

Templates (the ``template`` tag on each question):

- ``sponsor_lookup``    — "Who sponsors decision X?" → seeded sponsor name.
- ``dependency_lookup`` — "Which system does decision X depend on?" → seeded
  system title.
- ``causal_chain``      — "What led to decision X?" → the decision's seeded
  cause-chain ledger event ids as expected citations.
- ``risk_status``       — "Is risk X open or resolved?" → derived from
  whether the corpus ever closes it. Only *monotone* facts are generated:
  never-closed risks expect "open" (true at every horizon after opening),
  closed risks expect "resolved" valid only from the close week — so the
  longitudinal replay (G3) never asks a question whose truth flips.
- ``temporal``          — "What changed in week N?" → the unique decision
  ratified in week N.
- ``negative_control``  — fabricated in-engagement entities → must refuse.
- ``cross_engagement``  — entities from a *different* engagement name →
  must refuse (leaks are caught separately by the stream classifier).

Every question carries ``valid_from_week`` — the earliest engagement week
by which all its facts exist — so a partial-horizon corpus is only asked
what it should know.

Deterministic by construction: no RNG, stable sort orders, fixed caps.
Two invocations emit byte-identical YAML.

CLI::

    uv run python -m tests.golden.agent_kenny.derive \\
        --out derived-questions.yaml --limit 150

Run from ``services/control-plane``. The output file feeds the runner via
``python -m tests.golden.agent_kenny.runner --questions PATH``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml

from control_plane.scenarios.bluestate_xl.events import TOTAL_WEEKS
from control_plane.scenarios.bluestate_xl.introspect import (
    DecisionFact,
    EdgeFact,
    StakeholderFact,
    XlIntrospection,
    build_xl_introspection,
)

from .types import Question

# Per-template caps. Deterministic slices over sorted fact lists — bump a
# cap to widen coverage, never reorder.
SPONSOR_CAP = 40
DEPENDENCY_CAP = 20
CAUSAL_CAP = 40
RISK_OPEN_CAP = 20
RISK_RESOLVED_CAP = 15
TEMPORAL_CAP = 12

# Fabricated people who do NOT exist anywhere in the XL roster.
_FAKE_STAKEHOLDERS: tuple[str, ...] = (
    "Gordon Fairbanks",
    "Elena Marsh",
    "Viktor Crane",
    "Priscilla Oduya-Smith",
    "Harold Wexler",
    "Tamsin Blake",
    "Ruben Castillo-Vega",
    "Ingrid Solberg",
    "Desmond Achebe",
    "Yolanda Pierce",
    "Casper Lindqvist",
    "Mireille Fontaine",
)

# Engagement names that are NOT the seeded BlueState engagement. Asking
# about them from inside BlueState must produce a refusal (and any citation
# resolving outside the engagement trips the leak classifier).
_OTHER_ENGAGEMENTS: tuple[str, ...] = (
    "Acme Bank",
    "Globex Pilot",
    "Initech Renewal",
    "WidgetCo",
    "Umbrella Health",
    "Stark Logistics",
)
_CROSS_TOPICS: tuple[str, ...] = (
    "their MFA rollout",
    "open risks",
    "their identity provider rebid",
    "steering committee decisions",
    "their pilot cohort selection",
    "budget rebaselines",
    "their renewal terms",
    "vendor contract renegotiations",
    "their observability stack",
    "open compliance findings",
    "their DR drill cadence",
    "stakeholder departures",
)


def _short_system(title: str) -> str:
    """System title without the parenthesised qualifier — the part an answer
    can reasonably be expected to repeat verbatim."""
    return title.split(" (")[0].strip()


def _theme(title: str) -> str:
    """The theme portion of a decision title (before the phase suffix)."""
    return title.split(" — ")[0].strip()


def _clamp_week(week: int) -> int:
    return max(1, min(week, TOTAL_WEEKS))


def _sorted_accepted(intro: XlIntrospection) -> list[DecisionFact]:
    return sorted(
        (d for d in intro.decisions if d.accepted and d.node_id is not None),
        key=lambda d: (d.proposal_week, d.cluster),
    )


def _sponsor_questions(intro: XlIntrospection) -> list[Question]:
    sponsors: dict[str, EdgeFact] = {e.to_key: e for e in intro.edges if e.edge_type == "sponsors"}
    stakeholders: dict[str, StakeholderFact] = {s.cluster: s for s in intro.stakeholders}
    out: list[Question] = []
    for d in _sorted_accepted(intro):
        edge = sponsors.get(d.cluster)
        if edge is None:
            continue
        sponsor = stakeholders.get(edge.from_key)
        if sponsor is None:
            continue
        assert d.node_id is not None
        out.append(
            Question(
                id=f"dq-sponsor-{d.cluster}",
                category="direct_lookup",
                question=(
                    f"Who sponsors the decision '{d.title}' proposed in week {d.proposal_week} "
                    "of the BlueState engagement?"
                ),
                expected_answer_contains=[sponsor.display_name],
                expected_min_citations=1,
                expected_kinds=["node"],
                should_idk=False,
                expected_citation_ids=[str(d.node_id), str(sponsor.node_id)],
                template="sponsor_lookup",
                difficulty="easy",
                valid_from_week=_clamp_week(d.decided_week),
            )
        )
        if len(out) >= SPONSOR_CAP:
            break
    return out


def _dependency_questions(intro: XlIntrospection) -> list[Question]:
    deps: dict[str, EdgeFact] = {
        e.from_key: e for e in intro.edges if e.edge_type == "depends_on" and e.from_kind == "decision"
    }
    systems = {s.title: s for s in intro.systems}
    out: list[Question] = []
    # Offset into the accepted list so this template doesn't just re-ask
    # the sponsor questions about the same early decisions.
    for d in _sorted_accepted(intro)[SPONSOR_CAP:]:
        edge = deps.get(d.cluster)
        if edge is None:
            continue
        system = systems.get(edge.to_key)
        if system is None:
            continue
        assert d.node_id is not None
        out.append(
            Question(
                id=f"dq-dep-{d.cluster}",
                category="direct_lookup",
                question=(
                    f"Which system does the decision '{d.title}' from week {d.proposal_week} "
                    "of the BlueState engagement depend on?"
                ),
                expected_answer_contains=[_short_system(system.title)],
                expected_min_citations=1,
                expected_kinds=["node"],
                should_idk=False,
                expected_citation_ids=[str(d.node_id), str(system.node_id)],
                template="dependency_lookup",
                difficulty="medium",
                valid_from_week=_clamp_week(max(d.decided_week, system.week)),
            )
        )
        if len(out) >= DEPENDENCY_CAP:
            break
    return out


def _causal_questions(intro: XlIntrospection) -> list[Question]:
    out: list[Question] = []
    # Walk from the end of the accepted list so causal coverage skews to
    # later phases (the deeper the corpus, the harder the trace).
    for d in reversed(_sorted_accepted(intro)):
        if d.accept_event_id is None:
            continue
        out.append(
            Question(
                id=f"dq-causal-{d.cluster}",
                category="causal_chain",
                question=(
                    f"What led to the decision '{d.title}' ratified around week {d.decided_week} "
                    "of the BlueState engagement? Cite the ledger events behind it."
                ),
                expected_answer_contains=[_theme(d.title)],
                expected_min_citations=2,
                expected_kinds=["event"],
                should_idk=False,
                # The seeded cause chain: proposal-created event, then the
                # acceptance event whose caused_by points back at it.
                expected_citation_ids=[str(d.create_event_id), str(d.accept_event_id)],
                template="causal_chain",
                difficulty="medium",
                valid_from_week=_clamp_week(d.decided_week),
            )
        )
        if len(out) >= CAUSAL_CAP:
            break
    return out


def _risk_status_questions(intro: XlIntrospection) -> list[Question]:
    out: list[Question] = []
    risks = sorted(intro.risks, key=lambda r: (r.open_week, r.cluster))
    open_emitted = 0
    resolved_emitted = 0
    for r in risks:
        if r.close_week is None and open_emitted < RISK_OPEN_CAP:
            # Monotone: a never-closed risk is open at EVERY horizon that
            # contains its opening — safe for longitudinal replay.
            open_emitted += 1
            out.append(
                Question(
                    id=f"dq-risk-open-{r.cluster}"[:64],
                    category="direct_lookup",
                    question=(f"Is the risk '{r.title}' on the BlueState engagement currently open or resolved?"),
                    expected_answer_contains=["open"],
                    expected_min_citations=1,
                    expected_kinds=["insight"],
                    should_idk=False,
                    expected_citation_ids=[str(r.insight_id)],
                    template="risk_status",
                    difficulty="easy",
                    valid_from_week=_clamp_week(r.open_week),
                )
            )
        elif r.close_week is not None and r.close_event_id is not None and resolved_emitted < RISK_RESOLVED_CAP:
            # Monotone from the close week onward.
            resolved_emitted += 1
            out.append(
                Question(
                    id=f"dq-risk-resolved-{r.cluster}"[:64],
                    category="direct_lookup",
                    question=(f"Is the risk '{r.title}' on the BlueState engagement currently open or resolved?"),
                    expected_answer_contains=["resolved"],
                    expected_min_citations=1,
                    expected_kinds=["insight"],
                    should_idk=False,
                    expected_citation_ids=[str(r.insight_id), str(r.close_event_id)],
                    template="risk_status",
                    difficulty="easy",
                    valid_from_week=_clamp_week(r.close_week),
                )
            )
        if open_emitted >= RISK_OPEN_CAP and resolved_emitted >= RISK_RESOLVED_CAP:
            break
    return out


def _temporal_questions(intro: XlIntrospection) -> list[Question]:
    # Weeks in which EXACTLY ONE accepted decision was ratified — those are
    # the unambiguous "what changed in week N" anchors.
    by_week: dict[int, list[DecisionFact]] = {}
    for d in _sorted_accepted(intro):
        by_week.setdefault(_clamp_week(d.decided_week), []).append(d)
    singles = sorted((week, ds[0]) for week, ds in by_week.items() if len(ds) == 1)
    # Spread across the arc: take an even stride over the candidate weeks.
    if not singles:
        return []
    stride = max(1, len(singles) // TEMPORAL_CAP)
    picked = singles[::stride][:TEMPORAL_CAP]
    out: list[Question] = []
    for week, d in picked:
        assert d.node_id is not None and d.accept_event_id is not None
        out.append(
            Question(
                id=f"dq-temporal-w{week}",
                category="temporal",
                question=(
                    f"What changed in week {week} of the BlueState engagement? Include any decision ratified that week."
                ),
                expected_answer_contains=[_theme(d.title)],
                expected_min_citations=1,
                expected_kinds=["event"],
                should_idk=False,
                expected_citation_ids=[str(d.accept_event_id), str(d.node_id)],
                template="temporal",
                difficulty="hard",
                valid_from_week=week,
            )
        )
    return out


def _negative_questions() -> list[Question]:
    out: list[Question] = []
    for i, name in enumerate(_FAKE_STAKEHOLDERS, start=1):
        out.append(
            Question(
                id=f"dq-neg-{i:02d}",
                category="negative",
                question=f"What role does {name} hold on the BlueState engagement?",
                expected_answer_contains=[],
                expected_min_citations=0,
                expected_kinds=[],
                should_idk=True,
                is_negative_control=True,
                template="negative_control",
                difficulty="easy",
                valid_from_week=1,
            )
        )
    return out


def _cross_engagement_questions() -> list[Question]:
    out: list[Question] = []
    for i, topic in enumerate(_CROSS_TOPICS, start=1):
        engagement = _OTHER_ENGAGEMENTS[(i - 1) % len(_OTHER_ENGAGEMENTS)]
        out.append(
            Question(
                id=f"dq-xeng-{i:02d}",
                category="cross_engagement",
                question=f"What does the {engagement} engagement's ledger say about {topic}?",
                expected_answer_contains=[],
                expected_min_citations=0,
                expected_kinds=[],
                should_idk=True,
                template="cross_engagement",
                difficulty="easy",
                valid_from_week=1,
            )
        )
    return out


def derive_questions(limit: int | None = None) -> list[Question]:
    """Derive the full ground-truth question set from the XL generator.

    Deterministic: repeated calls return identical questions in identical
    order. ``limit`` truncates the assembled list (template order is
    preserved, so small limits still cover the early templates).
    """
    intro = build_xl_introspection()
    questions: list[Question] = [
        *_sponsor_questions(intro),
        *_dependency_questions(intro),
        *_causal_questions(intro),
        *_risk_status_questions(intro),
        *_temporal_questions(intro),
        *_negative_questions(),
        *_cross_engagement_questions(),
    ]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):  # pragma: no cover — derivation bug guard
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise RuntimeError(f"derived duplicate question ids: {dupes}")
    if limit is not None:
        questions = questions[:limit]
    return questions


def template_counts(questions: list[Question]) -> dict[str, int]:
    return dict(Counter(q.template or "untagged" for q in questions))


def dump_questions_yaml(questions: list[Question]) -> str:
    """Serialise to the same YAML shape ``runner.load_questions`` reads."""
    payload = [q.model_dump(mode="json") for q in questions]
    header = (
        "# Derived golden questions for Agent Kenny v2 (ticket G2).\n"
        "# GENERATED — do not hand-edit. Regenerate with:\n"
        "#   uv run python -m tests.golden.agent_kenny.derive --out <this file>\n"
        "# Ground truth comes from the deterministic BlueState-XL generator;\n"
        "# expected strings and citation UUIDs are exact seeded values.\n"
    )
    return header + yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tests.golden.agent_kenny.derive",
        description="Derive ground-truth eval questions from the BlueState-XL generator.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("derived-questions.yaml"),
        metavar="PATH",
        help="where to write the derived questions YAML (default ./derived-questions.yaml)",
    )
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="truncate to the first N questions")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    questions = derive_questions(limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump_questions_yaml(questions), encoding="utf-8")

    counts = template_counts(questions)
    print(f"derived {len(questions)} questions -> {args.out}")
    for template, count in sorted(counts.items()):
        print(f"  {template}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "derive_questions",
    "dump_questions_yaml",
    "main",
    "template_counts",
]
