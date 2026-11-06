"""Execute the stuck job through the real renderer, with progress printed as it happens."""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import RenderJob
from app.services.render import render_service


async def main() -> None:
    service = render_service()
    async with SessionFactory() as session:
        job = await session.scalar(select(RenderJob).order_by(RenderJob.created_at.desc()).limit(1))
        spec = await service._spec_for(session, job)

    last = 0.0
    started = time.perf_counter()

    async def progress(p) -> None:  # noqa: ANN001
        nonlocal last
        now = time.perf_counter()
        if now - last > 3:
            last = now
            print(f"  {p.stage:<10} {p.progress:.0%}  ({now - started:.0f}s)", flush=True)

    task = asyncio.create_task(service.renderer.render(spec, on_progress=progress))
    try:
        artifact, meta = await asyncio.wait_for(task, timeout=420)
        print("done:", artifact.bytes, "bytes in", round(time.perf_counter() - started), "s")
        print("composition:", meta.get("composition"))
    except TimeoutError:
        print("TIMEOUT at", round(time.perf_counter() - started), "s")


if __name__ == "__main__":
    asyncio.run(main())
