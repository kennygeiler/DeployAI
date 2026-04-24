"""Slack — Events API URL verification and no-op event sink (signing verification is optional; Epic 3+)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from control_plane.config.settings import get_settings

router = APIRouter(prefix="/integrations/slack", tags=["integrations-slack"])


def _verify_slack_signature(*, body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if not secret or not signature.startswith("v0="):
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > 60 * 5:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    dig = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"v0={dig}")


@router.post(
    "/events",
    summary="Slack Events API (URL challenge + event envelope stub)",
    response_model=None,
)
async def slack_events(request: Request) -> JSONResponse | PlainTextResponse:
    body = await request.body()
    secret = (get_settings().slack_signing_secret or "").strip()
    sig = (request.headers.get("X-Slack-Signature") or "").strip()
    ts = (request.headers.get("X-Slack-Request-Timestamp") or "").strip()
    if secret:
        if not body or not _verify_slack_signature(body=body, timestamp=ts, signature=sig, secret=secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Slack signature",
            )

    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON body required",
        ) from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expected JSON object")

    if data.get("type") == "url_verification":
        ch = data.get("challenge")
        if isinstance(ch, str) and ch:
            return PlainTextResponse(content=ch, status_code=200, media_type="text/plain")
        return JSONResponse(content={"error": "missing challenge"}, status_code=400)

    if data.get("type") in ("event_callback", "event"):
        return JSONResponse(content={"ok": True}, status_code=200)

    return JSONResponse(content={"ok": True}, status_code=200)
