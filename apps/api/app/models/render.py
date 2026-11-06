"""Render jobs for the Remotion engine.

A job is the durable record of one render: the exact storyboard snapshot sent to Remotion, its
status and progress, the worker process, and the produced artifacts. Storing the spec makes renders
reproducible (and lets the dashboard preview the same input props the renderer will use).

``VideoRender`` keeps its role as the project's "current video" pointer; ``RenderJob`` is the
execution history behind it (retries, scene-only re-renders, previews, cancellations).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow

RENDER_STATUSES = (
    "queued",
    "bundling",
    "rendering",
    "encoding",
    "validating",
    "succeeded",
    "failed",
    "cancelled",
)
_RS = "('queued','bundling','rendering','encoding','validating','succeeded','failed','cancelled')"

RENDER_KINDS = ("full", "scene", "preview")


class RenderJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "render_jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {_RS}", name="status_valid"),
        CheckConstraint("kind IN ('full','scene','preview')", name="kind_valid"),
        Index("ix_render_jobs_project_created", "project_id", "created_at"),
        Index("ix_render_jobs_workspace_status", "workspace_id", "status"),
        UniqueConstraint("idempotency_key", name="uq_render_job_idempotency"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL"), index=True
    )
    render_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("video_renders.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(12), default="full")
    template_id: Mapped[str] = mapped_column(String(48), default="youtube-editorial")
    composition_id: Mapped[str] = mapped_column(String(48), default="youtube-editorial")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    fps: Mapped[int] = mapped_column(Integer, default=30)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    frames: Mapped[int] = mapped_column(Integer, default=0)
    rendered_frames: Mapped[int] = mapped_column(Integer, default=0)
    spec: Mapped[dict] = mapped_column(default=dict)
    output_key: Mapped[str | None] = mapped_column(String(500))
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    poster_key: Mapped[str | None] = mapped_column(String(500))
    scene_indexes: Mapped[list] = mapped_column(default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_pid: Mapped[int | None] = mapped_column(Integer)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(120))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_bytes: Mapped[int | None] = mapped_column(BigInteger)


class RenderValidation(UUIDMixin, Base):
    """Output validation result for one render (dimensions, fps, duration, audio, streams)."""

    __tablename__ = "render_validations"
    __table_args__ = (Index("ix_render_validation_job", "job_id", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("render_jobs.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    passed: Mapped[bool] = mapped_column(default=False)
    checks: Mapped[list] = mapped_column(default=list)
    issues: Mapped[list] = mapped_column(default=list)
    video_codec: Mapped[str | None] = mapped_column(String(32))
    audio_codec: Mapped[str | None] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    bitrate_kbps: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RenderCostLog(UUIDMixin, Base):
    """Wall-clock compute spent rendering (useful when Remotion runs on a paid worker)."""

    __tablename__ = "render_cost_logs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("render_jobs.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[str] = mapped_column(String(48))
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    render_seconds: Mapped[float] = mapped_column(Float, default=0)
    frames: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
