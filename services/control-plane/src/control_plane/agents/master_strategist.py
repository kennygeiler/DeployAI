"""Phase 7 (increment 7.4) — Master Strategist agent (cross-engagement).

Pure function: read a tenant's whole portfolio (matrix nodes + edges + member
roster across all of its engagements), run deterministic predicates that look
for *cross-engagement* patterns, ask the LLM in a single call to phrase a
narrative for each flagged candidate, return ``InsightDraft`` objects ready
to upsert as ``matrix_insights`` rows. ``engagement_id`` on the resulting
rows is ``None`` — these are tenant-scoped insights.

Design record: ``docs/product/synthesis-agents.md`` §4, §9, §11.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from llm_provider_py.types import ChatMessage, LLMProvider

from control_plane.agents.oracle import InsightDraft

_log = logging.getLogger(__name__)

# Guardrails (design record §13).
_MAX_ENGAGEMENTS = 5
_MAX_NODES_PER_ENG = 200
_MAX_EDGES_TOTAL = 1_000
_MAX_PROMPT_CHARS = 12_000
_MAX_TITLE_CHARS = 100
_MAX_BODY_CHARS = 600
_MAX_OUTPUT_TOKENS = 3_000
_TEMPERATURE = 0.0

# Predicate thresholds (design record §4).
_RECURRING_RISK_JACCARD_THRESHOLD = 0.6
_RECURRING_RISK_MIN_ENGAGEMENTS = 2
_RECURRING_RISK_HIGH_ENGAGEMENTS = 3

_SYSTEM_CONCENTRATION_JACCARD_THRESHOLD = 0.7
_SYSTEM_CONCENTRATION_MIN_ENGAGEMENTS = 3
_SYSTEM_CONCENTRATION_HIGH_ENGAGEMENTS = 5

_ROLE_COVERAGE_GAP_FLOOR = 0.5

# Roles tracked for the coverage-gap predicate.
_TRACKED_ROLES = ("fde", "biz_dev")

# Insight type slugs.
INSIGHT_TYPE_RECURRING_RISK = "recurring_risk_pattern"
INSIGHT_TYPE_SYSTEM_CONCENTRATION = "system_concentration"
INSIGHT_TYPE_ROLE_COVERAGE_GAP = "role_coverage_gap"


# --- inputs -----------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioEngagement:
    """One engagement's slice of the tenant portfolio."""

    id: uuid.UUID
    name: str
    status: str
    current_phase: str
    member_roles: tuple[str, ...]  # e.g. ("fde", "deployment_strategist")
    nodes: tuple[PortfolioNode, ...]
    edges: tuple[PortfolioEdge, ...]


@dataclass(frozen=True)
class PortfolioNode:
    id: uuid.UUID
    node_type: str
    title: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioEdge:
    id: uuid.UUID
    edge_type: str
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID


# --- internal candidate shape ------------------------------------------------


@dataclass(frozen=True)
class MasterStrategistCandidate:
    """Predicate-flagged candidate, exposed for route-handler short-circuit."""

    insight_type: str
    severity: str
    citation_node_ids: tuple[uuid.UUID, ...]
    citation_edge_ids: tuple[uuid.UUID, ...]
    dedup_key: str
    input_hash: str
    prompt_context: str


# --- public entrypoints ------------------------------------------------------


def master_strategist_candidates(
    *,
    tenant_id: uuid.UUID,
    engagements: list[PortfolioEngagement],
) -> list[MasterStrategistCandidate]:
    """Run the tenant-scoped predicates over the portfolio snapshot."""
    engagements = _apply_caps(engagements)
    out: list[MasterStrategistCandidate] = []
    out.extend(_predicate_recurring_risk(tenant_id, engagements))
    out.extend(_predicate_system_concentration(tenant_id, engagements))
    out.extend(_predicate_role_coverage_gap(tenant_id, engagements))
    return out


def master_strategist_phrase(
    *,
    tenant_name: str,
    engagements: list[PortfolioEngagement],
    candidates: list[MasterStrategistCandidate],
    llm: LLMProvider,
) -> list[InsightDraft]:
    """One LLM call to phrase title + body for each candidate."""
    if not candidates:
        return []
    engagements = _apply_caps(engagements)
    messages = _build_messages(tenant_name=tenant_name, engagements=engagements, candidates=candidates)
    try:
        raw = llm.chat_complete(
            messages,
            temperature=_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:  # broad: best-effort, never raise
        _log.warning("master_strategist: LLM call failed: %s", e)
        return []
    items = _parse_response(raw)
    if items is None:
        _log.warning("master_strategist: could not parse LLM response")
        return []
    return _zip_to_drafts(candidates, items)


def run_master_strategist(
    *,
    tenant_id: uuid.UUID,
    tenant_name: str,
    engagements: list[PortfolioEngagement],
    llm: LLMProvider,
) -> list[InsightDraft]:
    """Convenience wrapper: predicates + LLM. No short-circuit."""
    candidates = master_strategist_candidates(tenant_id=tenant_id, engagements=engagements)
    return master_strategist_phrase(tenant_name=tenant_name, engagements=engagements, candidates=candidates, llm=llm)


# --- caps --------------------------------------------------------------------


def _apply_caps(engagements: list[PortfolioEngagement]) -> list[PortfolioEngagement]:
    """Enforce snapshot caps (design §13). Truncate by recency-via-id order."""
    capped: list[PortfolioEngagement] = []
    edge_count = 0
    for eng in engagements[:_MAX_ENGAGEMENTS]:
        nodes = eng.nodes[:_MAX_NODES_PER_ENG]
        room = max(0, _MAX_EDGES_TOTAL - edge_count)
        edges = eng.edges[:room]
        edge_count += len(edges)
        capped.append(
            PortfolioEngagement(
                id=eng.id,
                name=eng.name,
                status=eng.status,
                current_phase=eng.current_phase,
                member_roles=eng.member_roles,
                nodes=nodes,
                edges=edges,
            )
        )
    return capped


# --- predicates --------------------------------------------------------------


def _predicate_recurring_risk(
    tenant_id: uuid.UUID, engagements: list[PortfolioEngagement]
) -> list[MasterStrategistCandidate]:
    """Same risk title family on ≥ 2 engagements (Jaccard ≥ 0.6)."""
    out: list[MasterStrategistCandidate] = []
    # Collect (engagement_id, node) for every risk node across the portfolio.
    risks: list[tuple[PortfolioEngagement, PortfolioNode]] = []
    for eng in engagements:
        for n in eng.nodes:
            if n.node_type == "risk":
                risks.append((eng, n))
    if not risks:
        return out
    seen: set[int] = set()
    for i, (eng_i, n_i) in enumerate(risks):
        if i in seen:
            continue
        # One family per anchor risk.
        family: list[tuple[PortfolioEngagement, PortfolioNode]] = [(eng_i, n_i)]
        engagement_ids: set[uuid.UUID] = {eng_i.id}
        for j in range(i + 1, len(risks)):
            if j in seen:
                continue
            eng_j, n_j = risks[j]
            if eng_j.id == eng_i.id:
                continue  # same engagement doesn't count as recurring
            if _title_jaccard(n_i.title, n_j.title) >= _RECURRING_RISK_JACCARD_THRESHOLD:
                family.append((eng_j, n_j))
                engagement_ids.add(eng_j.id)
                seen.add(j)
        if len(engagement_ids) < _RECURRING_RISK_MIN_ENGAGEMENTS:
            continue
        seen.add(i)
        severity = "high" if len(engagement_ids) >= _RECURRING_RISK_HIGH_ENGAGEMENTS else "medium"
        node_ids = tuple(sorted({n.id for _, n in family}))
        engagement_sorted = tuple(sorted(engagement_ids))
        sample = ", ".join(f"{e.name}: {n.title!r}" for e, n in family[:5])
        input_payload = {
            "anchor": n_i.title,
            "node_ids": [str(nid) for nid in node_ids],
            "engagement_ids": [str(eid) for eid in engagement_sorted],
        }
        out.append(
            MasterStrategistCandidate(
                insight_type=INSIGHT_TYPE_RECURRING_RISK,
                severity=severity,
                citation_node_ids=node_ids,
                citation_edge_ids=(),
                dedup_key=_dedup_key(
                    "master_strategist",
                    tenant_id,
                    INSIGHT_TYPE_RECURRING_RISK,
                    engagement_sorted,
                    node_ids,
                ),
                input_hash=_input_hash(input_payload),
                prompt_context=(
                    f"risk_title_family_anchor = {n_i.title!r}\n"
                    f"engagements_affected = {len(engagement_ids)}\n"
                    f"sample = [{sample}]"
                ),
            )
        )
    return out


def _predicate_system_concentration(
    tenant_id: uuid.UUID, engagements: list[PortfolioEngagement]
) -> list[MasterStrategistCandidate]:
    """Same system on ≥ 3 engagements (Jaccard ≥ 0.7)."""
    out: list[MasterStrategistCandidate] = []
    systems: list[tuple[PortfolioEngagement, PortfolioNode]] = []
    for eng in engagements:
        for n in eng.nodes:
            if n.node_type == "system":
                systems.append((eng, n))
    if not systems:
        return out
    seen: set[int] = set()
    for i, (eng_i, n_i) in enumerate(systems):
        if i in seen:
            continue
        family: list[tuple[PortfolioEngagement, PortfolioNode]] = [(eng_i, n_i)]
        engagement_ids: set[uuid.UUID] = {eng_i.id}
        for j in range(i + 1, len(systems)):
            if j in seen:
                continue
            eng_j, n_j = systems[j]
            if eng_j.id == eng_i.id:
                continue
            if _title_jaccard(n_i.title, n_j.title) >= _SYSTEM_CONCENTRATION_JACCARD_THRESHOLD:
                family.append((eng_j, n_j))
                engagement_ids.add(eng_j.id)
                seen.add(j)
        if len(engagement_ids) < _SYSTEM_CONCENTRATION_MIN_ENGAGEMENTS:
            continue
        seen.add(i)
        severity = "high" if len(engagement_ids) >= _SYSTEM_CONCENTRATION_HIGH_ENGAGEMENTS else "medium"
        node_ids = tuple(sorted({n.id for _, n in family}))
        engagement_sorted = tuple(sorted(engagement_ids))
        sample = ", ".join(f"{e.name}: {n.title!r}" for e, n in family[:5])
        input_payload = {
            "anchor": n_i.title,
            "node_ids": [str(nid) for nid in node_ids],
            "engagement_ids": [str(eid) for eid in engagement_sorted],
        }
        out.append(
            MasterStrategistCandidate(
                insight_type=INSIGHT_TYPE_SYSTEM_CONCENTRATION,
                severity=severity,
                citation_node_ids=node_ids,
                citation_edge_ids=(),
                dedup_key=_dedup_key(
                    "master_strategist",
                    tenant_id,
                    INSIGHT_TYPE_SYSTEM_CONCENTRATION,
                    engagement_sorted,
                    node_ids,
                ),
                input_hash=_input_hash(input_payload),
                prompt_context=(
                    f"system_title_anchor = {n_i.title!r}\n"
                    f"engagements_using = {len(engagement_ids)}\n"
                    f"sample = [{sample}]"
                ),
            )
        )
    return out


def _predicate_role_coverage_gap(
    tenant_id: uuid.UUID, engagements: list[PortfolioEngagement]
) -> list[MasterStrategistCandidate]:
    """Active engagement missing a role where ≥ 50% of peers have it."""
    out: list[MasterStrategistCandidate] = []
    active = [e for e in engagements if e.status == "active"]
    if not active:
        return out
    n_active = len(active)
    role_present_count = {role: sum(1 for e in active if role in e.member_roles) for role in _TRACKED_ROLES}
    for eng in active:
        missing_roles: list[str] = []
        for role in _TRACKED_ROLES:
            if role in eng.member_roles:
                continue
            # Predicate: at least floor% of *peer* engagements have the role.
            peers_with = role_present_count[role]
            if eng.id not in {a.id for a in active}:
                # Defensive — should be in active by definition.
                continue
            ratio = peers_with / n_active
            if ratio >= _ROLE_COVERAGE_GAP_FLOOR:
                missing_roles.append(role)
        if not missing_roles:
            continue
        # One candidate per (engagement, role) combo — easier review than
        # bundling all gaps for an engagement into one card.
        for role in missing_roles:
            engagement_sorted = (eng.id,)
            input_payload = {
                "engagement_id": str(eng.id),
                "missing_role": role,
                "peer_ratio": round(role_present_count[role] / n_active, 2),
            }
            out.append(
                MasterStrategistCandidate(
                    insight_type=INSIGHT_TYPE_ROLE_COVERAGE_GAP,
                    severity="medium",
                    citation_node_ids=(),
                    citation_edge_ids=(),
                    dedup_key=_dedup_key(
                        "master_strategist",
                        tenant_id,
                        f"{INSIGHT_TYPE_ROLE_COVERAGE_GAP}:{role}",
                        engagement_sorted,
                        (),
                    ),
                    input_hash=_input_hash(input_payload),
                    prompt_context=(
                        f"engagement = {eng.name!r}\n"
                        f"missing_role = {role}\n"
                        f"peer_engagements_with_role = {role_present_count[role]}/{n_active}"
                    ),
                )
            )
    return out


# --- title similarity --------------------------------------------------------


def _title_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity, case-insensitive. Cheap + good-enough."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    inter = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(inter) / len(union)


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokenize(s: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(s.lower()) if t}


# --- prompt ------------------------------------------------------------------


def _build_messages(
    *,
    tenant_name: str,
    engagements: list[PortfolioEngagement],
    candidates: list[MasterStrategistCandidate],
) -> list[ChatMessage]:
    return [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _user_prompt(tenant_name, engagements, candidates),
        },
    ]


def _system_prompt() -> str:
    return (
        "You are the Master Strategist for DeployAI. You read a team's "
        "portfolio of deployments and a list of candidate observations the "
        "system has flagged, and write a short narrative for each one "
        "suitable for a human deployment strategist or biz-dev lead.\n"
        "\n"
        "Return a JSON array. One element per candidate, in the same order:\n"
        "\n"
        '  { "title": string (<= 100 chars, plain language),\n'
        '    "body":  string (<= 600 chars, what the pattern is + why it '
        "matters across the portfolio + one concrete next step) }\n"
        "\n"
        "Rules:\n"
        "- Be specific. Name the engagements, the risk/system, the missing role.\n"
        "- Frame the insight as a portfolio-level observation, not a single-engagement one.\n"
        '- If a candidate is actually fine on second look, set title="" and the row will be dropped.\n'
        "- Output ONLY the JSON array. No prose, no code fences, no commentary."
    )


def _user_prompt(
    tenant_name: str,
    engagements: list[PortfolioEngagement],
    candidates: list[MasterStrategistCandidate],
) -> str:
    active = [e for e in engagements if e.status == "active"]
    role_present: dict[str, int] = {role: sum(1 for e in active if role in e.member_roles) for role in _TRACKED_ROLES}
    eng_lines = "\n".join(
        f"- {e.name} (phase: {e.current_phase}, status: {e.status}, roles: {sorted(set(e.member_roles))})"
        for e in engagements
    )
    role_summary = ", ".join(f"{role}: {n}/{len(active)}" for role, n in role_present.items())
    candidates_block = "\n\n".join(
        f"[{i + 1}] type={c.insight_type} severity={c.severity}\n{c.prompt_context}" for i, c in enumerate(candidates)
    )
    prompt = (
        f"Tenant: {tenant_name}\n"
        f"Portfolio:\n{eng_lines}\n"
        f"Role coverage (active engagements only): {role_summary}\n"
        f"\n"
        f"Candidates flagged for narrative:\n{candidates_block}\n"
    )
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS] + "\n…[truncated]"
    return prompt


# --- parse + zip -------------------------------------------------------------


def _parse_response(raw: str) -> list[dict[str, Any]] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def _zip_to_drafts(candidates: list[MasterStrategistCandidate], items: list[dict[str, Any]]) -> list[InsightDraft]:
    drafts: list[InsightDraft] = []
    for cand, item in zip(candidates, items, strict=False):
        title_raw = item.get("title")
        body_raw = item.get("body")
        if not isinstance(title_raw, str) or not title_raw.strip():
            continue
        if not isinstance(body_raw, str) or not body_raw.strip():
            continue
        title = title_raw.strip()[:_MAX_TITLE_CHARS]
        body = body_raw.strip()[:_MAX_BODY_CHARS]
        drafts.append(
            InsightDraft(
                insight_type=cand.insight_type,
                severity=cand.severity,
                title=title,
                body=body,
                citation_node_ids=cand.citation_node_ids,
                citation_edge_ids=cand.citation_edge_ids,
                citation_event_ids=(),
                dedup_key=cand.dedup_key,
                input_hash=cand.input_hash,
            )
        )
    return drafts


# --- helpers ------------------------------------------------------------------


def _dedup_key(
    agent: str,
    scope_id: uuid.UUID,
    insight_type: str,
    engagement_ids: tuple[uuid.UUID, ...],
    node_ids: tuple[uuid.UUID, ...],
) -> str:
    engs = ",".join(sorted(str(i) for i in engagement_ids))
    nodes = ",".join(sorted(str(i) for i in node_ids))
    return f"{agent}:{scope_id}:{insight_type}:{engs}:{nodes}"


def _input_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
