"""Reset production data, keeping provider settings and the channel definition.

Removes: content ideas, projects, workflows (tasks/logs), approvals, QC reports, publishing jobs,
scripts/storyboards/scenes, media/audio assets, renders, render jobs, TTS generations, AI usage
logs and audit rows. Also prunes orphaned files from local storage.

Keeps: providers (credentials intact), the channel, its schedule, agents and workspace settings.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select, update

from app.core.settings import get_settings
from app.db.session import SessionFactory
from app.models import (
    AiUsageLog,
    ApprovalRequest,
    AudioAsset,
    AuditLog,
    Channel,
    ContentIdea,
    ContentProject,
    MediaAsset,
    ProductionWorkflow,
    PublishingJob,
    QualityReport,
    RenderCostLog,
    RenderJob,
    RenderValidation,
    Scene,
    Schedule,
    Script,
    Storyboard,
    TTSGeneration,
    TTSPreviewCache,
    TTSUsageLog,
    VideoRender,
    WorkflowLog,
    WorkflowTask,
)

# Ordered children-first so foreign keys never block the delete.
ORDER = [
    RenderValidation,
    RenderCostLog,
    RenderJob,
    TTSGeneration,
    TTSUsageLog,
    TTSPreviewCache,
    WorkflowLog,
    WorkflowTask,
    ApprovalRequest,
    QualityReport,
    PublishingJob,
    AiUsageLog,
    AudioAsset,
    MediaAsset,
    VideoRender,
    Scene,
    Storyboard,
    Script,
    ProductionWorkflow,
    ContentProject,
    ContentIdea,
]


async def main() -> None:
    async with SessionFactory() as session:
        before = {}
        for model in ORDER:
            before[model.__name__] = await session.scalar(select(func.count()).select_from(model))

        # Projects reference ideas and channels by FK; clear pointers first.
        await session.execute(update(ContentProject).values(idea_id=None, thumbnail_asset_id=None))
        await session.flush()

        for model in ORDER:
            await session.execute(delete(model))
        await session.flush()

        # Audit rows are history of the deleted work; keep auth/provider entries.
        deleted_audit = await session.execute(
            delete(AuditLog).where(
                AuditLog.action.not_in(
                    [
                        "auth.login",
                        "auth.login_failed",
                        "auth.logout",
                        "provider.created",
                        "provider.deleted",
                        "provider.credentials.created",
                        "provider.credentials.updated",
                        "provider.credentials.rotated",
                        "provider.credentials.removed",
                        "provider.models.synced",
                    ]
                )
            )
        )
        await session.commit()

        print(f"{'table':24} removed")
        for name, count in before.items():
            if count:
                print(f"{name:24} {count}")
        print(f"{'AuditLog (work only)':24} {deleted_audit.rowcount}")

        # Report what survives.
        from app.models import AiProvider

        providers = await session.scalar(select(func.count()).select_from(AiProvider))
        channels = (await session.execute(select(Channel))).scalars().all()
        schedules = (await session.execute(select(Schedule))).scalars().all()
        print(f"\nkept: {providers} providers, {len(channels)} channel(s), {len(schedules)} schedule(s)")

    # Local storage: prune project media that no row references any more.
    root = Path(get_settings().storage_root)
    projects_dir = root / "p"
    if projects_dir.exists():
        async with SessionFactory() as session:
            live = {
                str(v)
                for v in (
                    await session.execute(select(ContentProject.id))
                ).scalars()
            }
        for directory in projects_dir.iterdir():
            if directory.is_dir() and directory.name not in live:
                shutil.rmtree(directory, ignore_errors=True)
        remaining = sum(1 for _ in root.rglob("*") if _.is_file())
        print(f"storage: {remaining} file(s) remain under {root}")


if __name__ == "__main__":
    asyncio.run(main())
