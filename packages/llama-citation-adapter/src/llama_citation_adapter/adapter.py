"""Wrap a LlamaIndex `BaseRetriever` and drop nodes whose metadata lack a valid v0.1.0 citation envelope (FR27)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from deployai_citation import CITATION_ENVELOPE_SCHEMA_VERSION, CitationEnvelopeV01
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from pydantic import ValidationError

log = logging.getLogger(__name__)

# Epic 4-2: observability hook for rejections (metrics backend can subscribe / scrape logs).
CITATION_ENVELOPE_REJECTIONS_METRIC = "citation_envelope_rejections"

_METADATA_KEY = "citation_envelope"


@dataclass
class CitationMetrics:
    """In-process counter for testability; replace with OTel in production if needed."""

    rejections: int = 0


def _envelope_from_metadata(meta: dict[str, Any]) -> CitationEnvelopeV01:
    """Parse ``citation_envelope`` from retriever node metadata. Raises on missing/invalid kind."""
    raw = meta.get(_METADATA_KEY)
    if raw is None:
        msg = "missing citation_envelope in node.metadata"
        raise ValueError(msg)
    if isinstance(raw, CitationEnvelopeV01):
        return raw
    if isinstance(raw, dict):
        return CitationEnvelopeV01.model_validate(raw)
    if isinstance(raw, str):
        return CitationEnvelopeV01.model_validate(json.loads(raw))
    msg = f"citation_envelope has unsupported type: {type(raw).__name__}"
    raise TypeError(msg)


def validate_envelope_on_retrieval() -> str:
    """Contract test hook: current schema version enforced by Pydantic models."""
    v: str = CITATION_ENVELOPE_SCHEMA_VERSION
    return v


class CitationValidatingRetriever(BaseRetriever):
    """Delegates to an inner retriever, returns only nodes with valid `CitationEnvelopeV01` in metadata."""

    def __init__(
        self,
        retriever: BaseRetriever,
        *,
        metrics: CitationMetrics | None = None,
    ) -> None:
        super().__init__(callback_manager=retriever.callback_manager)
        self._inner = retriever
        self._metrics = metrics or CitationMetrics()

    @property
    def metrics(self) -> CitationMetrics:
        return self._metrics

    def _filter(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        out: list[NodeWithScore] = []
        for nws in nodes:
            node = nws.node
            meta = node.metadata or {}
            try:
                env = _envelope_from_metadata(meta)
                if env.schema_version != CITATION_ENVELOPE_SCHEMA_VERSION:
                    raise ValueError("schema_version mismatch")
            except (
                ValueError,
                ValidationError,
                TypeError,
                json.JSONDecodeError,
            ) as e:
                self._metrics.rejections += 1
                # Short reason only — avoid echoing user-controlled envelope strings in full.
                err = str(e) if len(str(e)) <= 200 else f"{str(e)[:200]}…"
                log.info(
                    "citation_envelope_rejection",
                    extra={
                        "metric": CITATION_ENVELOPE_REJECTIONS_METRIC,
                        "node_id": getattr(node, "node_id", None),
                        "error": err,
                    },
                )
                continue
            out.append(nws)
        return out

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        inner = self._inner.retrieve(query_bundle)
        return self._filter(inner)
