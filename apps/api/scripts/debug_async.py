"""Debug: run the renderer's async _run on the compose command and print full stderr tail."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from app.adapters.video import _error_excerpt, _run


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="ff-step2-"))
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
    conf.write_text("<?xml version='1.0'?><fontconfig><dir>C:/Windows/Fonts</dir></fontconfig>", encoding="utf-8")
    video = work / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=640x360:d=2", "-c:v", "libx264", str(video)],
        capture_output=True,
    )
    escaped = ass.resolve().as_posix().replace(":", "\\:")
    out = work / "out.mp4"
    code, err = await _run(
        ["ffmpeg", "-y", "-i", str(video), "-vf", f"ass='{escaped}'", "-c:v", "libx264", str(out)],
        env={"FONTCONFIG_FILE": str(conf)},
    )
    print("exit", code)
    print("LAST LINES:")
    print("\n".join(err.splitlines()[-8:]))
    print("excerpt:", _error_excerpt(err))
    print("out exists", out.exists())


asyncio.run(main())
