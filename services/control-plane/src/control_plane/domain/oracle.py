"""ORM: oracle_conversations + oracle_chat_turns (Phase G1.a).

One conversation per (tenant, engagement, actor user); chat turns are
append-only with the upstream context event ids carried alongside each
turn so the ledger dual-emit in the chat service can wire ``caused_by``
to the causal graph. See ``docs/design/post-f-polish.md`` §8.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class OracleConversation(Base):
    """One Mr. Oracle chat thread held by one user against one engagement."""

    __tablename__ = "oracle_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_turn_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"],
            ["engagements.tenant_id", "engagements.id"],
            ondelete="CASCADE",
            name="fk_oracle_conversations_engagement_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "engagement_id",
            "actor_user_id",
            name="uq_oracle_conversations_tenant_engagement_actor",
        ),
    )


class OracleChatTurn(Base):
    """One append-only turn in a Mr. Oracle conversation (role: user | oracle)."""

    __tablename__ = "oracle_chat_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oracle_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text(), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    context_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    tokens_used: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'oracle')", name="oracle_chat_turns_role_enum"),
        Index("ix_oracle_turns_convo_created", "conversation_id", "created_at"),
    )


ORACLE_TURN_ROLES: tuple[str, ...] = ("user", "oracle")


__all__ = ["ORACLE_TURN_ROLES", "OracleChatTurn", "OracleConversation"]
