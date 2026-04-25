"""LLM-backed chunked extraction (DP1: text-in-text-out; no web)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any, cast

from cartographer.extract import (
    MAX_CHUNK_CHARS,
    ExtractedEntity,
    ExtractionBundle,
    _dedupe,
    _envelope,
    chunk_by_paragraphs,
)
from cartographer.triage import EventSignals, TriageResult

_ChatBlock = list[dict[str, str]]


def _system_prompt() -> str:
    return (
        "You are Cartographer (DeployAI). Extract named entities from the user TEXT only. "
        "Do not use the web or outside knowledge. "
        'Reply with a single JSON object: {"entities":[{"label":string,"kind":string,'
        '"span_text":string}]} where span_text is copied verbatim from the text '
        "for that entity. If none, use {\"entities\":[]}."
    )


def _parse_llm_json(raw: str) -> dict[str, Any]:
    t = raw.strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        t = m.group(0)
    return cast(dict[str, Any], json.loads(t))


def _span_for_quote(chunk: str, quote: str, base: int) -> tuple[int, int] | None:
    q = (quote or "").strip()
    if len(q) < 2:
        return None
    at = chunk.find(q)
    if at < 0:
        at = chunk.lower().find(q.lower())
    if at < 0:
        return None
    return base + at, base + at + len(q)


def _llm_map_chunk(
    chunk: str,
    base: int,
    chunk_index: int,
    event_id: uuid.UUID,
    graph_epoch: int,
    completer: Callable[[str], str],
) -> list[ExtractedEntity]:
    raw = completer(chunk)
    try:
        data = _parse_llm_json(raw)
    except json.JSONDecodeError:
        return []
    rows = data.get("entities")
    if not isinstance(rows, list):
        return []
    out: list[ExtractedEntity] = []
    for ent in rows[:16]:
        if not isinstance(ent, dict):
            continue
        label = str(ent.get("label", "")).strip()
        if not label:
            continue
        kind = str(ent.get("kind", "other")).strip() or "other"
        span = str(ent.get("span_text", ent.get("match", ""))).strip()
        pos = _span_for_quote(chunk, span, base) if span else None
        if pos is None:
            pos = (base, min(base + len(chunk), base + 1 + len(label)))
        s0, s1 = pos
        ev = _envelope(
            event_id,
            chunk_index=chunk_index,
            label=label,
            start=s0,
            end=max(s0 + 1, s1),
            graph_epoch=graph_epoch,
        )
        out.append(ExtractedEntity(label=label, kind=kind, evidence_span=ev.evidence_span, envelope=ev))
    return out


def _default_anthropic_completer() -> Callable[[str], str]:
    from llm_provider_py.anthropic import AnthropicProvider

    p = AnthropicProvider(
        tenant_id="cartographer",
        agent_name="cartographer-extract",
    )
    sys_text = _system_prompt()

    def _c(chunk: str) -> str:
        msgs: _ChatBlock = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": chunk},
        ]
        return str(p.chat_complete(msgs, max_output_tokens=1024, temperature=0.0))

    return _c


def extract_map_reduce_llm(
    event: EventSignals,
    triage: TriageResult,
    *,
    graph_epoch: int = 0,
    completer: Callable[[str], str] | None = None,
) -> ExtractionBundle:
    """Map-reduce with an LLM per chunk. Pass ``completer(prompt_with_text)->str`` for tests; default Anthropic.

    If ``completer`` is omitted, uses :class:`AnthropicProvider` (requires API key in env).
    """
    if triage.triaged_out or not triage.would_consume_extraction:
        msg = "extract_map_reduce_llm requires a triage-passed event"
        raise ValueError(msg)
    c = completer or _default_anthropic_completer()
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
    segs = chunk_by_paragraphs(text, max_chars=MAX_CHUNK_CHARS)
    mapped: list[ExtractedEntity] = []
    for i, (base, chunk) in enumerate(segs):
        if not chunk.strip():
            continue
        mapped.extend(_llm_map_chunk(chunk, base, i, event.event_id, graph_epoch, c))
    return ExtractionBundle(
        source_event_id=event.event_id,
        graph_epoch=graph_epoch,
        full_text=text,
        entities=tuple(_dedupe(mapped)),
        relationships=(),
        blockers=(),
        candidate_learnings=(),
    )
