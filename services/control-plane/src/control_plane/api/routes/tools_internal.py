"""Internal API: exercise individual Agent Kenny tools for dev + debugging.

Posts a JSON body matching the target tool's ``INPUT_SCHEMA``. Gated by
the same X-DeployAI-Internal-Key header as the rest of ``/internal/v1/...``
and additionally requires ``DEPLOYAI_TOOLS_DEBUG_ENABLED=1`` in the
environment so production deployments can opt out entirely.

The route exists for Phase 1 development. Phase 2 (LangGraph multi-step
loop) routes tool dispatch through the agent loop and this endpoint
becomes a manual debugging seam.
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.tools import (
    TOOL_REGISTRY,
    Citation,
    ToolError,
    ToolResult,
)
from control_plane.agents.tools.analysis import (
    get_decision_history,
    get_engagement_summary,
    get_open_risks,
)
from control_plane.agents.tools.escalate import propose_action
from control_plane.agents.tools.ledger import query_ledger, walk_chain
from control_plane.agents.tools.matrix import (
    get_matrix_neighbors,
    get_matrix_node,
    get_matrix_subgraph,
)
from control_plane.agents.tools.search import keyword_search, vector_search
from control_plane.agents.tools.synthesis import read_synthesis
from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session

router = APIRouter(prefix="/admin/tools", tags=["internal-agent-tools"])


def _debug_enabled() -> bool:
    """Allow the debug routes only when the env switch is on."""
    return os.environ.get("DEPLOYAI_TOOLS_DEBUG_ENABLED", "0") == "1"


def require_debug_enabled() -> None:
    if not _debug_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent-tools debug route disabled",
        )


class ToolInvokeBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    args: dict[str, Any] = Field(default_factory=dict)


class CitationRead(BaseModel):
    kind: str
    id: uuid.UUID


class ToolResultRead(BaseModel):
    name: str
    rows: list[dict[str, Any]]
    citations: list[CitationRead]
    truncated: bool
    next_cursor: str | None
    duration_ms: float
    detail: str | None = None


@router.get("", dependencies=[Depends(require_internal), Depends(require_debug_enabled)])
async def list_registered_tools() -> dict[str, Any]:
    """Return the JSON-schema registry. Useful for confirming a deploy."""
    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
            }
            for spec in TOOL_REGISTRY.values()
        ]
    }


def _coerce_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid ISO timestamp: {raw!r}",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"expected ISO timestamp string, got {type(raw).__name__}",
    )


async def _dispatch(
    name: str,
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    args: dict[str, Any],
    embedder: Any = None,
) -> ToolResult:
    common: dict[str, Any] = {
        "tenant_id": tenant_id,
        "engagement_id": engagement_id,
    }
    if name == "query_ledger":
        return await query_ledger(
            session,
            **common,
            source_kind=args.get("source_kind"),
            actor_id=args.get("actor_id"),
            from_=_coerce_datetime(args.get("from")),
            to=_coerce_datetime(args.get("to")),
            affects_entity_kind=args.get("affects_entity_kind"),
            affects_entity_id=args.get("affects_entity_id"),
            text_query=args.get("text"),
            limit=int(args.get("limit", 50)),
            cursor=args.get("cursor"),
        )
    if name == "walk_chain":
        return await walk_chain(
            session,
            **common,
            event_id=args["event_id"],
            direction=args.get("direction", "both"),
            max_depth=int(args.get("max_depth", 3)),
            max_nodes=int(args.get("max_nodes", 200)),
        )
    if name == "get_matrix_node":
        return await get_matrix_node(
            session,
            **common,
            node_id=args["node_id"],
            include_neighbors=bool(args.get("include_neighbors", True)),
        )
    if name == "get_matrix_neighbors":
        return await get_matrix_neighbors(
            session,
            **common,
            node_id=args["node_id"],
            k=int(args.get("k", 1)),
            edge_types=args.get("edge_types"),
            limit=int(args.get("limit", 100)),
        )
    if name == "get_matrix_subgraph":
        return await get_matrix_subgraph(
            session,
            **common,
            node_types=args.get("node_types"),
            edge_types=args.get("edge_types"),
            since=_coerce_datetime(args.get("since")),
            limit=int(args.get("limit", 100)),
        )
    if name == "read_synthesis":
        return await read_synthesis(
            session,
            **common,
            node_id=args.get("node_id"),
            agent=args.get("agent", "kenny"),
            insight_type=args.get("insight_type"),
            status=args.get("status"),
            include_stale=bool(args.get("include_stale", False)),
            limit=int(args.get("limit", 50)),
        )
    if name == "get_decision_history":
        return await get_decision_history(
            session,
            **common,
            limit=int(args.get("limit", 50)),
            status=args.get("status"),
        )
    if name == "get_open_risks":
        return await get_open_risks(
            session,
            **common,
            severity=args.get("severity"),
            limit=int(args.get("limit", 50)),
        )
    if name == "get_engagement_summary":
        return await get_engagement_summary(session, **common)
    if name == "keyword_search":
        return await keyword_search(
            session,
            **common,
            query=args["query"],
            kinds=args.get("kinds"),
            limit=int(args.get("limit", 25)),
        )
    if name == "vector_search":
        if embedder is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="vector_search unavailable: no embedder configured on app.state",
            )
        return await vector_search(
            session,
            **common,
            query=args["query"],
            kind=args.get("kind"),
            limit=int(args.get("limit", 10)),
            embedder=embedder,
        )
    if name == "propose_action":
        return await propose_action(
            session,
            **common,
            description=args["description"],
            priority=args["priority"],
            phase=args.get("phase", "P2_active"),
            evidence_node_ids=args.get("evidence_node_ids"),
            evidence_event_ids=args.get("evidence_event_ids"),
            rationale=args.get("rationale"),
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"unknown tool: {name!r}",
    )


@router.post(
    "/{name}",
    response_model=ToolResultRead,
    dependencies=[Depends(require_internal), Depends(require_debug_enabled)],
)
async def invoke_tool(
    name: str,
    body: ToolInvokeBody,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID, Query()],
) -> ToolResultRead:
    if name not in TOOL_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown tool: {name!r}",
        )
    embedder = getattr(request.app.state, "embedder", None)
    try:
        result = await _dispatch(
            name,
            session=session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            args=body.args,
            embedder=embedder,
        )
    except ToolError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    payload = dataclasses.asdict(result)
    payload["citations"] = [_citation_to_dict(c) for c in result.citations]
    return ToolResultRead(**payload)


def _citation_to_dict(c: Citation) -> dict[str, Any]:
    return {"kind": c.kind, "id": c.id}


__all__ = ["router"]
