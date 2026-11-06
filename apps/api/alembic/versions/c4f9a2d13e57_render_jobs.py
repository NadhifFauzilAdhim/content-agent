"""render jobs, validations and render cost logs (Remotion engine)

Adds:
* ``render_jobs`` — one row per Remotion render (spec snapshot, status, progress, artifacts)
* ``render_validations`` — ffprobe-based output checks per job
* ``render_cost_logs`` — wall-clock compute per render
* retires the ``ffmpeg`` video provider row (composition is Remotion-only)

Revision ID: c4f9a2d13e57
Revises: 9a1c4d2e77b0
Create Date: 2026-11-06 10:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f9a2d13e57"
down_revision: str | None = "9a1c4d2e77b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "render_jobs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("render_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("template_id", sa.String(length=48), nullable=False),
        sa.Column("composition_id", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("frames", sa.Integer(), nullable=False),
        sa.Column("rendered_frames", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("output_key", sa.String(length=500), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("poster_key", sa.String(length=500), nullable=True),
        sa.Column("scene_indexes", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_pid", sa.Integer(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_bytes", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','bundling','rendering','encoding','validating','succeeded',"
            "'failed','cancelled')",
            name=op.f("ck_render_jobs_status_valid"),
        ),
        sa.CheckConstraint("kind IN ('full','scene','preview')", name=op.f("ck_render_jobs_kind_valid")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_render_jobs_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["content_projects.id"],
                                name=op.f("fk_render_jobs_project_id_content_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["production_workflows.id"],
                                name=op.f("fk_render_jobs_workflow_id_production_workflows"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["render_id"], ["video_renders.id"],
                                name=op.f("fk_render_jobs_render_id_video_renders"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"],
                                name=op.f("fk_render_jobs_requested_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_jobs")),
        sa.UniqueConstraint("idempotency_key", name="uq_render_job_idempotency"),
    )
    with op.batch_alter_table("render_jobs") as batch:
        batch.create_index(batch.f("ix_render_jobs_workspace_id"), ["workspace_id"])
        batch.create_index(batch.f("ix_render_jobs_project_id"), ["project_id"])
        batch.create_index(batch.f("ix_render_jobs_workflow_id"), ["workflow_id"])
        batch.create_index("ix_render_jobs_project_created", ["project_id", "created_at"])
        batch.create_index("ix_render_jobs_workspace_status", ["workspace_id", "status"])

    op.create_table(
        "render_validations",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("video_codec", sa.String(length=32), nullable=True),
        sa.Column("audio_codec", sa.String(length=32), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("bitrate_kbps", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["render_jobs.id"],
                                name=op.f("fk_render_validations_job_id_render_jobs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_render_validations_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_validations")),
    )
    with op.batch_alter_table("render_validations") as batch:
        batch.create_index(batch.f("ix_render_validations_job_id"), ["job_id"])
        batch.create_index(batch.f("ix_render_validations_workspace_id"), ["workspace_id"])
        batch.create_index("ix_render_validation_job", ["job_id", "created_at"])

    op.create_table(
        "render_cost_logs",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.String(length=48), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("render_seconds", sa.Float(), nullable=False),
        sa.Column("frames", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["render_jobs.id"],
                                name=op.f("fk_render_cost_logs_job_id_render_jobs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_render_cost_logs_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_cost_logs")),
    )
    with op.batch_alter_table("render_cost_logs") as batch:
        batch.create_index(batch.f("ix_render_cost_logs_job_id"), ["job_id"])
        batch.create_index(batch.f("ix_render_cost_logs_workspace_id"), ["workspace_id"])

    # FFmpeg is no longer a video engine; retire the provider row without deleting its history.
    op.execute(
        "UPDATE ai_providers SET is_enabled = false, "
        "health_detail = 'FFmpeg composition retired — Remotion renders all videos' "
        "WHERE kind = 'video'"
    )


def downgrade() -> None:
    with op.batch_alter_table("render_cost_logs") as batch:
        batch.drop_index(batch.f("ix_render_cost_logs_workspace_id"))
        batch.drop_index(batch.f("ix_render_cost_logs_job_id"))
    op.drop_table("render_cost_logs")
    with op.batch_alter_table("render_validations") as batch:
        batch.drop_index("ix_render_validation_job")
        batch.drop_index(batch.f("ix_render_validations_workspace_id"))
        batch.drop_index(batch.f("ix_render_validations_job_id"))
    op.drop_table("render_validations")
    with op.batch_alter_table("render_jobs") as batch:
        batch.drop_index("ix_render_jobs_workspace_status")
        batch.drop_index("ix_render_jobs_project_created")
        batch.drop_index(batch.f("ix_render_jobs_workflow_id"))
        batch.drop_index(batch.f("ix_render_jobs_project_id"))
        batch.drop_index(batch.f("ix_render_jobs_workspace_id"))
    op.drop_table("render_jobs")
