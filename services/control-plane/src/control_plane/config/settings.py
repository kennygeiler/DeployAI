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
