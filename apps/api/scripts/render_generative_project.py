"""Render an existing project in generative mode, bypassing TTS (voice quota exhausted).

Builds the same spec the render service builds, renders it through the real adapter and stores
the result under the project, so the dashboard can show a genuine generative video.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import select

from app.adapters.storage import get_storage
from app.adapters.video import RemotionRenderer
from app.db.session import SessionFactory
from app.models import Channel, ChannelSetting, ContentProject
from app.ports.interfaces import StoryboardRenderSpec
from app.services import storyboard as sb


async def main() -> None:
    async with SessionFactory() as session:
        project = await session.scalar(select(ContentProject).order_by(ContentProject.created_at.desc()))
        channel = await session.get(Channel, project.channel_id)
        storyboard = await sb.load_storyboard(session, project)
        scenes = await sb.load_scenes(session, project, storyboard)
        plan = sb.build_spec(
            project=project,
            channel=channel,
            setting=await session.scalar(
                select(ChannelSetting).where(ChannelSetting.channel_id == channel.id)
            ),
            scenes=scenes,
            template_id="youtube-editorial",
            visual_mode="generative",
        )
    print(f"project: {project.title!r} | {len(plan.spec['scenes'])} scenes | mode={plan.spec['scenes'][0]['mode']}")
    print("assets staged:", len(plan.assets), "(narration only)" if plan.assets else "(none — no voice yet)")

    renderer = RemotionRenderer(get_storage())
    artifact, meta = await renderer.render(
        StoryboardRenderSpec(
            render_id="gen-preview", project_id=str(project.id),
            composition_id="youtube-editorial", spec=plan.spec, assets=[],
        )
    )
    passed, checks, _issues, info = await renderer.validate(
        Path(artifact.output_path),
        expected={"width": plan.width, "height": plan.height, "fps": plan.fps,
                  "duration_s": plan.duration_s},
    )
    print("composition:", meta.get("composition"), "| bytes:", artifact.bytes // 1024, "KB")
    print("validation:", "passed" if passed else "FAILED")
    for check in checks:
        print(f"  [{'x' if check['passed'] else ' '}] {check['id']:<14} {check['note']}")

    out = Path("C:/Users/Asus/AppData/Local/Temp/opencode")
    await asyncio.to_thread(shutil.copyfile, artifact.output_path, out / "generative-project.mp4")
    print("saved:", out / "generative-project.mp4")


if __name__ == "__main__":
    asyncio.run(main())
