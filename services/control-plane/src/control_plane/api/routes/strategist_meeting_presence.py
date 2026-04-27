"""Epic 9 Story 9.1 — strategist meeting presence (stub until Graph calendar wiring).

``DEPLOYAI_STUB_IN_MEETING_TENANT_IDS`` — comma-separated tenant UUIDs that are treated as
``in_meeting: true`` for integration tests and local demos. Real Microsoft Graph polling lands in
the same contract in a follow-up; Oracle trigger timestamps are stubbed here.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from control_plane.config.internal_api import verify_internal_key

router = APIRouter(prefix="/strategist", tags=["internal-strategist-meeting"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class MeetingPresenceRead(BaseModel):
    in_meeting: bool
    meeting_id: str | None = None
    meeting_title: str | None = None
    oracle_in_meeting_alert_at: str | None = None
    detection_source: Literal["stub", "graph_cache", "oracle_signal", "off"] = Field(
        default="off",
        description="How the active-meeting signal was derived (stub until Graph calendar wiring).",
    )
    calendar_poll_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=30,
        description="Suggested client poll cadence for presence refresh (Story 9.1: ≤ 30 s).",
    )


def _stub_tenant_ids() -> set[str]:
    raw = os.environ.get("DEPLOYAI_STUB_IN_MEETING_TENANT_IDS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


@router.get(
    "/meeting-presence",
    response_model=MeetingPresenceRead,
    dependencies=[Depends(require_internal)],
)
async def read_meeting_presence(
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope for calendar / presence lookup.")],
) -> MeetingPresenceRead:
    tid = str(tenant_id)
    if tid in _stub_tenant_ids():
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return MeetingPresenceRead(
            in_meeting=True,
            meeting_id="00000000-0000-4000-8000-00000000c001",
            meeting_title="Stub meeting (Graph calendar deferred)",
            oracle_in_meeting_alert_at=now,
            # Contract: live Oracle uses ``oracle_signal``; stub tenants exercise the same shape.
            detection_source="oracle_signal",
            calendar_poll_interval_seconds=30,
        )
    return MeetingPresenceRead(
        in_meeting=False,
        meeting_id=None,
        meeting_title=None,
        oracle_in_meeting_alert_at=None,
        detection_source="off",
        calendar_poll_interval_seconds=30,
    )
