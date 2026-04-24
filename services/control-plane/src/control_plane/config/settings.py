"""Environment-backed settings (Story 2-4: Redis + JWT)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ControlPlaneSettings(BaseSettings):
    """Load from process env. Prefix ``DEPLOYAI_`` (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_prefix="DEPLOYAI_",
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Async redis URL; use rediss:// in prod (TLS)",
    )

    redis_ssl_ca_certs: str | None = None
    redis_ssl_certfile: str | None = None
    redis_ssl_keyfile: str | None = None

    jwt_issuer: str = "deployai-control-plane"
    jwt_audience: str = "deployai"
    jwt_kid: str = "default"
    jwt_private_key_path: str | None = None
    jwt_public_key_paths: str = ""
    # Comma-separated PEM paths; first private signs; all publics verify (rotation, NFR76).
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60

    allow_test_session_mint: bool = False
    """When True, ``POST /internal/v1/test/session-tokens`` may mint (still needs internal key)."""

    tenant_dek_mode: Literal["stub", "aws_kms"] = "stub"
    """``stub`` stores random key material (dev/tests). ``aws_kms`` — TODO(Story 2-5+): real KMS wrap."""

    break_glass_bypass_webauthn: bool = False
    """When True (dev/tests only), skip ``X-DeployAI-WebAuthn-Assertion`` on break-glass routes. Production: False."""

    # --- Story 2-2: Entra-compatible OIDC (SAML in a later slice) ---
    oidc_issuer: str | None = None
    # e.g. https://login.microsoftonline.com/<tenant-id>/v2.0 (must serve openid-configuration).
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None
    """Registered reply URL, e.g. ``https://cp.example.com/auth/oidc/callback`` (must match Entra app registration)."""

    # --- Epic 3 / Story 3-1: M365 Calendar (Graph delegated) ---
    m365_oauth_issuer: str | None = None
    """If unset, calendar OAuth uses ``oidc_issuer`` (same Entra app registration)."""
    m365_oauth_client_id: str | None = None
    m365_oauth_client_secret: str | None = None
    m365_calendar_redirect_uri: str | None = None
    """Reply URL for ``/integrations/m365-calendar/callback``; must be registered in Entra for this app."""

    m365_mail_redirect_uri: str | None = None
    """Reply URL for ``/integrations/m365-mail/callback``; register separately in Entra."""

    m365_teams_redirect_uri: str | None = None
    """Reply URL for ``/integrations/m365-teams/callback``; add Teams + transcript scopes in Entra."""

    ingest_email_body_mode: Literal["stub", "s3"] = "stub"
    """``stub`` stores bodies on disk (see below); ``s3`` is not implemented yet."""

    ingest_email_body_stub_dir: str | None = None
    """Base directory for stub email bodies; default uses a subdir of the system temp dir."""

    # --- Epic 3 / Story 3-4: direct-to-S3 meeting audio upload (presigned POST) ---
    upload_artifact_s3_bucket: str | None = None
    """When set, ``POST /upload/artifacts/presign`` can mint S3 POST policies (see AR11)."""

    upload_artifact_s3_region: str = "us-east-1"
    upload_artifact_s3_key_prefix: str = "ingest/artifacts"
    """Key prefix (no leading/trailing slash). Objects: ``{prefix}/tenant/{tid}/...``"""

    session_access_cookie: str = "dep_access"
    session_refresh_cookie: str = "dep_refresh"
    """HttpOnly cookies set on OIDC callback (browser clients); `POST /auth/refresh` still uses JSON body too."""

    @field_validator("allow_test_session_mint", "break_glass_bypass_webauthn", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)


@lru_cache(maxsize=1)
def get_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
