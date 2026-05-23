"""Phase 7 (increment 7.2) — Oracle synthesis agent (per-engagement).

Pure function: read one engagement's matrix snapshot + recent canonical
events, run deterministic predicates over them, ask the LLM in a single
call to phrase a narrative for each flagged candidate, return validated
``InsightDraft`` objects ready to upsert as ``matrix_insights`` rows. No
FastAPI, no SQLAlchemy — caller composes with the I/O layers.

Design record: ``docs/product/synthesis-agents.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from llm_provider_py.types import ChatMessage, LLMProvider

_log = logging.getLogger(__name__)

# Guardrails (design record §13).
_MAX_NODES = 200
_MAX_EDGES = 400
_MAX_EVENTS = 50
_MAX_TITLE_CHARS = 100
_MAX_BODY_CHARS = 600
_MAX_PROMPT_CHARS = 12_000
_MAX_OUTPUT_TOKENS = 3_000
_TEMPERATURE = 0.0

# Predicate thresholds (design record §3).
_STALE_COMMITMENT_DAYS_MEDIUM = 14
_STALE_COMMITMENT_DAYS_HIGH = 30
_UNANSWERED_RISK_DAYS_MEDIUM = 7
_UNANSWERED_RISK_DAYS_HIGH = 21
_STAKEHOLDER_NEGLECT_DAYS_LOW = 14
_STAKEHOLDER_NEGLECT_DAYS_HIGH = 30

# Edge types that constitute a "mitigation" link from a risk.
_RISK_MITIGATION_EDGES = ("blocks", "affects")
# Edge types that constitute "ownership" on a decision.
_DECISION_OWNER_EDGES = ("sponsors", "owns")

# Insight type slugs.
INSIGHT_TYPE_STALE_COMMITMENT = "stale_commitment"
INSIGHT_TYPE_UNANSWERED_RISK = "unanswered_risk"
INSIGHT_TYPE_DECISION_WITHOUT_OWNER = "decision_without_owner"
INSIGHT_TYPE_STAKEHOLDER_NEGLECT = "stakeholder_neglect"


# --- inputs -----------------------------------------------------------------


@dataclass(frozen=True)
class NodeSnapshot:
    """Minimal shape of a matrix node for the agent."""

    id: uuid.UUID
    node_type: str
    title: str
    attributes: dict[str, Any] = field(default_factory=dict)
    evidence_event_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class EdgeSnapshot:
    """Minimal shape of a matrix edge for the agent."""

    id: uuid.UUID
    edge_type: str
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID


@dataclass(frozen=True)
class EventSnapshot:
    """Minimal shape of a canonical event for the agent."""

    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    text: str  # extracted/summarized — already truncated


# --- outputs ----------------------------------------------------------------


@dataclass(frozen=True)
class InsightDraft:
    """A validated insight ready to persist (or to upsert by dedup_key)."""

    insight_type: str
    severity: str
    title: str
    body: str
    citation_node_ids: tuple[uuid.UUID, ...]
    citation_edge_ids: tuple[uuid.UUID, ...]
    citation_event_ids: tuple[uuid.UUID, ...]
    dedup_key: str
    input_hash: str


# --- internal candidate shape ------------------------------------------------


@dataclass
class _Candidate:
    """A predicate-flagged candidate, awaiting the LLM narrative."""

    insight_type: str
    severity: str
    citation_node_ids: tuple[uuid.UUID, ...]
    citation_edge_ids: tuple[uuid.UUID, ...]
    citation_event_ids: tuple[uuid.UUID, ...]
    dedup_key: str
    input_hash: str
    # Compact human-readable context for the LLM prompt.
    prompt_context: str


# --- public entrypoints ------------------------------------------------------


@dataclass(frozen=True)
class OracleCandidate:
    """Predicate-flagged candidate, exposed to the route handler so it can
    short-circuit unchanged ones before the LLM call.

    The route handler matches candidates to existing ``matrix_insights`` rows
    by ``dedup_key``: equal ``input_hash`` on an `open` row = no change,
    skip the LLM. Different hash, missing row, or `resolved` row = phrase
    via the LLM.
    """

    insight_type: str
    severity: str
    citation_node_ids: tuple[uuid.UUID, ...]
    citation_edge_ids: tuple[uuid.UUID, ...]
    citation_event_ids: tuple[uuid.UUID, ...]
    dedup_key: str
    input_hash: str
    prompt_context: str


def oracle_candidates(
    *,
    engagement_id: uuid.UUID,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    recent_events: list[EventSnapshot],
    now: datetime | None = None,
) -> list[OracleCandidate]:
    """Run the deterministic predicates, return the flagged candidates.

    No LLM call. Safe to call repeatedly; expected to be cheap relative to
    the cost of the LLM call that follows for the *unchanged* subset.
    """
    _now = now or datetime.now(UTC)
    nodes = nodes[:_MAX_NODES]
    edges = edges[:_MAX_EDGES]
    recent_events = recent_events[:_MAX_EVENTS]

    raw: list[_Candidate] = []
    raw.extend(_predicate_stale_commitment(engagement_id, nodes, recent_events, _now))
    raw.extend(_predicate_unanswered_risk(engagement_id, nodes, edges, recent_events, _now))
    raw.extend(_predicate_decision_without_owner(engagement_id, nodes, edges))
    raw.extend(_predicate_stakeholder_neglect(engagement_id, nodes, recent_events, _now))
    return [
        OracleCandidate(
            insight_type=c.insight_type,
            severity=c.severity,
            citation_node_ids=c.citation_node_ids,
            citation_edge_ids=c.citation_edge_ids,
            citation_event_ids=c.citation_event_ids,
            dedup_key=c.dedup_key,
            input_hash=c.input_hash,
            prompt_context=c.prompt_context,
        )
        for c in raw
    ]


def oracle_phrase(
    *,
    engagement_name: str,
    engagement_phase: str,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    candidates: list[OracleCandidate],
    llm: LLMProvider,
) -> list[InsightDraft]:
    """Single LLM call to phrase title + body for each candidate.

    Returns one ``InsightDraft`` per candidate that the LLM successfully
    phrased (empty title = LLM dropped the candidate). Best-effort: a
    failed LLM call or unparseable response returns ``[]``.
    """
    if not candidates:
        return []
    nodes = nodes[:_MAX_NODES]
    edges = edges[:_MAX_EDGES]
    internal = [
        _Candidate(
            insight_type=c.insight_type,
            severity=c.severity,
            citation_node_ids=c.citation_node_ids,
            citation_edge_ids=c.citation_edge_ids,
            citation_event_ids=c.citation_event_ids,
            dedup_key=c.dedup_key,
            input_hash=c.input_hash,
            prompt_context=c.prompt_context,
        )
        for c in candidates
    ]
    messages = _build_messages(
        engagement_name=engagement_name,
        engagement_phase=engagement_phase,
        nodes=nodes,
        edges=edges,
        candidates=internal,
    )
    try:
        raw = llm.chat_complete(
            messages,
            temperature=_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:  # broad: best-effort, never raise
        _log.warning("oracle: LLM call failed: %s", e)
        return []
    items = _parse_response(raw)
    if items is None:
        _log.warning("oracle: could not parse LLM response")
        return []
    return _zip_to_drafts(internal, items)


def run_oracle(
    *,
    engagement_id: uuid.UUID,
    engagement_name: str,
    engagement_phase: str,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    recent_events: list[EventSnapshot],
    llm: LLMProvider,
    now: datetime | None = None,
) -> list[InsightDraft]:
    """Convenience wrapper: predicates + LLM in one call (no short-circuit).

    Tests and callers that do not need the upsert short-circuit can use this.
    Production route handler should call ``oracle_candidates`` then
    ``oracle_phrase`` so it can skip the LLM for unchanged candidates.
    """
    candidates = oracle_candidates(
        engagement_id=engagement_id,
        nodes=nodes,
        edges=edges,
        recent_events=recent_events,
        now=now,
    )
    return oracle_phrase(
        engagement_name=engagement_name,
        engagement_phase=engagement_phase,
        nodes=nodes,
        edges=edges,
        candidates=candidates,
        llm=llm,
    )


# --- predicates --------------------------------------------------------------


def _predicate_stale_commitment(
    engagement_id: uuid.UUID,
    nodes: list[NodeSnapshot],
    events: list[EventSnapshot],
    now: datetime,
) -> list[_Candidate]:
    out: list[_Candidate] = []
    events_by_id: dict[uuid.UUID, EventSnapshot] = {e.id: e for e in events}
    for n in nodes:
        if n.node_type != "commitment":
            continue
        cited_events = [events_by_id[eid] for eid in n.evidence_event_ids if eid in events_by_id]
        most_recent = max((e.occurred_at for e in cited_events), default=None)
        days_since = _days_since(most_recent, now) if most_recent else None
        # No recent event = treat as definitely stale; we lack ground truth on
        # creation date here, so fall back on the highest severity tier.
        if days_since is None or days_since >= _STALE_COMMITMENT_DAYS_HIGH:
            severity = "high"
        elif days_since >= _STALE_COMMITMENT_DAYS_MEDIUM:
            severity = "medium"
        else:
            continue  # fresh — skip
        input_payload = {
            "node_id": str(n.id),
            "title": n.title,
            "days_since": days_since,
            "event_ids": sorted(str(e.id) for e in cited_events),
        }
        out.append(
            _Candidate(
                insight_type=INSIGHT_TYPE_STALE_COMMITMENT,
                severity=severity,
                citation_node_ids=(n.id,),
                citation_edge_ids=(),
                citation_event_ids=tuple(e.id for e in cited_events),
                dedup_key=_dedup_key("oracle", engagement_id, INSIGHT_TYPE_STALE_COMMITMENT, (n.id,)),
                input_hash=_input_hash(input_payload),
                prompt_context=(
                    f"commitment.title = {n.title!r}\n"
                    f"days_since_last_event = {days_since if days_since is not None else 'never'}\n"
                    f"evidence_events = {[e.text[:120] for e in cited_events[:3]]}"
                ),
            )
        )
    return out


def _predicate_unanswered_risk(
    engagement_id: uuid.UUID,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    events: list[EventSnapshot],
    now: datetime,
) -> list[_Candidate]:
    out: list[_Candidate] = []
    edges_by_from: dict[uuid.UUID, list[EdgeSnapshot]] = {}
    for e in edges:
        edges_by_from.setdefault(e.from_node_id, []).append(e)
    nodes_by_id: dict[uuid.UUID, NodeSnapshot] = {n.id: n for n in nodes}
    events_by_id: dict[uuid.UUID, EventSnapshot] = {e.id: e for e in events}
    for n in nodes:
        if n.node_type != "risk":
            continue
        outgoing = edges_by_from.get(n.id, [])
        has_mitigation = any(e.edge_type in _RISK_MITIGATION_EDGES for e in outgoing)
        if has_mitigation:
            continue
        cited_events = [events_by_id[eid] for eid in n.evidence_event_ids if eid in events_by_id]
        most_recent = max((e.occurred_at for e in cited_events), default=None)
        days_since = _days_since(most_recent, now) if most_recent else None
        if days_since is None or days_since >= _UNANSWERED_RISK_DAYS_HIGH:
            severity = "high"
        elif days_since >= _UNANSWERED_RISK_DAYS_MEDIUM:
            severity = "medium"
        else:
            severity = "medium"
        neighborhood_summaries = [
            f"{e.edge_type} {nodes_by_id[e.to_node_id].title!r}" for e in outgoing[:5] if e.to_node_id in nodes_by_id
        ]
        edge_ids = tuple(e.id for e in outgoing)
        input_payload = {
            "node_id": str(n.id),
            "title": n.title,
            "days_since": days_since,
            "outgoing_edge_ids": sorted(str(e) for e in edge_ids),
        }
        out.append(
            _Candidate(
                insight_type=INSIGHT_TYPE_UNANSWERED_RISK,
                severity=severity,
                citation_node_ids=(n.id,),
                citation_edge_ids=edge_ids,
                citation_event_ids=tuple(e.id for e in cited_events),
                dedup_key=_dedup_key("oracle", engagement_id, INSIGHT_TYPE_UNANSWERED_RISK, (n.id,)),
                input_hash=_input_hash(input_payload),
                prompt_context=(
                    f"risk.title = {n.title!r}\n"
                    f"days_since_last_event = {days_since if days_since is not None else 'never'}\n"
                    f"neighborhood_edges = {neighborhood_summaries}"
                ),
            )
        )
    return out


def _predicate_decision_without_owner(
    engagement_id: uuid.UUID,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
) -> list[_Candidate]:
    out: list[_Candidate] = []
    nodes_by_id: dict[uuid.UUID, NodeSnapshot] = {n.id: n for n in nodes}
    edges_by_to: dict[uuid.UUID, list[EdgeSnapshot]] = {}
    for e in edges:
        edges_by_to.setdefault(e.to_node_id, []).append(e)
    for n in nodes:
        if n.node_type != "decision":
            continue
        incoming = edges_by_to.get(n.id, [])
        has_owner = any(
            e.edge_type in _DECISION_OWNER_EDGES
            and nodes_by_id.get(e.from_node_id) is not None
            and nodes_by_id[e.from_node_id].node_type == "stakeholder"
            for e in incoming
        )
        if has_owner:
            continue
        nearby_stakeholders = [n2.title for n2 in nodes if n2.node_type == "stakeholder"][:5]
        input_payload = {
            "node_id": str(n.id),
            "title": n.title,
            "incoming_edge_ids": sorted(str(e.id) for e in incoming),
        }
        out.append(
            _Candidate(
                insight_type=INSIGHT_TYPE_DECISION_WITHOUT_OWNER,
                severity="medium",
                citation_node_ids=(n.id,),
                citation_edge_ids=tuple(e.id for e in incoming),
                citation_event_ids=tuple(),
                dedup_key=_dedup_key("oracle", engagement_id, INSIGHT_TYPE_DECISION_WITHOUT_OWNER, (n.id,)),
                input_hash=_input_hash(input_payload),
                prompt_context=(f"decision.title = {n.title!r}\nnearby_stakeholders = {nearby_stakeholders}"),
            )
        )
    return out


def _predicate_stakeholder_neglect(
    engagement_id: uuid.UUID,
    nodes: list[NodeSnapshot],
    events: list[EventSnapshot],
    now: datetime,
) -> list[_Candidate]:
    out: list[_Candidate] = []
    events_by_id: dict[uuid.UUID, EventSnapshot] = {e.id: e for e in events}
    stakeholders = [n for n in nodes if n.node_type == "stakeholder"]
    if not stakeholders:
        return out
    # Sponsor heuristic per design §15: explicit attribute, fallback to first.
    explicit_sponsors = [n for n in stakeholders if bool(n.attributes.get("is_sponsor"))]
    sponsors: list[NodeSnapshot] = explicit_sponsors or [stakeholders[0]]
    for n in sponsors:
        cited_events = [events_by_id[eid] for eid in n.evidence_event_ids if eid in events_by_id]
        most_recent = max((e.occurred_at for e in cited_events), default=None)
        days_since = _days_since(most_recent, now) if most_recent else None
        if days_since is None or days_since >= _STAKEHOLDER_NEGLECT_DAYS_HIGH:
            severity = "medium"
        elif days_since >= _STAKEHOLDER_NEGLECT_DAYS_LOW:
            severity = "low"
        else:
            continue
        input_payload = {
            "node_id": str(n.id),
            "title": n.title,
            "days_since": days_since,
        }
        out.append(
            _Candidate(
                insight_type=INSIGHT_TYPE_STAKEHOLDER_NEGLECT,
                severity=severity,
                citation_node_ids=(n.id,),
                citation_edge_ids=(),
                citation_event_ids=tuple(e.id for e in cited_events),
                dedup_key=_dedup_key("oracle", engagement_id, INSIGHT_TYPE_STAKEHOLDER_NEGLECT, (n.id,)),
                input_hash=_input_hash(input_payload),
                prompt_context=(
                    f"stakeholder.title = {n.title!r}\n"
                    f"days_since_last_event = {days_since if days_since is not None else 'never'}"
                ),
            )
        )
    return out


# --- prompt ------------------------------------------------------------------


def _build_messages(
    *,
    engagement_name: str,
    engagement_phase: str,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    candidates: list[_Candidate],
) -> list[ChatMessage]:
    return [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _user_prompt(engagement_name, engagement_phase, nodes, edges, candidates),
        },
    ]


def _system_prompt() -> str:
    return (
        "You are the Oracle for DeployAI. You read a deployment's matrix and "
        "a list of candidate observations the system has flagged, and write a "
        "short narrative for each one suitable for a human deployment "
        "strategist.\n"
        "\n"
        "Return a JSON array. One element per candidate, in the same order:\n"
        "\n"
        '  { "title": string (<= 100 chars, plain language, no jargon),\n'
        '    "body":  string (<= 600 chars, what is happening + why it matters '
        "+ 1 concrete next step) }\n"
        "\n"
        "Rules:\n"
        "- Be specific. Name the stakeholder, the commitment, the risk. Do not generalize.\n"
        "- Cite by name, not by id. Ids are for the system; humans read names.\n"
        '- If a candidate is actually fine on second look, set title="" and the row will be dropped.\n'
        "- Output ONLY the JSON array. No prose, no code fences, no commentary."
    )


def _user_prompt(
    engagement_name: str,
    engagement_phase: str,
    nodes: list[NodeSnapshot],
    edges: list[EdgeSnapshot],
    candidates: list[_Candidate],
) -> str:
    node_type_counts: dict[str, int] = {}
    for n in nodes:
        node_type_counts[n.node_type] = node_type_counts.get(n.node_type, 0) + 1
    edge_type_counts: dict[str, int] = {}
    for e in edges:
        edge_type_counts[e.edge_type] = edge_type_counts.get(e.edge_type, 0) + 1
    summary = ", ".join(f"{c} {t}" for t, c in sorted(node_type_counts.items()))
    top_edges = sorted(edge_type_counts.items(), key=lambda kv: -kv[1])[:10]
    edges_summary = ", ".join(f"{t}: {c}" for t, c in top_edges) or "(none)"
    candidates_block = "\n\n".join(
        f"[{i + 1}] type={c.insight_type} severity={c.severity}\n{c.prompt_context}" for i, c in enumerate(candidates)
    )
    prompt = (
        f"Engagement: {engagement_name} (phase: {engagement_phase})\n"
        f"Matrix summary: {summary}\n"
        f"Top edges: {edges_summary}\n"
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


def _zip_to_drafts(candidates: list[_Candidate], items: list[dict[str, Any]]) -> list[InsightDraft]:
    drafts: list[InsightDraft] = []
    # Align by index; if the LLM returned fewer items than candidates, the
    # tail is dropped (best-effort, per §10 / §13 — no retries).
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
                citation_event_ids=cand.citation_event_ids,
                dedup_key=cand.dedup_key,
                input_hash=cand.input_hash,
            )
        )
    return drafts


# --- helpers ------------------------------------------------------------------


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int((now - moment).total_seconds() // 86400)


def _dedup_key(agent: str, scope_id: uuid.UUID, insight_type: str, node_ids: tuple[uuid.UUID, ...]) -> str:
    sorted_ids = ",".join(sorted(str(i) for i in node_ids))
    return f"{agent}:{scope_id}:{insight_type}:{sorted_ids}"


def _input_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
