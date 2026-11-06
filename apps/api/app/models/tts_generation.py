"""TTS generation history and usage accounting.

``tts_generations`` records every synthesis request (studio test, comparison or production
narration) with provider metadata, the stored audio path, per-chunk manifest, latency and both
estimated and actual cost. ``tts_usage_logs`` is an append-only usage ledger with provider-fair
units (characters — the billing unit of both Cartesia and ElevenLabs) so spend can be reconciled
independently of generation retention.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow

GENERATION_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
TRIGGERS = ("studio", "compare", "production", "voice_agent")


class TTSGeneration(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tts_generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("request_key", name="uq_tts_generation_request_key"),
        Index("ix_tts_gen_workspace_created", "workspace_id", "created_at"),
        Index("ix_tts_gen_provider_created", "provider", "created_at"),
        Index("ix_tts_gen_status", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120), default="")
    voice_id: Mapped[str | None] = mapped_column(String(160))
    language: Mapped[str | None] = mapped_column(String(16))
    input_text: Mapped[str] = mapped_column(Text)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    audio_path: Mapped[str | None] = mapped_column(String(500))
    audio_format: Mapped[str | None] = mapped_column(String(32))
    mime_type: Mapped[str | None] = mapped_column(String(80))
    audio_duration: Mapped[float] = mapped_column(Float, default=0)
    generation_latency: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    status: Mapped[str] = mapped_column(String(16), default="running")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    provider_request_id: Mapped[str | None] = mapped_column(String(120))
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_from: Mapped[str | None] = mapped_column(String(64))
    trigger: Mapped[str] = mapped_column(String(16), default="studio")
    is_test: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(16), default="single")  # single | dialogue
    chunk_count: Mapped[int] = mapped_column(Integer, default=1)
    chunk_manifest: Mapped[list] = mapped_column(default=list)
    settings: Mapped[dict] = mapped_column(default=dict)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL"), index=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_projects.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    request_key: Mapped[str] = mapped_column(String(80))


class TTSUsageLog(UUIDMixin, Base):
    __tablename__ = "tts_usage_logs"
    __table_args__ = (
        Index("ix_tts_usage_workspace_created", "workspace_id", "created_at"),
        Index("ix_tts_usage_provider_created", "provider", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tts_generations.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120), default="")
    operation: Mapped[str] = mapped_column(String(32), default="tts_speech")
    usage_quantity: Mapped[float] = mapped_column(Float, default=0)
    usage_unit: Mapped[str] = mapped_column(String(24), default="characters")
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="succeeded")
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL")
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL")
    )
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_projects.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TTSPreviewCache(UUIDMixin, Base):
    """Voice preview audio fetched with the API key, served to the browser through the API.

    Cartesia preview files require the bearer token, so the bytes are cached (short TTL) and
    streamed from ``/api/v1/tts/voices/{provider}/{voice_id}/preview`` — the key never reaches the
    browser and providers never see a cross-origin request.
    """

    __tablename__ = "tts_preview_cache"
    __table_args__ = (UniqueConstraint("provider", "voice_id", name="uq_tts_preview"),)

    provider: Mapped[str] = mapped_column(String(64))
    voice_id: Mapped[str] = mapped_column(String(160))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    mime: Mapped[str] = mapped_column(String(80), default="audio/mpeg")
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
