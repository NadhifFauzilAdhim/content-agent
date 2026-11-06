"""Inspect the render service's live state and rebuild a job's spec (the step before spawning node)."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import RenderJob
from app.services.render import render_service


async def main() -> None:
    service = render_service()
    print("workers:", [(t.done(), t.get_name()) for t in service._workers])
    print("known:", len(service._known), "| queued:", len(service._queued_ids))
    async with SessionFactory() as session:
        job = await session.scalar(select(RenderJob).order_by(RenderJob.created_at.desc()).limit(1))
        print("job:", job.id, job.status, job.stage)
        spec = await service._spec_for(session, job)
        if spec is None:
            print("_spec_for returned None")
        else:
            scenes = spec.spec.get("scenes") or []
            print(f"_spec_for ok: {len(spec.assets)} assets, {len(scenes)} scenes")
            print("first scene keys:", sorted(scenes[0].keys()) if scenes else "-")
            for asset in spec.assets[:3]:
                print("  asset:", asset.get("name"), "->", asset.get("source"))


if __name__ == "__main__":
    asyncio.run(main())
