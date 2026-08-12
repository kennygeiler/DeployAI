"""Demo guest session mint (Wave 4S showcase) — behind X-DeployAI-Internal-Key.

``POST /internal/v1/demo/session`` mints a short-TTL session with the single
``demo_guest`` role, always for the configured demo user on the configured demo
tenant. The web app's ``GET /api/auth/demo`` route calls this server-side with
the internal key and sets the resulting access token as the session cookie, so
"View live demo" works with zero token gymnastics for the visitor.

Security posture (be honest about it):

- The route is 404 unless ``DEPLOYAI_DEMO_GUEST_ENABLED=1`` AND both
  ``DEPLOYAI_DEMO_TENANT_ID`` / ``DEPLOYAI_DEMO_USER_ID`` are set, and it still
  requires the internal key — the public internet can never call it directly.
- ``demo_guest`` holds ``canonical:read`` only (see docs/authz/role-matrix.md):
  ``/admin`` and ``/api/internal/v1`` proxy surfaces are denied at the web
  middleware, and the authz cross-tenant rule pins every call to the demo tenant.
- Residual risk (accepted for wave 1 of this feature): BFF mutation routes that
  gate with ``canonical:read`` today (single proposal accept/reject, review-item
  resolve/dismiss, insight actions, onboarding seeds) remain callable by a
  demo_guest session. Mitigation: the demo tenant is disposable and isolated by
  tenancy/RLS; reseed it at will. Never enable demo mode on a deployment that
  hosts customer tenants.
- Sessions use a demo-specific TTL: ``DEPLOYAI_DEMO_SESSION_TTL`` (seconds,
  default 900, clamped to 3600 max — see ``demo_session_ttl_seconds`` in
  settings). Normal sessions keep the standard access-token TTL. The refresh
  JTI is returned so the caller *could* extend a demo, but the web demo route
  intentionally sets only the access cookie — a demo session simply expires.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from control_plane.auth.session_service import issue_tokens
from control_plane.config.internal_auth import require_internal
from control_plane.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo-session"])

DEMO_GUEST_ROLE = "demo_guest"


def _demo_config() -> tuple[uuid.UUID, uuid.UUID]:
    """Parsed (tenant_id, user_id) when demo mode is fully configured, else 404.

    404 (not 403) so a probe cannot distinguish "disabled" from "absent".
    """
    s = get_settings()
    detail = (
        "Demo sessions are disabled "
        "(set DEPLOYAI_DEMO_GUEST_ENABLED=1 + DEPLOYAI_DEMO_TENANT_ID + DEPLOYAI_DEMO_USER_ID)"
    )
    if not (s.demo_guest_enabled and s.demo_tenant_id and s.demo_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    try:
        return uuid.UUID(s.demo_tenant_id), uuid.UUID(s.demo_user_id)
    except ValueError:
        logger.error("demo_session.misconfigured_ids", extra={"tenant": s.demo_tenant_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from None


@router.post("/session", dependencies=[Depends(require_internal)], status_code=status.HTTP_201_CREATED)
async def mint_demo_session() -> dict[str, object]:
    """Mint a ``demo_guest`` session on the demo tenant. No request body: the
    caller cannot choose roles, tenant, or user — everything comes from settings.
    """
    tenant_id, user_id = _demo_config()
    pair = await issue_tokens(
        tenant_id,
        user_id,
        [DEMO_GUEST_ROLE],
        access_ttl_seconds=get_settings().demo_session_ttl_seconds,
    )
    logger.info(
        "demo_session.minted",
        extra={"tenant_id": str(tenant_id), "user_id": str(user_id)},
    )
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_jti,
        "token_type": pair.token_type,
        "expires_in": pair.expires_in,
        "tenant_id": str(tenant_id),
        "roles": [DEMO_GUEST_ROLE],
    }
