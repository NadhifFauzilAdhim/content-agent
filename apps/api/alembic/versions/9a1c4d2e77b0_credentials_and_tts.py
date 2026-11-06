"""credentials, tts configuration, generation and usage

Adds:
* provider credential metadata (version, status, rotation timestamp)
* ``tts_configurations`` (workspace default provider/voice and fallback)
* channel voice overrides (``voice_model``, ``voice_config``)
* richer ``audio_assets`` metadata (model, settings, output format)
* ``tts_generations``, ``tts_usage_logs``, ``tts_preview_cache``

Existing secrets are untouched: the column stays the same and the vault now seals with
AES-256-GCM. Legacy Fernet blobs are re-sealed on first read.

Revision ID: 9a1c4d2e77b0
Revises: 33855a02808b
Create Date: 2026-11-06 01:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a1c4d2e77b0"
down_revision: str | None = "33855a02808b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- provider credentials -------------------------------------------
    with op.batch_alter_table("ai_providers") as batch:
        batch.add_column(sa.Column("credential_version", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("credential_status", sa.String(length=16), nullable=False,
                                   server_default="unset"))
        batch.add_column(sa.Column("credential_updated_at", sa.DateTime(timezone=True),
                                   nullable=True))

    # --- workspace TTS configuration ------------------------------------
    op.create_table(
        "tts_configurations",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider_slug", sa.String(length=64), nullable=False),
        sa.Column("fallback_provider_slug", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("voice_id", sa.String(length=160), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("output_format", sa.String(length=32), nullable=True),
        sa.Column("voice_settings", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_tts_configurations_workspace_id_workspaces"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"],
                                name=op.f("fk_tts_configurations_updated_by_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tts_configurations")),
        sa.UniqueConstraint("workspace_id", name="uq_tts_config_workspace"),
    )
    with op.batch_alter_table("tts_configurations") as batch:
        batch.create_index(batch.f("ix_tts_configurations_workspace_id"), ["workspace_id"])
        batch.create_index("ix_tts_config_provider", ["provider_slug"])

    # --- channel voice override -----------------------------------------
    with op.batch_alter_table("channel_settings") as batch:
        batch.add_column(sa.Column("voice_model", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("voice_config", sa.JSON(), nullable=False,
                                   server_default="{}"))
        batch.alter_column("voice_id", type_=sa.String(length=160), existing_type=sa.String(length=120),
                           existing_nullable=True)

    # --- audio assets ----------------------------------------------------
    with op.batch_alter_table("audio_assets") as batch:
        batch.add_column(sa.Column("model_id", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("voice_settings", sa.JSON(), nullable=False,
                                   server_default="{}"))
        batch.add_column(sa.Column("output_format", sa.String(length=32), nullable=True))
        batch.alter_column("voice_id", type_=sa.String(length=160), existing_type=sa.String(length=120),
                           existing_nullable=True)

    # --- generations -----------------------------------------------------
    op.create_table(
        "tts_generations",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("voice_id", sa.String(length=160), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("audio_path", sa.String(length=500), nullable=True),
        sa.Column("audio_format", sa.String(length=32), nullable=True),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("audio_duration", sa.Float(), nullable=False),
        sa.Column("generation_latency", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("actual_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=120), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_from", sa.String(length=64), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("chunk_manifest", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("request_key", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')",
                           name=op.f("ck_tts_generations_status_valid")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_tts_generations_workspace_id_workspaces"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["production_workflows.id"],
                                name=op.f("fk_tts_generations_workflow_id_production_workflows"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"],
                                name=op.f("fk_tts_generations_channel_id_channels"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["content_id"], ["content_projects.id"],
                                name=op.f("fk_tts_generations_content_id_content_projects"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                name=op.f("fk_tts_generations_created_by_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tts_generations")),
        sa.UniqueConstraint("request_key", name="uq_tts_generation_request_key"),
    )
    with op.batch_alter_table("tts_generations") as batch:
        batch.create_index(batch.f("ix_tts_generations_workspace_id"), ["workspace_id"])
        batch.create_index("ix_tts_gen_workspace_created", ["workspace_id", "created_at"])
        batch.create_index("ix_tts_gen_provider_created", ["provider", "created_at"])
        batch.create_index("ix_tts_gen_status", ["status"])
        batch.create_index("ix_tts_generations_workflow_id", ["workflow_id"])
        batch.create_index("ix_tts_generations_channel_id", ["channel_id"])
        batch.create_index("ix_tts_generations_content_id", ["content_id"])

    # --- usage ledger ----------------------------------------------------
    op.create_table(
        "tts_usage_logs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("usage_quantity", sa.Float(), nullable=False),
        sa.Column("usage_unit", sa.String(length=24), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("actual_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name=op.f("fk_tts_usage_logs_workspace_id_workspaces"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_id"], ["tts_generations.id"],
                                name=op.f("fk_tts_usage_logs_generation_id_tts_generations"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"],
                                name=op.f("fk_tts_usage_logs_channel_id_channels"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["production_workflows.id"],
                                name=op.f("fk_tts_usage_logs_workflow_id_production_workflows"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["content_id"], ["content_projects.id"],
                                name=op.f("fk_tts_usage_logs_content_id_content_projects"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tts_usage_logs")),
    )
    with op.batch_alter_table("tts_usage_logs") as batch:
        batch.create_index(batch.f("ix_tts_usage_logs_workspace_id"), ["workspace_id"])
        batch.create_index("ix_tts_usage_workspace_created", ["workspace_id", "created_at"])
        batch.create_index("ix_tts_usage_provider_created", ["provider", "created_at"])

    # --- voice preview cache --------------------------------------------
    op.create_table(
        "tts_preview_cache",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("voice_id", sa.String(length=160), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("mime", sa.String(length=80), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tts_preview_cache")),
        sa.UniqueConstraint("provider", "voice_id", name="uq_tts_preview"),
    )

    # --- backfill credential status -------------------------------------
    op.execute(
        "UPDATE ai_providers SET credential_status = 'unset' WHERE credential_ciphertext IS NULL"
    )
    op.execute(
        "UPDATE ai_providers SET credential_status = 'active', credential_version = 1 "
        "WHERE credential_ciphertext IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("tts_preview_cache")
    with op.batch_alter_table("tts_usage_logs") as batch:
        batch.drop_index("ix_tts_usage_provider_created")
        batch.drop_index("ix_tts_usage_workspace_created")
        batch.drop_index(batch.f("ix_tts_usage_logs_workspace_id"))
    op.drop_table("tts_usage_logs")
    with op.batch_alter_table("tts_generations") as batch:
        for name in (
            "ix_tts_generations_content_id",
            "ix_tts_generations_channel_id",
            "ix_tts_generations_workflow_id",
            "ix_tts_gen_status",
            "ix_tts_gen_provider_created",
            "ix_tts_gen_workspace_created",
            batch.f("ix_tts_generations_workspace_id"),
        ):
            batch.drop_index(name)
    op.drop_table("tts_generations")
    with op.batch_alter_table("audio_assets") as batch:
        batch.alter_column("voice_id", type_=sa.String(length=120), existing_type=sa.String(length=160),
                           existing_nullable=True)
        batch.drop_column("output_format")
        batch.drop_column("voice_settings")
        batch.drop_column("model_id")
    with op.batch_alter_table("channel_settings") as batch:
        batch.alter_column("voice_id", type_=sa.String(length=120), existing_type=sa.String(length=160),
                           existing_nullable=True)
        batch.drop_column("voice_config")
        batch.drop_column("voice_model")
    with op.batch_alter_table("tts_configurations") as batch:
        batch.drop_index("ix_tts_config_provider")
        batch.drop_index(batch.f("ix_tts_configurations_workspace_id"))
    op.drop_table("tts_configurations")
    with op.batch_alter_table("ai_providers") as batch:
        batch.drop_column("credential_updated_at")
        batch.drop_column("credential_status")
        batch.drop_column("credential_version")
