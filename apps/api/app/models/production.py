"""Ideas, workflows, QC, approvals, publishing, analytics, usage and audit."""

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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow

WORKFLOW_STATUSES = (
    "pending",
    "planning",
    "script_generation",
    "storyboarding",
    "voice_generation",
    "visual_generation",
    "rendering",
    "quality_checking",
    "awaiting_approval",
    "publishing",
    "published",
    "failed",
    "cancelled",
)

_WS = "('pending','planning','script_generation','storyboarding','voice_generation'," \
      "'visual_generation','rendering','quality_checking','awaiting_approval'," \
      "'publishing','published','failed','cancelled')"


class ContentIdea(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "content_ideas"
    __table_args__ = (Index("ix_ideas_channel_created", "channel_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    topic: Mapped[str] = mapped_column(String(240))
    angle: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str | None] = mapped_column(String(160))
    brief: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="story")
    estimated_duration_s: Mapped[int] = mapped_column(Integer, default=240)
    score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    source: Mapped[str] = mapped_column(String(16), default="agent")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductionWorkflow(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "production_workflows"
    __table_args__ = (
        CheckConstraint(f"status IN {_WS}", name="status_valid"),
        UniqueConstraint("workflow_key", name="uq_workflow_key"),
        Index("ix_workflows_workspace_status", "workspace_id", "status"),
        Index("ix_workflows_channel_created", "channel_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    workflow_key: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[str | None] = mapped_column(String(120))
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | schedule
    status: Mapped[str] = mapped_column(String(24), default="pending")
    stage: Mapped[str] = mapped_column(String(32), default="planning")
    current_agent_key: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    input_json: Mapped[dict] = mapped_column(default=dict)
    output_json: Mapped[dict] = mapped_column(default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workflow_tasks"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_index", "attempt", name="uq_task_step_attempt"),
        Index("ix_tasks_workflow_step", "workflow_id", "step_index"),
        Index("ix_tasks_agent_status", "agent_key", "status"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    agent_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(120))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_json: Mapped[dict] = mapped_column(default=dict)
    output_json: Mapped[dict] = mapped_column(default=dict)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowLog(UUIDMixin, Base):
    __tablename__ = "workflow_logs"
    __table_args__ = (Index("ix_logs_workflow_at", "workflow_id", "at"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_tasks.id", ondelete="SET NULL"))
    level: Mapped[str] = mapped_column(String(12), default="info")
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "quality_reports"
    __table_args__ = (Index("ix_qc_project_created", "project_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_renders.id", ondelete="SET NULL"))
    score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    approval_status: Mapped[str] = mapped_column(String(16), default="review")  # pass | review | fail
    checks: Mapped[list] = mapped_column(default=list)
    issues: Mapped[list] = mapped_column(default=list)
    warnings: Mapped[list] = mapped_column(default=list)
    recommendations: Mapped[list] = mapped_column(default=list)
    regenerate: Mapped[list] = mapped_column(default=list)


class ApprovalRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approvals_status_created", "status", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="publish")
    requested_by_agent: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    summary: Mapped[dict] = mapped_column(default=dict)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision_note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishingJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (Index("ix_publish_status_created", "status", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_renders.id", ondelete="SET NULL"))
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    privacy: Mapped[str] = mapped_column(String(16), default="private")
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(default=list)
    playlist: Mapped[str | None] = mapped_column(String(160))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    youtube_video_id: Mapped[str | None] = mapped_column(String(32))


class YouTubeVideo(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "youtube_videos"
    __table_args__ = (UniqueConstraint("youtube_video_id", name="uq_yt_video_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_projects.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(240))
    url: Mapped[str] = mapped_column(String(300))
    privacy: Mapped[str] = mapped_column(String(16), default="private")
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=True)
    thumbnail_set: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalyticsSnapshot(UUIDMixin, Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (Index("ix_snapshots_video_captured", "youtube_video_id", "captured_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    youtube_video_id: Mapped[str] = mapped_column(String(32), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    ctr: Mapped[float | None] = mapped_column(Float)
    watch_time_minutes: Mapped[float] = mapped_column(Float, default=0)
    avg_view_duration_s: Mapped[float | None] = mapped_column(Float)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)


class AiUsageLog(UUIDMixin, Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        UniqueConstraint("request_key", name="uq_usage_request_key"),
        Index("ix_usage_workspace_created", "workspace_id", "created_at"),
        Index("ix_usage_provider_created", "provider_id", "created_at"),
        Index("ix_usage_agent_created", "agent_key", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="SET NULL"))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"))
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_workflows.id", ondelete="SET NULL")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_projects.id", ondelete="SET NULL")
    )
    agent_key: Mapped[str | None] = mapped_column(String(64))
    provider_slug: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    operation: Mapped[str] = mapped_column(String(24), default="llm_chat")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[float] = mapped_column(Float, default=0)
    unit_label: Mapped[str] = mapped_column(String(24), default="request")
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
