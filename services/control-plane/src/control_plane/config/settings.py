"""Environment-backed settings (Story 2-4: Redis + JWT)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_SESSION_TTL_MAX_SECONDS = 3600
"""Hard ceiling for ``demo_session_ttl_seconds`` — a demo session never outlives an hour."""


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

    # --- Wave 4S: public "View live demo" guest access ---
    demo_guest_enabled: bool = False
    """When True AND ``demo_tenant_id``/``demo_user_id`` are set, ``POST /internal/v1/demo/session``
    (still behind the internal key) mints short-TTL ``demo_guest`` sessions onto the demo tenant.
    NEVER enable on a deployment that hosts customer tenants — see docs/ops/cloud-deploy.md §7.1."""

    self_serve_signup_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEPLOYAI_SELF_SERVE_SIGNUP", "self_serve_signup_enabled"),
    )
    """``DEPLOYAI_SELF_SERVE_SIGNUP=1`` opens ``POST /api/v1/auth/signup`` (public
    workspace creation). Default OFF: customer deploys keep provisioning
    admin-only (``/platform/accounts``); enable on the public demo deploy."""

    demo_tenant_id: str | None = None
    """UUID of the disposable, pre-seeded demo tenant every guest session is scoped to."""

    demo_user_id: str | None = None
    """UUID of the seeded demo user row all guest sessions share (audit trails attribute to it)."""

    demo_session_ttl_seconds: int = Field(
        default=900,
        validation_alias=AliasChoices("DEPLOYAI_DEMO_SESSION_TTL", "demo_session_ttl_seconds"),
    )
    """Access-token TTL for demo guest sessions ONLY (env ``DEPLOYAI_DEMO_SESSION_TTL``).
    Clamped to [1, 3600] — a demo session never outlives an hour. Normal sessions keep
    ``access_token_ttl_seconds``; the demo mint threads this value explicitly."""

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

    oidc_jit_enabled: bool = True
    """When True (default), first OIDC login just-in-time provisions an ``app_users`` row on the
    SSO-pending tenant with the least-privilege ``pending_assignment`` role. Set
    ``DEPLOYAI_OIDC_JIT_ENABLED=0`` to reject unknown users at the callback with 403 instead."""

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

    ingest_upload_sqs_url: str | None = None
    (
        "SQS queue URL; ``/upload/artifacts/complete`` sends a job; run "
        "``python -m control_plane.workers.transcribe_upload``."
    )

    upload_asr_mode: Literal["stub", "transcribe"] = "stub"
    (
        "``stub`` = worker writes deterministic placeholder text. "
        "``transcribe`` = reserved for real AWS Transcribe (logs + stub until wired)."
    )

    graph_ingest_rps: float = 1000.0
    """Token-bucket rate for Microsoft Graph (Story 3-7); default 1000 req/s, configurable (NFR19)."""

    # --- Inbound API rate limiting (public surface; /internal + probes exempt) ---
    api_rate_limit_per_minute: int = 0
    """Sustained per-principal request budget for the public API surface.
    0 (default) disables the limiter entirely — existing deployments and test
    suites are untouched until an operator sets ``DEPLOYAI_API_RATE_LIMIT_PER_MINUTE``."""

    api_rate_limit_burst: int | None = None
    """Token-bucket capacity (max burst). Defaults to ``api_rate_limit_per_minute``."""

    # --- Outbound dependency circuit breakers (docs/ops/resilience.md) ---
    circuit_failure_threshold: int = 5
    """Consecutive failures before an outbound dependency's breaker opens
    (MCP connectors, Voyage embedder). On by default — a healthy dependency
    never trips. ``DEPLOYAI_CIRCUIT_FAILURE_THRESHOLD=0`` disables breakers
    entirely (every call goes to the network)."""

    circuit_cooldown_s: float = 30.0
    """Seconds an open breaker waits before admitting one half-open probe."""

    # --- Gmail / Slack (Epic 3+): optional; stub routes work without these ---
    google_gmail_client_id: str | None = None
    google_gmail_client_secret: str | None = None
    google_gmail_redirect_uri: str | None = None
    """Registered redirect for ``/integrations/google-gmail/callback`` when Gmail OAuth is implemented."""

    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_redirect_uri: str | None = None
    """OAuth install redirect, e.g. ``https://cp.example.com/integrations/slack/oauth/callback``."""

    slack_signing_secret: str | None = None
    """``/integrations/slack/events`` verifies Slack signatures with this secret. When unset,
    ``event_callback`` payloads are rejected (fail closed); the URL-verification challenge still works."""

    slack_allow_unsigned: bool = False
    """Dev-only escape hatch (``DEPLOYAI_SLACK_ALLOW_UNSIGNED=1``): process unsigned
    ``event_callback`` payloads when ``slack_signing_secret`` is unset. Never enable in production."""

    session_access_cookie: str = "dep_access"
    session_refresh_cookie: str = "dep_refresh"
    """HttpOnly cookies set on OIDC callback (browser clients); `POST /auth/refresh` still uses JSON body too."""

    # --- Observability: OpenTelemetry tracing (docs/ops/tracing.md) ---
    otel_exporter_otlp_endpoint: str | None = None
    """OTLP/HTTP collector base URL (``/v1/traces`` + ``/v1/metrics`` are appended).
    Unset → the SDK pipeline is never installed and every span helper is a no-op."""

    otel_service_name: str = "deployai-control-plane"
    """``service.name`` resource attribute on exported telemetry."""

    @field_validator("demo_session_ttl_seconds", mode="after")
    @classmethod
    def _clamp_demo_session_ttl(cls, v: int) -> int:
        return max(1, min(v, DEMO_SESSION_TTL_MAX_SECONDS))

    @field_validator(
        "allow_test_session_mint",
        "self_serve_signup_enabled",
        "demo_guest_enabled",
        "break_glass_bypass_webauthn",
        "slack_allow_unsigned",
        "oidc_jit_enabled",
        mode="before",
    )
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
