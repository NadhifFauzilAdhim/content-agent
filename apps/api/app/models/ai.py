"""AI provider registry and agent configuration."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

PROVIDER_KINDS = ("llm", "tts", "image", "video", "youtube", "storage")
HEALTH_STATES = ("unknown", "ok", "degraded", "error")


class AiProvider(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('llm', 'tts', 'image', 'video', 'youtube', 'storage')",
            name="kind_valid",
        ),
        UniqueConstraint("workspace_id", "kind", "slug", name="uq_provider_workspace_kind_slug"),
        Index("ix_providers_workspace_kind", "workspace_id", "kind"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    slug: Mapped[str] = mapped_column(String(64))  # adapter key, e.g. "openai", "cartesia", "mock"
    name: Mapped[str] = mapped_column(String(120))
    vendor: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str | None] = mapped_column(String(400))
    models: Mapped[list] = mapped_column(default=list)  # [{id, name, input_cost, output_cost}]
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # Bumped on every credential write. Running workflows pin the version they started with so a
    # rotation mid-run cannot swap keys underneath an in-flight generation.
    credential_version: Mapped[int] = mapped_column(Integer, default=0)
    credential_status: Mapped[str] = mapped_column(String(16), default="unset")  # unset|active|disabled
    credential_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_config: Mapped[dict] = mapped_column(default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Numeric(3, 0), default=100)
    health: Mapped[str] = mapped_column(String(16), default="unknown")
    health_detail: Mapped[str | None] = mapped_column(String(400))
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Agent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agents"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="generation")
    stage: Mapped[str] = mapped_column(String(32))
    port: Mapped[str] = mapped_column(String(16))  # llm | tts | image | video | rules | youtube
    default_system_prompt: Mapped[str | None] = mapped_column(Text)
    input_schema: Mapped[dict] = mapped_column(default=dict)
    output_schema: Mapped[dict] = mapped_column(default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    configurations: Mapped[list[AgentConfiguration]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentConfiguration(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_configurations"
    __table_args__ = (
        UniqueConstraint("agent_id", "channel_id", name="uq_agent_config_scope"),
        Index("ix_agent_config_agent", "agent_id"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="SET NULL")
    )
    fallback_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="SET NULL")
    )
    model: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    max_tokens: Mapped[int] = mapped_column(Numeric(6, 0), default=4096)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(default=dict)
    retry_policy: Mapped[dict] = mapped_column(
        default=lambda: {"max_attempts": 3, "initial_interval_s": 5, "backoff": 2.0}
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    agent: Mapped[Agent] = relationship(back_populates="configurations")
