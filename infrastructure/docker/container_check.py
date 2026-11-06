"""Container check: render one 2-scene composition with the engine baked into the image."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from app.adapters.storage import LocalStorage
from app.adapters.video import RemotionRenderer
from app.ports.interfaces import StoryboardRenderSpec


async def run() -> int:
    root = Path(tempfile.mkdtemp(prefix="docker-smoke-"))
    renderer = RemotionRenderer(LocalStorage(root / "objects"))
    ok, detail = await renderer.health()
    print(f"engine: {'ok' if ok else 'FAILED'} - {detail}")
    if not ok:
        return 1

    spec = StoryboardRenderSpec(
        render_id="docker",
        project_id="docker",
        composition_id="youtube-editorial",
        spec={
            "version": 1, "title": "Container check", "brand": "FACTORY",
            "templateId": "youtube-editorial", "width": 960, "height": 540, "fps": 30,
            "accent": "#D6FF45", "background": "#FFFFFF", "ink": "#111111",
            "captions": {"enabled": True, "mode": "lower-third"},
            "defaultTransition": "fade", "transitionDurationS": 0.4,
            "intro": {"enabled": False, "durationS": 0, "title": "Container check"},
            "outro": {"enabled": False, "durationS": 0, "headline": ""},
            "music": {"url": None, "volume": 0.1, "duckUnderNarration": True},
            "scenes": [
                {"id": "s1", "index": 1, "title": "One", "durationS": 1.5,
                 "transition": "fade", "caption": "Rendering works inside the container."},
                {"id": "s2", "index": 2, "title": "Two", "durationS": 1.5,
                 "transition": "fade", "caption": "Captions, audio and encode included."},
            ],
        },
        assets=[],
    )
    artifact, meta = await renderer.render(spec)
    print("composition:", json.dumps(meta.get("composition")))
    print(f"output: {artifact.bytes // 1024} KB in {artifact.elapsed_s:.1f}s")

    passed, checks, issues, info = await renderer.validate(
        Path(artifact.output_path), expected={"width": 960, "height": 540, "fps": 30}
    )
    for check in checks:
        print(f"  [{'x' if check['passed'] else ' '}] {check['id']:<14} {check['note']}")
    print("validation:", "passed" if passed else f"FAILED - {'; '.join(issues)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
