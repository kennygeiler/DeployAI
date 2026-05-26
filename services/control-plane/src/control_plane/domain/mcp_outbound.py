"""ORM + Pydantic schemas for ``tenant_mcp_configs`` (scope-v2 §9.1).

One row per (tenant, named MCP integration) — the tenant-admin curated
catalog of external MCP servers Agent Kenny is allowed to call (Slack,
Linear, GDrive, Notion, GitHub for v1). See
``alembic/versions/20260613_0048_tenant_mcp_configs.py`` for the schema
and Wave 2D's ``mcp_client.py`` for the runtime that loads these rows.

The Wave 1A ORM + schemas exist so the Wave 2 CP routes
(``apps/web/src/app/(strategist)/settings/integrations/page.tsx`` POST/PATCH/DELETE
backends) compile against typed shapes from day one. No service-layer
glue here — that's Wave 2B.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

# Connector catalog kept in lockstep with the migration's CHECK constraint
# (``ck_tenant_mcp_configs_connector_kind``). Widening this set requires a
# matching alembic migration that ALTERs the CHECK + a new branch in the
# Wave 2D ``mcp_client.py`` connector registry.
ConnectorKind = Literal["slack", "linear", "gdrive", "notion", "github"]
CONNECTOR_KINDS: tuple[ConnectorKind, ...] = (
    "slack",
    "linear",
    "gdrive",
    "notion",
    "github",
)

# Transport catalog kept in lockstep with ``ck_tenant_mcp_configs_transport``.
# Wave 2's client only speaks ``http_sse``; ``stdio`` / ``websocket`` are
# left as future widenings.
McpTransport = Literal["http_sse"]
TRANSPORTS: tuple[McpTransport, ...] = ("http_sse",)


class TenantMcpConfig(Base):
    """One tenant-admin-enabled external MCP server Kenny may call."""

    __tablename__ = "tenant_mcp_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    connector_kind: Mapped[str] = mapped_column(Text(), nullable=False)
    transport: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        server_default=text("'http_sse'"),
    )
    endpoint: Mapped[str] = mapped_column(Text(), nullable=False)
    # TODO Wave 2D: write path will call
    # ``deployai_tenancy.envelope.encrypt_field`` so the bytes here are
    # pgcrypto ``pgp_sym_encrypt_bytea`` ciphertext keyed by the tenant
    # DEK. Wave 1A only ships the column shape so Wave 2 routes have a
    # stable target.
    encrypted_auth_token: Mapped[bytes | None] = mapped_column(BYTEA(), nullable=True)
    # Null = every tool the MCP advertises is allowed. Non-null = strict
    # allow-list of MCP tool names enforced server-side at agent loop
    # start (scope-v2 §9.4 — "Allow-list enforced server-side, not just
    # in UI").
    allowed_tools: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text()),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "connector_kind IN (" + ", ".join(f"'{k}'" for k in CONNECTOR_KINDS) + ")",
            name="ck_tenant_mcp_configs_connector_kind",
        ),
        CheckConstraint(
            "transport IN (" + ", ".join(f"'{t}'" for t in TRANSPORTS) + ")",
            name="ck_tenant_mcp_configs_transport",
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_tenant_mcp_configs_tenant_id_name",
        ),
        Index(
            "idx_tenant_mcp_configs_tenant_id_enabled",
            "tenant_id",
            "enabled",
        ),
    )


# ---------------------------------------------------------------------------
# Pydantic v2 schemas — request/response shapes for the Wave 2 CP routes.
# ---------------------------------------------------------------------------


class TenantMcpConfigCreate(BaseModel):
    """POST body for ``/internal/v1/tenant/mcp-configs``."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    connector_kind: ConnectorKind
    endpoint: Annotated[str, Field(min_length=1, max_length=2000)]
    transport: McpTransport = "http_sse"
    # Raw auth token (e.g. OAuth bearer); the Wave 2D write path encrypts
    # before persisting. Wave 1A leaves the field on the schema so the
    # contract doesn't reshape when encryption lands.
    auth_token: str | None = None
    allowed_tools: list[str] | None = None
    enabled: bool = True


class TenantMcpConfigUpdate(BaseModel):
    """PATCH body — every field optional; absent = leave unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    endpoint: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    transport: McpTransport | None = None
    auth_token: str | None = None
    allowed_tools: list[str] | None = None
    enabled: bool | None = None


class TenantMcpConfigRead(BaseModel):
    """GET response — ``encrypted_auth_token`` is never returned, only
    ``has_auth_token`` so the UI can render an indicator without ever
    pulling ciphertext over the wire.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    connector_kind: ConnectorKind
    transport: McpTransport
    endpoint: str
    has_auth_token: bool
    allowed_tools: list[str] | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: TenantMcpConfig) -> TenantMcpConfigRead:
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            connector_kind=row.connector_kind,
            transport=row.transport,
            endpoint=row.endpoint,
            has_auth_token=row.encrypted_auth_token is not None,
            allowed_tools=list(row.allowed_tools) if row.allowed_tools is not None else None,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = [
    "CONNECTOR_KINDS",
    "TRANSPORTS",
    "ConnectorKind",
    "McpTransport",
    "TenantMcpConfig",
    "TenantMcpConfigCreate",
    "TenantMcpConfigRead",
    "TenantMcpConfigUpdate",
]
