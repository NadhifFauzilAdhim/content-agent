"""Profile render stages to find slow steps (debug helper)."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path


def run(args: list[str]) -> float:
    t = time.perf_counter()
    r = subprocess.run(args, capture_output=True, text=True)
    dt = time.perf_counter() - t
    print(f"{dt:7.2f}s exit={r.returncode} {' '.join(args[:9])}")
    return dt


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="ff-prof-"))
    img = work / "i.png"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=orange:s=1792x1024:d=1", "-frames:v", "1", str(img)])
    audio = work / "a.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=220:d=4", str(audio)])
    w, h, fps = 1920, 1080, 30
    d = 4.3
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='min(zoom+0.0006,1.08)':d={int(round(d*fps))}:s={w}x{h}:fps={fps},format=yuv420p"
    )
    run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", str(img), "-i", str(audio),
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-shortest", str(work / "seg1.mp4")])
    vf2 = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"zoompan=z='min(zoom+0.0006,1.08)':d={int(round(d*fps))}:s={w}x{h}:fps={fps},format=yuv420p"
    )
    run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", str(img), "-i", str(audio), "-vf", vf2,
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-c:a", "aac", str(work / "seg2.mp4")])


asyncio.run(main())
