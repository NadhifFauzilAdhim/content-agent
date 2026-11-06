"""Profile alternative zoompan pipelines (debug helper)."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path


def run(label: str, args: list[str]) -> None:
    t = time.perf_counter()
    r = subprocess.run(args, capture_output=True, text=True)
    print(f"{time.perf_counter() - t:7.2f}s exit={r.returncode} {label}")
    if r.returncode:
        print(r.stderr[-600:])


work = Path(tempfile.mkdtemp(prefix="ff-prof2-"))
img = work / "i.png"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=orange:s=1792x1024:d=1", "-frames:v", "1", str(img)], capture_output=True)
w, h, fps, d = 1920, 1080, 30, 4.3
frames = int(round(d * fps))

variants = {
    "A z=dframes scale-first": (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},"
        f"zoompan=z='min(zoom+{0.08/frames:.6f},1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},format=yuv420p"
    ),
    "B z=d1": (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
        f"zoompan=z='min(zoom+{0.08/frames:.6f},1.08)':d=1:s={w}x{h}:fps={fps},format=yuv420p"
    ),
    "C no zoompan": (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},format=yuv420p"
    ),
}
for label, vf in variants.items():
    run(label, ["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", str(img), "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(work / f"{label[0]}.mp4")])
