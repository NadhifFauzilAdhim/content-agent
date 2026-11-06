"""Diagnose the render worker stuck at 'bundling' with no node child.

Checks, in order:
  1. the API process's event loop is responsive (a hung loop explains "stuck with no progress")
  2. what session the worker sees for the stuck job
  3. whether the job even reaches the renderer, by replaying it in THIS process
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import RenderJob
from app.services.render import render_service


async def main() -> None:
    service = render_service()
    print("workers:", [(t.done()) for t in service._workers], "| semaphore locked:", service._semaphore.locked())

    async with SessionFactory() as session:
        job = await session.scalar(
            select(RenderJob).where(RenderJob.status == "bundling").order_by(
                RenderJob.created_at.desc()
            ).limit(1)
        )
        if job is None:
            print("no job in bundling")
            return
        print("job:", job.id, "| progress", job.progress, "| attempt", job.attempts)

        started = time.perf_counter()
        spec = await asyncio.wait_for(service._spec_for(session, job), timeout=60)
        print(f"_spec_for took {time.perf_counter() - started:.1f}s ->",
              "None" if spec is None else f"{len(spec.assets)} assets, {len(spec.spec['scenes'])} scenes")

    # Now attempt the actual render in this process, with progress visible.
    async def progress(p) -> None:  # noqa: ANN001
        print(f"   {p.stage} {p.progress:.0%} @ {time.perf_counter() - started:.0f}s", flush=True)

    task = asyncio.create_task(service.renderer.render(spec, on_progress=progress))
    try:
        artifact, meta = await asyncio.wait_for(task, timeout=300)
        print("RENDER OK:", artifact.bytes // 1024, "KB", meta.get("composition"))
    except TimeoutError:
        print("RENDER TIMEOUT after 300s (this is the hang)")


if __name__ == "__main__":
    asyncio.run(main())
