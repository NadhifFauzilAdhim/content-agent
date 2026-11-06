"""Generated content: projects, scripts, storyboards, scenes, assets, renders."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

PROJECT_STATUSES = (
    "draft",
    "in_production",
    "awaiting_approval",
    "approved",
    "rejected",
    "scheduled",
    "published",
    "failed",
    "archived",
)


class ContentProject(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "content_projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','in_production','awaiting_approval','approved','rejected',"
            "'scheduled','published','failed','archived')",
            name="status_valid",
        ),
        Index("ix_projects_channel_created", "channel_id", "created_at"),
        Index("ix_projects_workspace_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    idea_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("content_ideas.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    language: Mapped[str] = mapped_column(String(12), default="en")
    format: Mapped[str] = mapped_column(String(8), default="16:9")
    estimated_duration_s: Mapped[int | None] = mapped_column(Integer)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    metadata_json: Mapped[dict] = mapped_column(default=dict)  # SEO block
    thumbnail_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL", use_alter=True)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scripts: Mapped[list[Script]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Script.version"
    )


class Script(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_script_version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    narration: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_duration_s: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    generated_by: Mapped[str | None] = mapped_column(String(64))  # agent key
    raw_output: Mapped[dict] = mapped_column(default=dict)

    project: Mapped[ContentProject] = relationship(back_populates="scripts")
    storyboards: Mapped[list[Storyboard]] = relationship(
        back_populates="script", cascade="all, delete-orphan"
    )


class Storyboard(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "storyboards"

    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    style_guide: Mapped[str] = mapped_column(Text, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    script: Mapped[Script] = relationship(back_populates="storyboards")
    scenes: Mapped[list[Scene]] = relationship(
        back_populates="storyboard", cascade="all, delete-orphan", order_by="Scene.index"
    )


class Scene(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("storyboard_id", "index", name="uq_scene_board_index"),
        Index("ix_scenes_board", "storyboard_id", "index"),
    )

    storyboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storyboards.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    narration: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[list] = mapped_column(default=list)
    camera: Mapped[str | None] = mapped_column(String(160))
    composition: Mapped[str | None] = mapped_column(Text)
    characters: Mapped[list] = mapped_column(default=list)
    background: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    sfx: Mapped[list] = mapped_column(default=list)
    duration_s: Mapped[float] = mapped_column(Numeric(7, 2), default=6)
    transition: Mapped[str] = mapped_column(String(32), default="fade")

    storyboard: Mapped[Storyboard] = relationship(back_populates="scenes")


class MediaAsset(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (Index("ix_media_project_kind", "project_id", "kind"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="image")
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(80), default="image/png")
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(120))
    license: Mapped[str] = mapped_column(String(60), default="ai-generated")
    prompt: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    status: Mapped[str] = mapped_column(String(16), default="ready")


class AudioAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (Index("ix_audio_project", "project_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="narration")
    voice_id: Mapped[str | None] = mapped_column(String(160))
    model_id: Mapped[str | None] = mapped_column(String(120))
    voice_settings: Mapped[dict] = mapped_column(default=dict)
    output_format: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    duration_s: Mapped[float] = mapped_column(Numeric(7, 2), default=0)
    sample_rate: Mapped[int] = mapped_column(Integer, default=44100)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)


class VideoRender(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "video_renders"
    __table_args__ = (Index("ix_renders_project_created", "project_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    template: Mapped[str] = mapped_column(String(60), default="editorial-storybook")
    resolution: Mapped[str] = mapped_column(String(16), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=30)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    subtitle_key: Mapped[str | None] = mapped_column(String(500))
    duration_s: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
