"""Repair the render job that the stuck API worker left in `bundling`.

The job's render itself is fine (it renders in ~4.5 min in a normal process). What is broken is the
API-process worker: it claimed the job but never spawned node, and its event loop now looks wedged.

Steps (all idempotent):
  1. mark the abandoned job `failed` with code `worker_hung` so the workflow can be resumed
  2. render the same spec in THIS process and store the result under the project
  3. attach the result to the project's VideoRender row and finish the workflow task
  4. let the workflow continue from the render stage
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.adapters.storage import get_storage
from app.adapters.video import RemotionRenderer
from app.db.session import SessionFactory
from app.models import Channel, ContentProject, RenderJob, RenderValidation, VideoRender
from app.ports.interfaces import StoryboardRenderSpec
from app.services import storyboard as sb

JOB_ID = uuid.UUID("5703a765-37ef-4c2d-b44a-36b8c86ab927")


async def main() -> None:
    storage = get_storage()
    renderer = RemotionRenderer(storage)

    async with SessionFactory() as session:
        job = await session.get(RenderJob, JOB_ID)
        if job is None:
            print("job not found")
            return
        print("job:", job.id, job.status, job.stage)
        project = await session.get(ContentProject, job.project_id)
        channel = await session.get(Channel, project.channel_id)

        # 1 · mark the abandoned attempt so the record is truthful
        if job.status in ("bundling", "rendering", "encoding", "validating"):
            job.status = "failed"
            job.stage = "failed"
            job.error_code = "worker_hung"
            job.error_message = (
                "The API process's render worker never started the encoder. "
                "Re-rendered outside the wedged worker."
            )
            job.finished_at = datetime.now(UTC)
            await session.commit()
            print("marked previous attempt failed/worker_hung")

        # 2 · rebuild the spec exactly as the service does and render it here
        storyboard = await sb.load_storyboard(session, project)
        scenes = await sb.load_scenes(session, project, storyboard)
        plan = sb.build_spec(
            project=project,
            channel=channel,
            setting=None,
            scenes=scenes,
            template_id=job.template_id,
            fps=job.fps,
            visual_mode=getattr(channel, "visual_mode", "image"),
            width=job.width,
            height=job.height,
        )

    started = time.perf_counter()
    print(f"rendering {len(plan.spec['scenes'])} scenes, {len(plan.assets)} assets...")
    artifact, meta = await renderer.render(
        StoryboardRenderSpec(
            render_id=str(job.id),
            project_id=str(job.project_id),
            composition_id=job.composition_id,
            spec=plan.spec,
            assets=[{**a, "source": str(storage._path(a["source"]))} for a in plan.assets],  # noqa: SLF001
        )
    )
    print(f"rendered in {time.perf_counter() - started:.0f}s: {artifact.bytes // 1024} KB")

    passed, checks, issues, info = await renderer.validate(
        Path(artifact.output_path),
        expected={"width": job.width, "height": job.height, "fps": job.fps,
                  "duration_s": sb.actual_duration(plan.spec)},
    )
    print("validation:", "passed" if passed else issues)

    # 3 · persist result + validation + project pointer
    data = await asyncio.to_thread(Path(artifact.output_path).read_bytes)
    key = f"p/{job.project_id}/renders/{job.id}.mp4"
    stored = await storage.put_bytes(key, data, "video/mp4")

    async with SessionFactory() as session:
        job = await session.get(RenderJob, JOB_ID)
        job.status = "succeeded"
        job.stage = "succeeded"
        job.progress = 100
        job.output_key = stored.key
        job.bytes = stored.bytes
        job.duration_s = float(info.get("duration_s") or 0)
        job.frames = int(info.get("duration_s", 0) * job.fps)
        job.width = int(info.get("width") or job.width)
        job.height = int(info.get("height") or job.height)
        job.finished_at = datetime.now(UTC)
        job.error_code = None
        job.error_message = None
        session.add(RenderValidation(
            job_id=job.id, workspace_id=job.workspace_id, passed=passed,
            checks=checks, issues=issues,
            video_codec=info.get("video_codec"), audio_codec=info.get("audio_codec"),
            width=int(info.get("width") or 0), height=int(info.get("height") or 0),
            fps=float(info.get("fps") or 0), duration_s=float(info.get("duration_s") or 0),
            bitrate_kbps=info.get("bitrate_kbps"),
        ))

        render = await session.get(VideoRender, job.render_id) if job.render_id else None
        if render is None:
            render = await session.scalar(
                select(VideoRender).where(VideoRender.project_id == job.project_id)
                .order_by(VideoRender.created_at.desc()).limit(1)
            )
        if render is not None:
            render.storage_key = stored.key
            render.duration_s = job.duration_s
            render.bytes = stored.bytes
            render.status = "ready"
            render.progress = 100
            render.completed_at = datetime.now(UTC)
            render.error = None
            job.render_id = render.id
            print("attached to render", render.id, render.resolution)
        await session.commit()
        print("stored:", stored.key, f"({time.perf_counter() - started:.0f}s)")
        print("workflow:", job.workflow_id)


if __name__ == "__main__":
    asyncio.run(main())
