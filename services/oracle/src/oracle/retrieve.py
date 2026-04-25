"""Phase-gated retrieval with Corpus-Confidence Marker and explicit null results (FR22, FR23, FR24).

Callers wrap a ``BaseRetriever`` (e.g. pgvector-backed) with
:class:`llama_citation_adapter.CitationValidatingRetriever` so every node has a
valid ``CitationEnvelopeV01`` in ``node.metadata['citation_envelope']``.

Indexed nodes should also set **metadata** (not the citation envelope) for gating:

- ``tenant_id`` (str): must match the request.
- ``deployment_phase`` (str): mission phase label (e.g. from ``tenant_deployment_phases``), used for
  phase-appropriate filtering. Nodes without this key are **dropped** (fail closed).
- ``recency`` (float, optional): ``[0, 1]`` evidence recency; defaults to ``0.5``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deployai_citation.citation import CitationEnvelopeV01
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

CorpusConfidenceMarker = Literal["high", "medium", "low", "null"]

# FR25 / DP10: Oracle never auto-executes; only this posture is defined for agent-boundary items.
ActionPosture = Literal["suggestion"]


@dataclass(frozen=True, slots=True)
class OracleRetrievalRequest:
    """Retrieval with tenant + deployment-phase context (7-phase framework, opaque strings)."""

    tenant_id: str
    target_deployment_phase: str
    query_text: str
    """Natural-language query passed to the underlying retriever."""
    phase_ambiguous: bool = False
    """When True, include a union of results from ``ambiguous_phases`` (FR23) instead of a single phase."""
    ambiguous_phases: tuple[str, ...] = ()
    """If empty and ``phase_ambiguous`` is True, any ``deployment_phase`` is allowed (still tenant-scoped)."""


@dataclass(frozen=True, slots=True)
class ExplicitNullResult:
    """Explicit null surface — no phase-inappropriate substitution."""

    reason: str


@dataclass(frozen=True, slots=True)
class OracleItem:
    """One ranked, phase-labeled result (suggestions only — FR25)."""

    text: str
    deployment_phase: str
    contextual_fit_score: float
    retriever_score: float
    confidence_score: float
    citation_envelope: CitationEnvelopeV01
    node_id: str | None = None
    action_posture: ActionPosture = "suggestion"


@dataclass(frozen=True, slots=True)
class OracleResponse:
    items: tuple[OracleItem, ...]
    """Descending ``contextual_fit_score``."""
    corpus_confidence_marker: CorpusConfidenceMarker
    null_result: ExplicitNullResult | None


def _envelope(nws: NodeWithScore) -> CitationEnvelopeV01:
    meta = nws.node.metadata or {}
    raw = meta.get("citation_envelope")
    if raw is None:
        msg = "citation_envelope missing (use CitationValidatingRetriever upstream)"
        raise ValueError(msg)
    if isinstance(raw, CitationEnvelopeV01):
        return raw
    return CitationEnvelopeV01.model_validate(raw)


def _tenant_ok(meta: dict[str, object], tenant_id: str) -> bool:
    tid = meta.get("tenant_id")
    return isinstance(tid, str) and tid == tenant_id


def _dep_phase(meta: dict[str, object]) -> str | None:
    p = meta.get("deployment_phase")
    return p if isinstance(p, str) and p else None


def _recency(meta: dict[str, object]) -> float:
    r = meta.get("recency")
    if isinstance(r, (int, float)) and 0.0 <= float(r) <= 1.0:
        return float(r)
    return 0.5


def _phase_ok(
    dep_phase: str,
    request: OracleRetrievalRequest,
) -> bool:
    if not request.phase_ambiguous:
        return dep_phase == request.target_deployment_phase
    if request.ambiguous_phases:
        return dep_phase in request.ambiguous_phases
    return True


def _contextual_fit(
    nws: NodeWithScore,
    env: CitationEnvelopeV01,
    dep_phase: str,
    request: OracleRetrievalRequest,
) -> float:
    meta = nws.node.metadata or {}
    sim = float(nws.score if nws.score is not None else 0.0)
    conf = float(env.confidence_score)
    rec = _recency(meta)
    if not request.phase_ambiguous:
        phase_fit = 1.0 if dep_phase == request.target_deployment_phase else 0.0
    else:
        phase_fit = 1.0 if _phase_ok(dep_phase, request) else 0.0
    if request.phase_ambiguous and request.ambiguous_phases and dep_phase in request.ambiguous_phases:
        phase_fit = max(phase_fit, 0.9)
    # Weighted blend (deterministic, documented; tuning is product-owned).
    return 0.35 * sim + 0.25 * conf + 0.25 * phase_fit + 0.15 * rec


def _marker_from_scores(scores: list[float]) -> CorpusConfidenceMarker:
    if not scores:
        return "null"
    mx = max(scores)
    if mx >= 0.72:
        return "high"
    if mx >= 0.45:
        return "medium"
    return "low"


def oracle_retrieve(
    retriever: BaseRetriever,
    request: OracleRetrievalRequest,
) -> OracleResponse:
    """Run the wrapped retriever, apply tenant + deployment-phase gating, rank, and emit CCM + null result."""
    q = QueryBundle(request.query_text)
    nodes = retriever.retrieve(q)

    kept: list[tuple[NodeWithScore, CitationEnvelopeV01, str, float]] = []
    for nws in nodes:
        meta = nws.node.metadata or {}
        if not _tenant_ok(meta, request.tenant_id):
            continue
        dep = _dep_phase(meta)
        if dep is None:
            continue
        if not _phase_ok(dep, request):
            continue
        env = _envelope(nws)
        fit = _contextual_fit(nws, env, dep, request)
        kept.append((nws, env, dep, fit))

    if not kept:
        reason = (
            "no_phase_appropriate_corpus_hits"
            if not request.phase_ambiguous
            else "no_phase_appropriate_corpus_hits_union"
        )
        return OracleResponse(
            items=(),
            corpus_confidence_marker="null",
            null_result=ExplicitNullResult(reason=reason),
        )

    kept.sort(key=lambda t: t[3], reverse=True)
    scores = [t[3] for t in kept]
    items: list[OracleItem] = []
    for nws, env, dep, fit in kept:
        node = nws.node
        nid: str | None = None
        if isinstance(node, TextNode) and getattr(node, "node_id", None):
            nid = str(node.node_id)
        text = str(getattr(node, "text", "") or "")
        items.append(
            OracleItem(
                text=text,
                deployment_phase=dep,
                contextual_fit_score=fit,
                retriever_score=float(nws.score if nws.score is not None else 0.0),
                confidence_score=float(env.confidence_score),
                citation_envelope=env,
                node_id=nid,
                action_posture="suggestion",
            )
        )
    return OracleResponse(
        items=tuple(items),
        corpus_confidence_marker=_marker_from_scores(scores),
        null_result=None,
    )
