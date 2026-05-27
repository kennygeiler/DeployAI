"""Internal API — tenant-wide outbound-MCP audit slice (Wave 3I).

Mounted under ``/internal/v1``. Returns the most recent ledger rows for
the MCP-outbound source_kinds (Wave 2D's runtime + Wave 2E/2F's config +
killswitch + oauth-rotation events) scoped to one tenant.

This is the thin GET route the admin "Agent Kenny — MCP activity" page
calls. The per-engagement ledger route already exists
(``ledger_internal.py`` accepts a comma-separated ``source_kind``), but
the admin panel is tenant-wide and bounded to the small MCP slice, so a
dedicated read keeps the BFF call shape obvious + lets us pin the
allowed source_kind set on the CP side too (defense in depth — the BFF
can't ask the route for arbitrary kinds).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.api.routes.tenants_internal import _require_tenant
from control_plane.db import get_app_db_session
from control_plane.domain.ledger import LedgerEvent

router = APIRouter(prefix="/tenants", tags=["internal-tenant-mcp-audit"])

# Match ``services/control-plane/src/control_plane/ledger/emitter.py`` —
# the four call-status kinds + the three config kinds + the OAuth
# rotation kind + the kill-switch flip. The admin page surfaces all of
# these so the auditor sees configuration changes interleaved with
# the calls those configurations produced.
_MCP_AUDIT_SOURCE_KINDS: tuple[str, ...] = (
    "mcp_outbound_call",
    "mcp_outbound_blocked",
    "mcp_outbound_rate_limited",
    "mcp_outbound_denied",
    "mcp_outbound_killswitch_changed",
    "mcp_config_created",
    "mcp_config_updated",
    "mcp_config_deleted",
    "mcp_oauth_token_rotated",
)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


class McpAuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID | None
    occurred_at: datetime
    actor_kind: str
    actor_id: str | None
    source_kind: str
    source_ref: uuid.UUID | None
    summary: str
    detail: dict[str, Any]


class McpAuditResponse(BaseModel):
    rows: list[McpAuditRow]


@router.get(
    "/{tenant_id}/mcp_audit",
    response_model=McpAuditResponse,
    dependencies=[Depends(require_internal)],
)
async def list_tenant_mcp_audit(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> McpAuditResponse:
    """Return the last ``limit`` MCP-related ledger rows for this tenant.

    Sorted newest first. Detail blob is whatever ``emit_ledger_event``
    persisted — already redacted on the write path (see
    ``_SECRET_KEY_NEEDLES``), so the route is a transparent read.
    """
    await _require_tenant(session, tenant_id)
    stmt = (
        select(LedgerEvent)
        .where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.source_kind.in_(_MCP_AUDIT_SOURCE_KINDS),
        )
        .order_by(LedgerEvent.occurred_at.desc(), LedgerEvent.id.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return McpAuditResponse(rows=[McpAuditRow.model_validate(r) for r in rows])


__all__ = ["router"]
