"""Integration kill-switch (Epic 2 Story 2-6) — plumb to Epic 3 providers + SQS + secrets later."""

from __future__ import annotations

import uuid
from typing import Annotated

from deployai_authz import AuthActor, can_access
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from control_plane.api.jwt_actor import bearer_auth_actor
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration
from control_plane.services.integration_kill_switch import disable_integration

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/catalog", summary="Available ingestion connectors and stub endpoints")
def get_integration_catalog() -> dict[str, object]:
    """Static catalog plus which optional OAuth env vars are set (not secret values)."""
    s = get_settings()
    g_mail = bool(s.google_gmail_client_id and s.google_gmail_client_secret and s.google_gmail_redirect_uri)
    slack_events = bool(s.slack_signing_secret)
    return {
        "version": 1,
        "providers": [
            {
                "id": "m365_calendar",
                "label": "Microsoft 365 Calendar",
                "status": "available",
                "auth": "oauth2",
                "connect_path": "/integrations/m365-calendar/connect",
            },
            {
                "id": "m365_mail",
                "label": "Microsoft 365 Exchange / Outlook mail",
                "status": "available",
                "auth": "oauth2",
                "connect_path": "/integrations/m365-mail/connect",
            },
            {
                "id": "m365_teams",
                "label": "Microsoft Teams (meeting transcripts)",
                "status": "available",
                "auth": "oauth2",
                "connect_path": "/integrations/m365-teams/connect",
            },
            {
                "id": "google_gmail",
                "label": "Google Gmail",
                "status": "preview" if g_mail else "stub",
                "auth": "oauth2",
                "connect_path": "/integrations/google-gmail/connect",
            },
            {
                "id": "slack",
                "label": "Slack",
                "status": "preview" if slack_events else "stub",
                "auth": "app_events",
                "events_path": "/integrations/slack/events",
            },
            {
                "id": "other_chat",
                "label": "Other chat (Discord, Zoom chat, etc.)",
                "status": "roadmap",
                "note": "Use catalog + internal ingest API; vendor-specific workers ship incrementally",
            },
        ],
    }


@router.post(
    "/{integration_id}/disable",
    status_code=status.HTTP_200_OK,
)
async def post_integration_disable(
    integration_id: uuid.UUID,
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> dict[str, object]:
    r = await session.execute(select(Integration).where(Integration.id == integration_id).limit(1))
    it = r.scalar_one_or_none()
    if it is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    d = can_access(
        actor,
        "integration:kill_switch",
        {"kind": "tenant", "id": str(it.tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    out = await disable_integration(session, integration_id)
    if out.get("not_found") is True:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return {k: v for k, v in out.items() if k != "not_found"}
