"""channel visual mode (image vs generative)

Adds ``channels.visual_mode``: ``image`` generates one image per scene with the image provider;
``generative`` skips image generation and lets Remotion compose each scene from its visual prompt.

Revision ID: 7d31b5c8a204
Revises: c4f9a2d13e57
Create Date: 2026-11-06 17:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d31b5c8a204"
down_revision: str | None = "c4f9a2d13e57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("channels") as batch:
        batch.add_column(
            sa.Column(
                "visual_mode",
                sa.String(length=16),
                nullable=False,
                server_default="image",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("channels") as batch:
        batch.drop_column("visual_mode")
