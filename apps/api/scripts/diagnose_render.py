"""Run the render adapter directly and report every stage, with a hard timeout."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from app.adapters.storage import LocalStorage
from app.adapters.video import engine_health, remotion_dir
from app.ports.interfaces import StoryboardRenderSpec


async def main() -> None:
    print("engine dir:", remotion_dir())
    print("health:", engine_health())
    renderer = __import__("app.adapters.video", fromlist=["RemotionRenderer"]).RemotionRenderer(
        LocalStorage(Path(tempfile.mkdtemp()))
    )
    spec = StoryboardRenderSpec(
        render_id="diag",
        project_id="diag",
        composition_id="youtube-editorial",
        spec={
            "version": 1, "title": "Diag", "brand": "FACTORY", "templateId": "youtube-editorial",
            "width": 640, "height": 360, "fps": 15, "accent": "#D6FF45",
            "background": "#FFFFFF", "ink": "#111111",
            "captions": {"enabled": False, "mode": "lower-third"},
            "defaultTransition": "cut", "transitionDurationS": 0.2,
            "intro": {"enabled": False}, "outro": {"enabled": False},
            "scenes": [{"id": "s1", "index": 1, "title": "One", "mode": "generative",
                        "prompt": "a fox in a forest", "durationS": 1.5, "transition": "cut",
                        "caption": None}],
            "music": {"url": None, "volume": 0.1, "duckUnderNarration": False},
        },
    )

    async def progress(p) -> None:  # noqa: ANN001
        print(f"  progress {p.stage} {p.progress:.2f}")

    started = time.perf_counter()
    try:
        artifact, meta = await asyncio.wait_for(
            renderer.render(spec, on_progress=progress), timeout=240
        )
        print("done in", round(time.perf_counter() - started), "s", artifact.bytes, "bytes")
        print("composition:", json.dumps(meta.get("composition")))
    except TimeoutError:
        print("TIMEOUT after", round(time.perf_counter() - started), "s")


if __name__ == "__main__":
    asyncio.run(main())
