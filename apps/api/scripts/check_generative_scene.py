"""Render two scenes in generative mode (no image provider, no image assets)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from app.adapters.storage import LocalStorage
from app.adapters.video import RemotionRenderer
from app.ports.interfaces import StoryboardRenderSpec
from app.services.storyboard import actual_duration


def spec(mode: str) -> dict:
    scenes = [
        {
            "id": f"s{i}",
            "index": i,
            "title": title,
            "mode": mode,
            "prompt": prompt,
            "durationS": 3.0,
            "transition": "fade",
            "caption": caption,
        }
        for i, (title, prompt, caption) in enumerate(
            [
                (
                    "The lantern path",
                    "A tiny fox cub with a red scarf walking a lantern-lit forest path at dusk",
                    "The little lantern glows softly on the path.",
                ),
                (
                    "Puddle the raindrop",
                    "A small raindrop resting on a wide green leaf while a snail smiles nearby",
                    "Puddle landed on a leaf and met Dew the snail.",
                ),
            ],
            start=1,
        )
    ]
    return {
        "version": 1,
        "title": f"Generative test ({mode})",
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
        "transitionDurationS": 0.5,
        "intro": {"enabled": False, "durationS": 0, "title": "t"},
        "outro": {"enabled": False, "durationS": 0, "headline": ""},
        "music": {"url": None, "volume": 0.1, "duckUnderNarration": True},
        "scenes": scenes,
    }


async def render(mode: str) -> Path:
    renderer = RemotionRenderer(LocalStorage(Path("storage")))
    payload = spec(mode)
    artifact, meta = await renderer.render(
        StoryboardRenderSpec(
            render_id=f"gen-{mode}",
            project_id="gen",
            composition_id="youtube-editorial",
            spec=payload,
            stills=[{"frame": 45}, {"frame": 120}],
        )
    )
    print(mode, "->", artifact.bytes // 1024, "KB", json.dumps(meta.get("composition")))

    passed, checks, issues, info = await renderer.validate(
        Path(artifact.output_path), expected={"width": 1280, "height": 720, "fps": 30,
                                              "duration_s": actual_duration(payload)}
    )
    print("  validation:", "passed" if passed else issues)
    for check in checks:
        print(f"   [{'x' if check['passed'] else ' '}] {check['id']:<14} {check['note']}")

    # Keep a copy of the video and two stills for visual inspection.
    out_dir = Path("C:/Users/Asus/AppData/Local/Temp/opencode")
    target = out_dir / f"generative-{mode}.mp4"
    await asyncio.to_thread(shutil.copyfile, artifact.output_path, target)
    for i, still in enumerate(meta.get("stills") or []):
        await asyncio.to_thread(shutil.copyfile, still, out_dir / f"gen-{mode}-{i}.jpg")
    return target


async def main() -> None:
    for mode in ("generative", "asset"):
        await render(mode)


if __name__ == "__main__":
    asyncio.run(main())
