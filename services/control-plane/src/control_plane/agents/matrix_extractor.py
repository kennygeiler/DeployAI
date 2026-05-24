"""Phase 6 (increment 6.2c) — matrix extraction agent (Cartographer).

Pure function: read one canonical event + the engagement's current matrix
nodes for context, ask the LLM for typed matrix-entity proposals, return
validated ``ProposalDraft`` objects ready to persist as ``matrix_proposals``
rows. No FastAPI, no SQLAlchemy — caller composes with the I/O layers.

Design record: ``docs/product/matrix-extraction-agent.md``.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from llm_provider_py.types import ChatMessage, LLMProvider

from control_plane.domain.canonical_memory.matrix import (
    MATRIX_EDGE_TYPES,
    MATRIX_NODE_TYPES,
)

_log = logging.getLogger(__name__)

# Guardrails (design record §8).
_MAX_CONTENT_CHARS = 8000
_MAX_PROPOSALS = 20
_MAX_RATIONALE_CHARS = 500
_MAX_OUTPUT_TOKENS = 2000
_TEMPERATURE = 0.0


@dataclass(frozen=True)
class ExistingNode:
    """Minimal shape of an existing matrix node for prompt context."""

    id: uuid.UUID
    title: str
    node_type: str


@dataclass(frozen=True)
class ProposalDraft:
    """A validated matrix proposal ready to persist.

    For ``kind = "node"``, payload carries ``{node_type, title}``.
    For ``kind = "edge"``, payload carries
    ``{edge_type, from_node_id, to_node_id}`` — titles resolved by the
    extractor; un-resolvable edges are dropped, never auto-create nodes.
    """

    kind: str
    payload: dict[str, Any]
    rationale: str | None


def extract_matrix_proposals(
    *,
    event_id: uuid.UUID,
    event_source: str,
    event_occurred_at: datetime,
    event_payload: dict[str, Any],
    existing_nodes: list[ExistingNode],
    llm: LLMProvider,
    system_prompt: str | None = None,
    allowed_node_types: set[str] | None = None,
) -> list[ProposalDraft]:
    """Run one extraction pass for one canonical event.

    ``allowed_node_types`` is the per-tenant union of baked-in +
    custom-registered node-type slugs; default ``None`` falls back to
    ``MATRIX_NODE_TYPES``.
    """
    node_types = allowed_node_types if allowed_node_types is not None else set(MATRIX_NODE_TYPES)
    messages = _build_messages(
        event_source=event_source,
        event_occurred_at=event_occurred_at,
        event_payload=event_payload,
        existing_nodes=existing_nodes,
        system_prompt=system_prompt,
        allowed_node_types=node_types,
    )
    try:
        raw = llm.chat_complete(
            messages,
            temperature=_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:  # broad: best-effort, never fail extraction
        _log.warning("matrix_extractor: LLM call failed for event %s: %s", event_id, e)
        return []
    items = _parse_response(raw)
    if items is None:
        _log.warning("matrix_extractor: could not parse LLM response for event %s", event_id)
        return []
    return _validate(items, existing_nodes, node_types)


# --- prompt -----------------------------------------------------------------


def _build_messages(
    *,
    event_source: str,
    event_occurred_at: datetime,
    event_payload: dict[str, Any],
    existing_nodes: list[ExistingNode],
    system_prompt: str | None = None,
    allowed_node_types: set[str],
) -> list[ChatMessage]:
    return [
        {"role": "system", "content": system_prompt if system_prompt is not None else _system_prompt()},
        {
            "role": "user",
            "content": _user_prompt(
                event_source=event_source,
                event_occurred_at=event_occurred_at,
                event_payload=event_payload,
                existing_nodes=existing_nodes,
                allowed_node_types=allowed_node_types,
            ),
        },
    ]


def default_system_prompt() -> str:
    """Public accessor for the baked-in system prompt (Sprint 5).

    Route handlers pass this as the ``default_prompt`` to
    ``resolve_tenant_prompt`` so a tenant override can swap it in.
    """
    return _system_prompt()


def _system_prompt() -> str:
    node_types = " | ".join(f'"{t}"' for t in MATRIX_NODE_TYPES)
    edge_types = " | ".join(f'"{t}"' for t in MATRIX_EDGE_TYPES)
    return (
        "You are the Cartographer for DeployAI's deployment matrix.\n"
        "\n"
        "You read one interaction (meeting note, email, field note, or manual\n"
        "import) and propose typed matrix entities the interaction supports.\n"
        "\n"
        "Return a JSON array. Each element is one of:\n"
        "\n"
        '  { "kind": "node",\n'
        f'    "node_type": {node_types},\n'
        '    "title": string,\n'
        '    "rationale": string (<= 200 chars, what in the text supports this) }\n'
        "\n"
        '  { "kind": "edge",\n'
        f'    "edge_type": {edge_types},\n'
        '    "from_title": string (must match an existing matrix node title),\n'
        '    "to_title": string (must match an existing matrix node title),\n'
        '    "rationale": string }\n'
        "\n"
        "Rules:\n"
        "- Only propose what the text clearly supports. Return [] if nothing extractable.\n"
        "- Do not duplicate existing matrix nodes — prefer drawing edges to them.\n"
        "- Output ONLY the JSON array. No prose, no code fences, no commentary."
    )


def _user_prompt(
    *,
    event_source: str,
    event_occurred_at: datetime,
    event_payload: dict[str, Any],
    existing_nodes: list[ExistingNode],
    allowed_node_types: set[str],
) -> str:
    nodes_block = "\n".join(f"- {n.title} ({n.node_type})" for n in existing_nodes) if existing_nodes else "(none yet)"
    content_text = _content_to_text(event_payload)
    if len(content_text) > _MAX_CONTENT_CHARS:
        content_text = content_text[:_MAX_CONTENT_CHARS] + "\n…[truncated]"
    # Custom-only types (not in the baked-in list) get surfaced separately
    # so the LLM knows it can emit them in addition to the system-prompt set.
    extra = sorted(allowed_node_types - set(MATRIX_NODE_TYPES))
    extra_block = ""
    if extra:
        extra_block = (
            "Additional tenant-registered node_type values you may use:\n"
            + "\n".join(f'- "{t}"' for t in extra)
            + "\n\n"
        )
    return (
        f"{extra_block}"
        f"Existing matrix nodes for this engagement:\n{nodes_block}\n\n"
        f"Interaction:\n"
        f"- source: {event_source}\n"
        f"- occurred_at: {event_occurred_at.isoformat()}\n"
        f"- content:\n"
        f"{content_text}\n"
    )


def _content_to_text(payload: dict[str, Any]) -> str:
    """Reasonable text for the LLM from the event payload."""
    content = payload.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text
        try:
            return json.dumps(content, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            return str(content)
    return json.dumps(payload, indent=2, sort_keys=True)


# --- parse + validate -------------------------------------------------------


def _parse_response(raw: str) -> list[dict[str, Any]] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
    return out[:_MAX_PROPOSALS]


def _validate(
    items: list[dict[str, Any]],
    existing_nodes: list[ExistingNode],
    allowed_node_types: set[str],
) -> list[ProposalDraft]:
    by_title: dict[str, uuid.UUID] = {n.title: n.id for n in existing_nodes}
    drafts: list[ProposalDraft] = []
    for item in items:
        kind = item.get("kind")
        rationale = _trim_rationale(item.get("rationale"))
        if kind == "node":
            node_type = item.get("node_type")
            title = item.get("title")
            if (
                not isinstance(node_type, str)
                or node_type not in allowed_node_types
                or not isinstance(title, str)
                or not title.strip()
            ):
                _log.info("matrix_extractor: dropping invalid node proposal: %s", item)
                continue
            drafts.append(
                ProposalDraft(
                    kind="node",
                    payload={"node_type": node_type, "title": title.strip()},
                    rationale=rationale,
                )
            )
        elif kind == "edge":
            edge_type = item.get("edge_type")
            from_title = item.get("from_title")
            to_title = item.get("to_title")
            if (
                not isinstance(edge_type, str)
                or edge_type not in MATRIX_EDGE_TYPES
                or not isinstance(from_title, str)
                or not isinstance(to_title, str)
            ):
                _log.info("matrix_extractor: dropping invalid edge proposal: %s", item)
                continue
            from_id = by_title.get(from_title)
            to_id = by_title.get(to_title)
            if from_id is None or to_id is None:
                _log.info(
                    "matrix_extractor: dropping edge proposal — unresolved title(s): %s -> %s",
                    from_title,
                    to_title,
                )
                continue
            drafts.append(
                ProposalDraft(
                    kind="edge",
                    payload={
                        "edge_type": edge_type,
                        "from_node_id": str(from_id),
                        "to_node_id": str(to_id),
                    },
                    rationale=rationale,
                )
            )
        else:
            _log.info("matrix_extractor: dropping proposal with unknown kind: %s", item)
    return drafts


def _trim_rationale(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > _MAX_RATIONALE_CHARS:
        return s[:_MAX_RATIONALE_CHARS]
    return s
