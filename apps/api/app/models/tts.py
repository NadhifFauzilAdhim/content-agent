"""Global text-to-speech configuration.

Channel-level overrides live on ``channel_settings`` (``voice_provider`` / ``voice_id`` /
``voice_config``); per-workflow overrides travel in the workflow input; per-scene overrides are
part of the voice agent payload. This table holds the workspace default plus the optional
fallback provider. Precedence is resolved (and shown to the user) by
:class:`app.services.tts.TTSConfigurationService`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class TTSConfiguration(TimestampMixin, UUIDMixin, Base):
    __tablename__ = "tts_configurations"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_tts_config_workspace"),
        Index("ix_tts_config_provider", "provider_slug"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider_slug: Mapped[str] = mapped_column(String(64))
    fallback_provider_slug: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(120))
    voice_id: Mapped[str | None] = mapped_column(String(160))
    language: Mapped[str | None] = mapped_column(String(16))
    output_format: Mapped[str | None] = mapped_column(String(32))
    voice_settings: Mapped[dict] = mapped_column(default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
