"""Generate one scene through the real VisualGenerationAgent (container -> adapter -> storage)."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.agents.media import VisualRequest, VisualSceneRequest
from app.agents.registry import REGISTRY
from app.container import ProviderFactory
from app.db.session import SessionFactory
from app.models import Channel


async def main() -> None:
    async with SessionFactory() as session:
        channel = await session.scalar(select(Channel))
        ctx = await ProviderFactory(session).build_context(
            agent_key="visual_generation", workspace_id=channel.workspace_id, channel=channel
        )
        print("resolved model:", ctx.model)
        row = ctx.params.get("provider_row")
        if row is not None:
            print("provider:", row.name, "| slug:", row.slug, "| base:", row.base_url)
            print("options:", row.extra_config)

        spec = REGISTRY.get("visual_generation")
        result = await spec.agent().run(
            ctx,
            VisualRequest(
                aspect_ratio="16:9",
                scenes=[
                    VisualSceneRequest(
                        scene_id="probe-1",
                        index=1,
                        prompt=(
                            "A tiny green turtle with a red scarf walking a lantern-lit forest "
                            "path, soft gouache storybook illustration"
                        ),
                        negative_prompt="text, watermark, extra limbs",
                    )
                ],
            ),
        )
        scene = result.output.scenes[0]
        print(
            f"generated {scene.width}x{scene.height} {scene.bytes // 1024} KB "
            f"provider={scene.provider} model={scene.model}"
        )
        print("stored key:", scene.key)


if __name__ == "__main__":
    asyncio.run(main())
