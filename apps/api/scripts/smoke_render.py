"""Ad-hoc smoke test for the Remotion engine (excluded from pytest collection).

Renders a tiny 3-scene composition straight through the adapter — no database, no workflow —
so the Node runtime, bundle, composition registration and output validation can be checked in
isolation.

    python scripts/smoke_render.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.adapters.storage import LocalStorage
from app.adapters.video import RemotionRenderer
from app.ports.interfaces import StoryboardRenderSpec

SPEC: dict = {
    "version": 1,
    "title": "Smoke test",
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
    "intro": {"enabled": False, "durationS": 0, "title": "Smoke test"},
    "outro": {"enabled": False, "durationS": 0, "headline": ""},
    "music": {"url": None, "volume": 0.1, "duckUnderNarration": True},
    "scenes": [
        {
            "id": f"s{i}",
            "index": i,
            "title": f"Scene {i}",
            "durationS": 2.0,
            "transition": "fade",
            "caption": f"Scene {i} of the smoke test renders correctly.",
        }
        for i in range(1, 4)
    ],
}


def main() -> int:
    # Windows consoles default to a legacy code page; keep output ASCII and UTF-8 safe.
    import sys

    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    return asyncio.run(_run())


async def _run() -> int:
    root = Path(tempfile.mkdtemp(prefix="remotion-smoke-"))
    renderer = RemotionRenderer(LocalStorage(root / "objects"))

    ok, detail = await renderer.health()
    print(f"engine: {'ok' if ok else 'unavailable'} — {detail}")
    if not ok:
        return 1

    async def progress(p) -> None:  # noqa: ANN001 - progress shape lives in the port
        if int(p.progress * 100) % 25 == 0:
            print(f"  {p.stage:<10} {p.progress:>5.0%}")

    spec = StoryboardRenderSpec(
        render_id="smoke",
        project_id="smoke",
        composition_id="youtube-editorial",
        spec=SPEC,
        assets=[],
    )
    artifact, meta = await renderer.render(spec, on_progress=progress)
    print(f"rendered {artifact.bytes // 1024} KB in {artifact.elapsed_s:.1f}s -> {artifact.output_path}")
    print("composition:", json.dumps(meta.get("composition"), default=str))

    passed, checks, issues, info = await renderer.validate(
        Path(artifact.output_path), expected={"width": 1280, "height": 720, "fps": 30}
    )
    for check in checks:
        print(f"  [{'x' if check['passed'] else ' '}] {check['id']:<14} {check['note']}")
    print("validation:", "passed" if passed else f"failed - {'; '.join(issues)}")
    print("media:", json.dumps(info))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
