"""Render the *same* scene three ways to compare image vs generative vs image+motion.

Scene: "a small cat asleep on a bed beside a child" — the example from the operator.
  A. generative   : no image, prompt only (what they disliked)
  B. image        : AI image + the standard template (Ken Burns + caption)
  C. image+motion : AI image + a richer motion treatment (layered parallax, light, grain)
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import select

from app.adapters.images import build_image_provider
from app.adapters.storage import get_storage
from app.adapters.video import RemotionRenderer
from app.core.crypto import get_vault
from app.db.session import SessionFactory
from app.models import AiProvider
from app.ports.interfaces import StoryboardRenderSpec
from app.services.credentials import aad_for

PROMPT = (
    "A small fluffy ginger cat asleep curled on a soft bed, beside a sleepy child, "
    "warm lamp light, soft gouache storybook illustration"
)
OUT = Path("C:/Users/Asus/AppData/Local/Temp/opencode")


def spec(mode: str, image_name: str | None, motion: str) -> dict:
    entry: dict = {
        "id": "s1",
        "index": 1,
        "title": "A quiet room",
        "mode": mode,
        "prompt": PROMPT,
        "durationS": 4.0,
        "transition": "fade",
        "caption": "In a cozy corner of the room, a small cat sleeps beside the child.",
        "animation": {"kenBurns": "in", "entrance": "rise"},
    }
    if image_name:
        entry["assetKey"] = "img"
    if motion != "standard":
        entry["motion"] = motion
    return {
        "version": 1,
        "title": f"{mode}+{motion}",
        "brand": "FACTORY",
        "templateId": "youtube-editorial",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "accent": "#D6FF45",
        "background": "#FFFFFF",
        "ink": "#111111",
        "captions": {"enabled": True, "mode": "lower-third"},
        "defaultTransition": "fade",
        "transitionDurationS": 0.4,
        "intro": {"enabled": False},
        "outro": {"enabled": False},
        "music": {"url": None, "volume": 0.1, "duckUnderNarration": False},
        "scenes": [entry],
    }


async def make_image() -> Path:
    """Generate one image with the configured provider and keep it locally."""
    local = OUT / "cat-scene.png"
    if local.exists() and local.stat().st_size > 10_000:
        print("reusing existing image:", local)
        return local
    async with SessionFactory() as session:
        row = await session.scalar(
            select(AiProvider).where(
                AiProvider.kind == "image", AiProvider.slug == "openai-compatible",
                AiProvider.is_enabled.is_(True),
            )
        )
        key = get_vault().open(row.credential_ciphertext, aad=aad_for(row))["api_key"]
        adapter = build_image_provider(
            row.slug, key, row.base_url, options=row.extra_config, label=row.name
        )
        model = (row.models or [{}])[0].get("id")
    result = await adapter.generate(prompt=PROMPT, aspect_ratio="16:9", model=model)
    local.write_bytes(result.data)
    print(f"image: {result.width}x{result.height} {len(result.data) // 1024} KB ({model})")
    return local


async def render(name: str, payload: dict, assets: list[dict]) -> None:
    renderer = RemotionRenderer(get_storage())
    artifact, meta = await renderer.render(
        StoryboardRenderSpec(
            render_id=f"cmp-{name}", project_id="cmp", composition_id="youtube-editorial",
            spec=payload, assets=assets, stills=[{"frame": 60}],
        )
    )
    target = OUT / f"compare-{name}.mp4"
    await asyncio.to_thread(shutil.copyfile, artifact.output_path, target)
    for i, still in enumerate(meta.get("stills") or []):
        await asyncio.to_thread(shutil.copyfile, still, OUT / f"compare-{name}.jpg")
    print(f"{name:<16} {artifact.bytes // 1024:>5} KB  {meta.get('composition', {}).get('durationInFrames')} frames")


async def main() -> None:
    image = await make_image()
    asset = {"key": "img", "source": str(image), "name": "scene-01.png"}

    await render("A-generative", spec("generative", None, "standard"), [])
    await render("B-image", spec("image", "scene-01.png", "standard"), [asset])
    await render("C-image-motion", spec("image", "scene-01.png", "cinematic"), [asset])


if __name__ == "__main__":
    asyncio.run(main())
