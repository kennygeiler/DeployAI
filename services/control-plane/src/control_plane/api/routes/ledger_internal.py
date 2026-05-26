"""Internal API: timeline-ledger read path (Phase F1.c).

Paginated chronological reads + single-event-with-expanded-edges over
`ledger_events` + `ledger_event_causes` + `ledger_event_affects`. Tenant
isolation goes through `_require_engagement` (same pattern as
`engagement_events.py`).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections import deque
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import _require_engagement, require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects, LedgerEventCause

router = APIRouter(prefix="/engagements", tags=["internal-ledger"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_DEFAULT_CHAIN_DEPTH = 3
_MAX_CHAIN_DEPTH = 10
_DEFAULT_CHAIN_NODES = 200
_MAX_CHAIN_NODES = 500


class LedgerEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    occurred_at: datetime
    recorded_at: datetime
    actor_kind: str
    actor_id: str | None
    source_kind: str
    source_ref: uuid.UUID | None
    summary: str
    detail: dict[str, Any]


class LedgerEventAffectsRead(BaseModel):
    entity_kind: str
    entity_id: uuid.UUID


class LedgerEventDetailRead(LedgerEventRead):
    caused_by: list[uuid.UUID]
    affects: list[LedgerEventAffectsRead]


class LedgerPage(BaseModel):
    events: list[LedgerEventRead]
    next_cursor: str | None


@router.get(
    "/{engagement_id}/ledger",
    response_model=LedgerPage,
    dependencies=[Depends(require_internal)],
)
async def list_ledger_events(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    source_kind: Annotated[str | None, Query(max_length=400)] = None,
    actor_id: Annotated[str | None, Query(max_length=200)] = None,
    affects_entity_kind: Annotated[str | None, Query(max_length=64)] = None,
    affects_entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> LedgerPage:
    await _require_engagement(session, tenant_id, engagement_id)
    stmt = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tenant_id,
        LedgerEvent.engagement_id == engagement_id,
    )
    if from_ is not None:
        stmt = stmt.where(LedgerEvent.occurred_at >= from_)
    if to is not None:
        stmt = stmt.where(LedgerEvent.occurred_at < to)
    if source_kind is not None:
        # Accept comma-separated values from the BFF (e.g. "matrix_node_created,
        # matrix_node_updated"). The previous exact-equals comparison silently
        # returned zero rows whenever the BFF joined multiple kinds with a comma,
        # which broke the provenance "find root event for node" lookup.
        kinds = [k.strip() for k in source_kind.split(",") if k.strip()]
        if len(kinds) == 1:
            stmt = stmt.where(LedgerEvent.source_kind == kinds[0])
        elif len(kinds) > 1:
            stmt = stmt.where(LedgerEvent.source_kind.in_(kinds))
    if actor_id is not None:
        stmt = stmt.where(LedgerEvent.actor_id == actor_id)
    if affects_entity_id is not None:
        affects_subq = select(LedgerEventAffects.event_id).where(
            LedgerEventAffects.entity_id == affects_entity_id,
        )
        if affects_entity_kind is not None:
            affects_subq = affects_subq.where(
                LedgerEventAffects.entity_kind == affects_entity_kind,
            )
        stmt = stmt.where(LedgerEvent.id.in_(affects_subq))
    if cursor is not None:
        cursor_at, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                LedgerEvent.occurred_at < cursor_at,
                (LedgerEvent.occurred_at == cursor_at) & (LedgerEvent.id < cursor_id),
            )
        )
    stmt = stmt.order_by(LedgerEvent.occurred_at.desc(), LedgerEvent.id.desc()).limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.occurred_at, last.id)
    return LedgerPage(
        events=[LedgerEventRead.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get(
    "/{engagement_id}/ledger/{event_id}",
    response_model=LedgerEventDetailRead,
    dependencies=[Depends(require_internal)],
)
async def get_ledger_event(
    engagement_id: uuid.UUID,
    event_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> LedgerEventDetailRead:
    await _require_engagement(session, tenant_id, engagement_id)
    row = (
        await session.execute(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.engagement_id == engagement_id,
                LedgerEvent.id == event_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ledger event not found")

    causes = list(
        (await session.execute(select(LedgerEventCause.caused_by_id).where(LedgerEventCause.event_id == event_id)))
        .scalars()
        .all()
    )
    affects_rows = list(
        (await session.execute(select(LedgerEventAffects).where(LedgerEventAffects.event_id == event_id)))
        .scalars()
        .all()
    )

    base = LedgerEventRead.model_validate(row)
    return LedgerEventDetailRead(
        **base.model_dump(),
        caused_by=causes,
        affects=[LedgerEventAffectsRead(entity_kind=a.entity_kind, entity_id=a.entity_id) for a in affects_rows],
    )


class LedgerChainNode(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    source_kind: str
    summary: str
    actor_kind: str
    depth: int
    truncated: bool


class LedgerChainEdge(BaseModel):
    from_event_id: uuid.UUID
    to_event_id: uuid.UUID


class LedgerChainResponse(BaseModel):
    root_event_id: uuid.UUID
    nodes: list[LedgerChainNode]
    edges: list[LedgerChainEdge]
    truncated_at_depth: int | None
    truncated_node_count: int | None


@router.get(
    "/{engagement_id}/ledger/{event_id}/chain",
    response_model=LedgerChainResponse,
    dependencies=[Depends(require_internal)],
)
async def get_ledger_event_chain(
    engagement_id: uuid.UUID,
    event_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    direction: Annotated[str, Query(pattern="^(upstream|downstream|both)$")] = "both",
    max_depth: Annotated[int, Query(ge=1, le=_MAX_CHAIN_DEPTH)] = _DEFAULT_CHAIN_DEPTH,
    max_nodes: Annotated[int, Query(ge=1, le=_MAX_CHAIN_NODES)] = _DEFAULT_CHAIN_NODES,
) -> LedgerChainResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    root = (
        await session.execute(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.engagement_id == engagement_id,
                LedgerEvent.id == event_id,
            )
        )
    ).scalar_one_or_none()
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ledger event not found")

    walk_upstream = direction in ("upstream", "both")
    walk_downstream = direction in ("downstream", "both")

    nodes: dict[uuid.UUID, LedgerEvent] = {root.id: root}
    depths: dict[uuid.UUID, int] = {root.id: 0}
    edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
    truncated_ids: set[uuid.UUID] = set()
    truncated_at_depth: int | None = None
    truncated_node_count: int | None = None

    queue: deque[tuple[uuid.UUID, int]] = deque([(root.id, 0)])
    visited: set[uuid.UUID] = {root.id}

    while queue:
        current_id, depth = queue.popleft()
        up_rows: list[uuid.UUID] = []
        down_rows: list[uuid.UUID] = []
        if walk_upstream:
            up_rows = list(
                (
                    await session.execute(
                        select(LedgerEventCause.caused_by_id).where(LedgerEventCause.event_id == current_id)
                    )
                )
                .scalars()
                .all()
            )
        if walk_downstream:
            down_rows = list(
                (
                    await session.execute(
                        select(LedgerEventCause.event_id).where(LedgerEventCause.caused_by_id == current_id)
                    )
                )
                .scalars()
                .all()
            )
        neighbor_ids: list[uuid.UUID] = [*up_rows, *down_rows]

        if depth >= max_depth:
            if any(n not in visited for n in neighbor_ids):
                truncated_ids.add(current_id)
                if truncated_at_depth is None or depth < truncated_at_depth:
                    truncated_at_depth = depth
            continue

        for cid in up_rows:
            edges.add((current_id, cid))
        for cid in down_rows:
            edges.add((cid, current_id))

        for neighbor_id in neighbor_ids:
            if neighbor_id in visited:
                continue
            visited.add(neighbor_id)
            row = (
                await session.execute(
                    select(LedgerEvent).where(
                        LedgerEvent.tenant_id == tenant_id,
                        LedgerEvent.id == neighbor_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                continue
            if len(nodes) >= max_nodes:
                if truncated_node_count is None:
                    truncated_node_count = 0
                truncated_node_count += 1
                continue
            nodes[neighbor_id] = row
            depths[neighbor_id] = depth + 1
            queue.append((neighbor_id, depth + 1))

    edges_filtered = [
        LedgerChainEdge(from_event_id=src, to_event_id=dst) for (src, dst) in edges if src in nodes and dst in nodes
    ]

    chain_nodes = [
        LedgerChainNode(
            id=ev.id,
            occurred_at=ev.occurred_at,
            source_kind=ev.source_kind,
            summary=ev.summary,
            actor_kind=ev.actor_kind,
            depth=depths[ev.id],
            truncated=ev.id in truncated_ids,
        )
        for ev in nodes.values()
    ]
    chain_nodes.sort(key=lambda n: (n.depth, n.occurred_at, str(n.id)))

    return LedgerChainResponse(
        root_event_id=root.id,
        nodes=chain_nodes,
        edges=edges_filtered,
        truncated_at_depth=truncated_at_depth,
        truncated_node_count=truncated_node_count,
    )


def _encode_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    payload = json.dumps({"occurred_at": occurred_at.isoformat(), "event_id": str(event_id)})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(raw: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        parsed = json.loads(decoded)
        occurred_at = datetime.fromisoformat(parsed["occurred_at"])
        event_id = uuid.UUID(parsed["event_id"])
    except (binascii.Error, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid cursor",
        ) from exc
    return occurred_at, event_id
