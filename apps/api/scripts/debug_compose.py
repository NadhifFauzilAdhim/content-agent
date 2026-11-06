"""Isolate the final FFmpeg compose step (debug helper, not part of the app)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from app.adapters.video import _fontconfig_xml

work = Path(tempfile.mkdtemp(prefix="ff-step-"))
ass = work / "c.ass"
ass.write_text(
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
    "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Caption,Georgia,24,&H00FFFFFF,&H00FFFFFF,&H00111111,&H80111111,0,0,0,0,100,100,0,0,3,6,0,2,20,20,20,1\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:00.00,0:00:02.00,Caption,,0,0,0,,Hello there\n",
    encoding="utf-8",
)
conf = work / "fonts.conf"
conf.write_text(_fontconfig_xml(), encoding="utf-8")
video = work / "in.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=640x360:d=2", "-c:v", "libx264", str(video)],
    capture_output=True,
)
escaped = ass.resolve().as_posix().replace(":", "\\:")
out = work / "out.mp4"
cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", f"ass='{escaped}'", "-c:v", "libx264", str(out)]
env = {**__import__("os").environ, "FONTCONFIG_FILE": str(conf), "AV_LOG_FORCE_NOCOLOR": "1"}
r = subprocess.run(cmd, capture_output=True, text=True, env=env)
print("exit", r.returncode)
print("\n".join(r.stderr.splitlines()[-12:]))
print("out exists", out.exists(), out.stat().st_size if out.exists() else 0)
sys.exit(0 if r.returncode == 0 else 1)
