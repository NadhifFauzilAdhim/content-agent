"""Ad-hoc smoke test for the FFmpeg renderer (excluded from pytest collection)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.adapters.images import MockImage
from app.adapters.storage import LocalStorage
from app.adapters.tts import MockTTS
from app.adapters.video import FFmpegRenderer
from app.ports.interfaces import RenderSpec, SceneClip


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="ff-smoke-"))
    storage = LocalStorage(root / "objects")
    image = MockImage()
    tts = MockTTS()
    clips = []
    for i, text in enumerate(
        [
            "Once upon a time a small fox found a shiny acorn in the meadow.",
            "The fox carried it home, remembering every turn of the path.",
            "That night the acorn grew into a tiny tree of light.",
            "The end, sleep well little friend.",
        ],
        start=1,
    ):
        img = await image.generate(prompt=f"Scene {i}: a small fox in a meadow")
        ik = await storage.put_bytes(f"p/demo/images/{i}.png", img.data, img.mime)
        audio = await tts.synthesize(text=text, voice_id="mock-narrator")
        ak = await storage.put_bytes(f"p/demo/audio/{i}.wav", audio.audio, audio.mime)
        clips.append(SceneClip(f"s{i}", i, ik.key, ak.key, float(audio.duration_s), text))
    renderer = FFmpegRenderer(storage=storage)
    out = await renderer.render(
        RenderSpec(render_id="smoke", project_id="demo", title="Smoke", clips=clips,
                   width=1280, height=720)
    )
    print(out)
    print(renderer.health and await renderer.health())


if __name__ == "__main__":
    asyncio.run(main())
