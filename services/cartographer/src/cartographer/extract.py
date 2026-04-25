"""Chunked map-reduce extraction (Epic 6, Story 6.2, FR20).

Deterministic **stub** extractors: no live LLM or web calls (DP1). Real LLM-backed
extraction and canonical-memory persistence land in the same module surface later.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, cast

from deployai_citation.citation import CitationEnvelopeV01, EvidenceSpanV01

from cartographer.triage import EventSignals, TriageResult

# Stable timestamp for stub envelopes (replay parity tests).
_STAMP = "2026-01-15T12:00:00Z"
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace (RFC 4122)

MAX_CHUNK_CHARS = 4000


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    label: str
    kind: str
    """Coarse type: e.g. organization, person (heuristic in stub)."""
    evidence_span: EvidenceSpanV01
    envelope: CitationEnvelopeV01


@dataclass(frozen=True, slots=True)
class ExtractedRelationship:
    subj: str
    obj: str
    predicate: str
    evidence_span: EvidenceSpanV01
    envelope: CitationEnvelopeV01


@dataclass(frozen=True, slots=True)
class BlockerStub:
    text: str
    evidence_span: EvidenceSpanV01
    envelope: CitationEnvelopeV01


@dataclass(frozen=True, slots=True)
class CandidateLearningStub:
    text: str
    evidence_span: EvidenceSpanV01
    envelope: CitationEnvelopeV01


@dataclass(frozen=True, slots=True)
class ExtractionBundle:
    source_event_id: uuid.UUID
    graph_epoch: int
    full_text: str
    entities: tuple[ExtractedEntity, ...]
    relationships: tuple[ExtractedRelationship, ...]
    blockers: tuple[BlockerStub, ...]
    candidate_learnings: tuple[CandidateLearningStub, ...]


def chunk_by_paragraphs(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[tuple[int, str]]:
    """Return ``(char_offset, chunk)`` for map-reduce; offsets are indices into full ``text``."""
    t = text.strip()
    if not t:
        return [(0, "")]
    if len(t) <= max_chars:
        return [(0, t)]
    out: list[tuple[int, str]] = []
    i = 0
    n = len(t)
    while i < n:
        j = min(i + max_chars, n)
        if j < n:
            sp = t.rfind(" ", i, j)
            if sp > i:
                j = sp
        chunk = t[i:j]
        if chunk:
            out.append((i, chunk))
        i = j
        while i < n and t[i].isspace():
            i += 1
    return out or [(0, t)]


def _stub_entity_token_candidates(chunk: str) -> list[tuple[str, int, int]]:
    """Deterministic 'entities' = Title-Case multi-word runs or known org tokens (stub)."""
    found: list[tuple[str, int, int]] = []
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|NYC|DOT)\b", chunk):
        s, e = m.span()
        found.append((m.group(1).strip(), s, e))
    return found[:8]


def _envelope(
    event_id: uuid.UUID,
    *,
    chunk_index: int,
    label: str,
    start: int,
    end: int,
    graph_epoch: int,
) -> CitationEnvelopeV01:
    node_n = f"{event_id!s}:{chunk_index}:{label}"
    node_id = uuid.uuid5(_NS, node_n)
    return CitationEnvelopeV01(
        node_id=node_id,
        graph_epoch=graph_epoch,
        evidence_span=EvidenceSpanV01(start=start, end=max(start + 1, end), source_ref=f"event:{event_id!s}"),
        retrieval_phase="cartographer",
        confidence_score=0.5,
        signed_timestamp=_STAMP,
    )


def _map_chunk(
    base: int,
    chunk: str,
    chunk_index: int,
    event_id: uuid.UUID,
    graph_epoch: int,
) -> list[ExtractedEntity]:
    ents: list[ExtractedEntity] = []
    for label, s, e in _stub_entity_token_candidates(chunk):
        g_start, g_end = base + s, base + e
        ev = _envelope(
            event_id,
            chunk_index=chunk_index,
            label=label,
            start=g_start,
            end=g_end,
            graph_epoch=graph_epoch,
        )
        kind = "organization" if "DOT" in label or "NYC" in label else "other"
        ents.append(ExtractedEntity(label=label, kind=kind, evidence_span=ev.evidence_span, envelope=ev))
    return ents


def _dedupe(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    seen: set[str] = set()
    out: list[ExtractedEntity] = []
    for e in sorted(entities, key=lambda x: (x.label.lower(), x.evidence_span.start)):
        k = f"{e.label.lower()}:{e.evidence_span.start}"
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def extract_stub(
    event: EventSignals,
    triage: TriageResult,
    *,
    graph_epoch: int = 0,
) -> ExtractionBundle:
    """Map-reduce over chunks; idempotent for fixed inputs. Skips if triage failed.

    Produces a narrow stub (entities only + empty relations/blockers/learnings) with
    valid citation envelopes. Canonical-memory writes are out of scope for this pass.
    """
    if triage.triaged_out or not triage.would_consume_extraction:
        msg = "extract_stub requires a triage-passed event"
        raise ValueError(msg)
    text = f"{' '.join(event.event_keywords)} {event.text_blob}".strip()
    if not text:
        return ExtractionBundle(
            source_event_id=event.event_id,
            graph_epoch=graph_epoch,
            full_text="",
            entities=(),
            relationships=(),
            blockers=(),
            candidate_learnings=(),
        )
    segs = chunk_by_paragraphs(text)
    mapped: list[ExtractedEntity] = []
    for i, (base, chunk) in enumerate(segs):
        mapped.extend(_map_chunk(base, chunk, i, event.event_id, graph_epoch))
    reduced = _dedupe(mapped)
    return ExtractionBundle(
        source_event_id=event.event_id,
        graph_epoch=graph_epoch,
        full_text=text,
        entities=tuple(reduced),
        relationships=(),
        blockers=(),
        candidate_learnings=(),
    )


def bundle_fingerprint(bundle: ExtractionBundle) -> str:
    """SHA-256 of canonical JSON for replay-parity (stable ordering)."""

    def env_to_dict(c: CitationEnvelopeV01) -> dict[str, Any]:
        d = c.model_dump(mode="json")
        return cast(dict[str, Any], json.loads(json.dumps(d, sort_keys=True)))

    payload = {
        "event": str(bundle.source_event_id),
        "epoch": bundle.graph_epoch,
        "entities": [
            (e.label, e.kind, e.evidence_span.model_dump(), env_to_dict(e.envelope)) for e in bundle.entities
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
