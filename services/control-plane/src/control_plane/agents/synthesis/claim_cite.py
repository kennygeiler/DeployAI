"""Per-claim citation validator for synthesized prose (scope-v2 §3.3, ethos §3.1).

A synthesized matrix-insight body or matrix-node description is split into
paragraphs (blank-line separated). Each paragraph must carry at least one
inline citation of the form ``[event:UUID]`` / ``[node:UUID]`` /
``[insight:UUID]`` / ``[turn:UUID]`` *and* each cited UUID must resolve to
a real row scoped to the same tenant + engagement. Failures fall into two
buckets:

- ``missing_cite_paragraphs`` — paragraph indices that contain no cite at
  all. The synthesizer retries the LLM prompt on this class of failure.
- ``unverified`` — cites that parsed but did not match a real row in the
  current engagement+tenant. Includes both fabricated UUIDs and
  cross-engagement leaks (a real UUID belonging to a sibling engagement).

A report with both lists empty means the prose is safe to persist.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.matrix import MatrixInsight, MatrixNode
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.oracle import OracleChatTurn

CitationKind = Literal["event", "node", "insight", "turn"]

CITATION_RE = re.compile(
    r"\[(event|node|insight|turn):([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]"
)


@dataclass(frozen=True)
class Citation:
    kind: CitationKind
    id: uuid.UUID


@dataclass(frozen=True)
class ClaimValidationReport:
    """Outcome of running ``validate_per_claim_cites`` over a body of prose."""

    paragraphs: int
    citations: list[Citation] = field(default_factory=list)
    missing_cite_paragraphs: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_cite_paragraphs


def _split_paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text.strip()) if chunk.strip()]


def validate_per_claim_cites(text: str) -> ClaimValidationReport:
    """Split ``text`` on blank lines; flag every paragraph that lacks a cite.

    Returns the full list of citations encountered in document order plus
    the indices (0-based) of paragraphs with zero cites. Empty input is
    treated as a single missing-cite paragraph so synthesizer code can
    surface "LLM returned nothing usable" the same way it surfaces
    "LLM forgot to cite".
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return ClaimValidationReport(paragraphs=0, missing_cite_paragraphs=[0])

    all_citations: list[Citation] = []
    missing: list[int] = []
    for idx, paragraph in enumerate(paragraphs):
        matches = CITATION_RE.findall(paragraph)
        if not matches:
            missing.append(idx)
            continue
        for kind, raw_id in matches:
            try:
                cid = uuid.UUID(raw_id)
            except ValueError:
                # Regex constrains shape, but UUID() still validates the bytes
                # (e.g. invalid hex digit). Treat as a missing cite for that
                # paragraph rather than crashing the synthesizer.
                if idx not in missing:
                    missing.append(idx)
                continue
            all_citations.append(Citation(kind=kind, id=cid))

    return ClaimValidationReport(
        paragraphs=len(paragraphs),
        citations=all_citations,
        missing_cite_paragraphs=missing,
    )


async def verify_citations_exist(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    citations: list[Citation],
) -> list[Citation]:
    """Return the subset of ``citations`` that DO NOT resolve in this scope.

    A citation resolves only when the row exists AND its tenant_id +
    engagement_id match. Cross-engagement leaks (UUID exists but in a
    sibling engagement) are returned as unverified — the synthesizer must
    not persist prose that cites them. See ethos §3.1 for why this is the
    critical guard.
    """
    if not citations:
        return []

    ids_by_kind: dict[str, set[uuid.UUID]] = {}
    for cite in citations:
        ids_by_kind.setdefault(cite.kind, set()).add(cite.id)

    found: dict[str, set[uuid.UUID]] = {kind: set() for kind in ids_by_kind}

    if "event" in ids_by_kind:
        rows = await session.execute(
            select(LedgerEvent.id).where(
                LedgerEvent.id.in_(ids_by_kind["event"]),
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.engagement_id == engagement_id,
            )
        )
        found["event"] = set(rows.scalars().all())

    if "node" in ids_by_kind:
        rows = await session.execute(
            select(MatrixNode.id).where(
                MatrixNode.id.in_(ids_by_kind["node"]),
                MatrixNode.tenant_id == tenant_id,
                MatrixNode.engagement_id == engagement_id,
            )
        )
        found["node"] = set(rows.scalars().all())

    if "insight" in ids_by_kind:
        rows = await session.execute(
            select(MatrixInsight.id).where(
                MatrixInsight.id.in_(ids_by_kind["insight"]),
                MatrixInsight.tenant_id == tenant_id,
                MatrixInsight.engagement_id == engagement_id,
            )
        )
        found["insight"] = set(rows.scalars().all())

    if "turn" in ids_by_kind:
        # OracleChatTurn isn't engagement-scoped on the row itself; it joins
        # via its conversation. Verify tenant scope and conversation→engagement
        # in one go.
        from control_plane.domain.oracle import OracleConversation

        rows = await session.execute(
            select(OracleChatTurn.id)
            .join(OracleConversation, OracleConversation.id == OracleChatTurn.conversation_id)
            .where(
                OracleChatTurn.id.in_(ids_by_kind["turn"]),
                OracleChatTurn.tenant_id == tenant_id,
                OracleConversation.engagement_id == engagement_id,
            )
        )
        found["turn"] = set(rows.scalars().all())

    unverified: list[Citation] = []
    seen: set[tuple[str, uuid.UUID]] = set()
    for cite in citations:
        key = (cite.kind, cite.id)
        if key in seen:
            continue
        seen.add(key)
        if cite.id not in found.get(cite.kind, set()):
            unverified.append(cite)
    return unverified


__all__ = [
    "CITATION_RE",
    "Citation",
    "ClaimValidationReport",
    "validate_per_claim_cites",
    "verify_citations_exist",
]
