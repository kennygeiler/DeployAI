"""Google Gmail — OAuth surface reserved; full Graph/Gmail API sync is not wired in v1 (Epic 3+)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from control_plane.config.settings import get_settings

router = APIRouter(prefix="/integrations/google-gmail", tags=["integrations-google-gmail"])


@router.get(
    "/connect",
    summary="Start Google Gmail OAuth (placeholder)",
    response_model=None,
)
async def google_gmail_connect() -> dict[str, str]:
    s = get_settings()
    if not (
        (s.google_gmail_client_id or "").strip()
        and (s.google_gmail_client_secret or "").strip()
        and (s.google_gmail_redirect_uri or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail integration is not configured. Set DEPLOYAI_GOOGLE_GMAIL_CLIENT_ID, "
                "DEPLOYAI_GOOGLE_GMAIL_CLIENT_SECRET, and DEPLOYAI_GOOGLE_GMAIL_REDIRECT_URI when ready; "
                "OAuth flow implementation is still pending."
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Gmail OAuth redirect is not implemented yet; see /integrations/catalog.",
    )
