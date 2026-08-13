"""Slack channel-scoped intake tables (Wave 5 SL1).

Consent model: inviting the DeployAI bot to a channel is the consent
boundary, and a :class:`SlackChannelMapping` row is the strategist's
explicit channel → engagement opt-in. Message content is only ever stored
for actively mapped channels (:class:`SlackStagingMessage`, later batched
into ``slack.thread`` canonical snapshots). :class:`SlackPendingChannel`
records channel id + name only — never message content — so the settings
UI can offer bot-invited-but-unmapped channels for mapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class SlackChannelMapping(Base):
    """One channel → engagement consent grant; ``revoked_at`` ends it (history kept)."""

    __tablename__ = "slack_channel_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(Text(), nullable=False)
    channel_name: Mapped[str] = mapped_column(Text(), nullable=False, server_default="")
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class SlackStagingMessage(Base):
    """One raw Slack message event for a mapped channel, awaiting snapshot flush."""

    __tablename__ = "slack_staging_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", "message_ts", name="uq_slack_staging_messages_msg"),
        Index(
            "ix_slack_staging_messages_unflushed",
            "tenant_id",
            "channel_id",
            postgresql_where=text("flushed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(Text(), nullable=False)
    message_ts: Mapped[str] = mapped_column(Text(), nullable=False)
    thread_ts: Mapped[str | None] = mapped_column(Text(), nullable=True)
    user_id: Mapped[str] = mapped_column(Text(), nullable=False, server_default="")
    text_body: Mapped[str] = mapped_column("text", Text(), nullable=False, server_default="")
    team_id: Mapped[str] = mapped_column(Text(), nullable=False, server_default="")
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    flushed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class SlackPendingChannel(Base):
    """Bot-invited channel with no mapping yet — id + name only, no content (consent gate)."""

    __tablename__ = "slack_pending_channels"
    __table_args__ = (UniqueConstraint("tenant_id", "channel_id", name="uq_slack_pending_channels_channel"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(Text(), nullable=False)
    channel_name: Mapped[str] = mapped_column(Text(), nullable=False, server_default="")
    first_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
