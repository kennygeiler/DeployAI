"""SAML 2.0 SP hooks (Story 2-2 follow-up).

Microsoft Entra is supported in production via **OIDC + PKCE** (`/auth/oidc/*`).
A full SAML SP (IdP metadata, signed ``<Response>`` validation, ``/auth/saml/acs``)
is tracked for enterprises that cannot use OIDC; it is not implemented in this
repository revision. These routes return **501** so load balancers and API
discovery see stable paths instead of 404.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/auth/saml", tags=["auth-saml"])


@router.get(
    "/login",
    summary="SAML SP-initiated sign-in (not implemented)",
)
async def saml_login() -> None:
    raise _not_implemented()


@router.post(
    "/acs",
    summary="SAML assertion consumer (not implemented)",
)
async def saml_acs() -> None:
    raise _not_implemented()


def _not_implemented() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "saml_not_implemented",
            "message": (
                "SAML 2.0 is not enabled. Configure Microsoft Entra for OpenID Connect per "
                "docs/auth/sso-setup.md and use /auth/oidc/login."
            ),
            "oidc_login_path": "/auth/oidc/login",
        },
    )
