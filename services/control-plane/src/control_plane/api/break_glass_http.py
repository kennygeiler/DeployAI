"""HTTP helpers for break-glass routes (WebAuthn step-up placeholder)."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from control_plane.config.settings import get_settings


def require_break_glass_webauthn(request: Request) -> None:
    """Production: require ``X-DeployAI-WebAuthn-Assertion``; dev/tests can bypass with settings."""
    if get_settings().break_glass_bypass_webauthn:
        return
    if not (request.headers.get("X-DeployAI-WebAuthn-Assertion") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WebAuthn step-up required (X-DeployAI-WebAuthn-Assertion)",
        )
