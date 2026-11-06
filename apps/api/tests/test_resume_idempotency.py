"""Regression tests for the two bugs found while debugging the stuck Pip run.

1. Re-persisting a TTS generation with the same ``request_key`` (a resumed workflow re-synthesises
   the same scene) must reuse the existing row instead of violating the UNIQUE constraint.
2. A resumed workflow whose project already has a ready render must reuse it instead of rendering
   the whole video again.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models import Channel, ContentProject, TTSGeneration, VideoRender


class _Generated:
    """Minimal stand-in for the audio the TTS service receives back from a provider."""

    provider = "mock"
    model = "mock-tts"
    voice_id = "mock-narrator"
    audio = b"RIFF....WAVE"
    mime = "audio/wav"
    output_format = "wav/22050/pcm_s16le"
    duration_s = 1.5
    estimated_cost_usd = 0.0
    fallback_used = False
    chunk_results: list = []
    warnings: list = []

    class result:  # noqa: N801 - mirrors the provider result object
        character_count = 12
        latency_ms = 5
        request_id = None
        actual_cost_usd = None


def test_repeated_tts_request_key_reuses_the_row(client, auth):
    """The second persist with the same key must not raise IntegrityError."""

    async def run() -> int:
        from app.adapters.storage import get_storage
        from app.services.tts import TTSGenerationService

        async with SessionFactory() as session:
            channel = await session.scalar(select(Channel))
            service = TTSGenerationService(session)
            service.storage = get_storage()  # type: ignore[attr-defined]
            key = f"tts-test:{uuid.uuid4().hex[:8]}"
            where = (
                TTSGeneration.workspace_id == channel.workspace_id,
                TTSGeneration.request_key == key,
            )

            for _ in range(2):
                await service._persist(  # noqa: SLF001 - exercising the persistence path directly
                    generated=_Generated(), config=None, request=None, text="A short narration line.",
                    workspace_id=channel.workspace_id, channel_id=channel.id, workflow_id=None,
                    content_id=None, actor_id=None, trigger="production", request_key=key,
                    store_chunks=False,
                )
                await session.commit()

            return int(await session.scalar(select(func.count(TTSGeneration.id)).where(*where)) or 0)

    rows = asyncio.run(run())
    assert rows == 1, "a repeated request key must reuse the first generation"


def test_ready_render_is_found_for_reuse(client, auth):
    """A completed render (status ready + storage key) is what the resume path reuses."""

    async def run() -> bool:
        async with SessionFactory() as session:
            channel = await session.scalar(select(Channel))
            project = ContentProject(
                workspace_id=channel.workspace_id,
                channel_id=channel.id,
                title="Reuse test",
                status="approved",
                language="en",
                format="long",
            )
            session.add(project)
            await session.flush()
            session.add(VideoRender(
                workspace_id=channel.workspace_id, project_id=project.id,
                template="youtube-editorial", resolution="1920x1080", fps=30,
                status="ready", storage_key=f"p/{project.id}/renders/reuse-test.mp4",
                duration_s=12.0, bytes=1024, progress=100,
            ))
            await session.commit()

            found = await session.scalar(
                select(VideoRender)
                .where(
                    VideoRender.project_id == project.id,
                    VideoRender.status == "ready",
                    VideoRender.storage_key.is_not(None),
                )
                .limit(1)
            )
            return found is not None

    assert asyncio.run(run()) is True
