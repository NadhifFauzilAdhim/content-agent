"""Cheap, read-only media inspection with ffprobe.

Used for narration chunks (duration), TTS validation and render output inspection. Native
inspection via FFmpeg/ffprobe is *not* used for composition, transitions, subtitles or mixing —
those are produced by Remotion; ffprobe only reads metadata from finished files.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger("factory.media.probe")


def ffmpeg_available() -> bool:
    return shutil.which(get_settings().ffmpeg_path) is not None


def ffprobe_available() -> bool:
    return shutil.which(get_settings().ffprobe_path) is not None


def probe_audio_bytes(data: bytes) -> float:
    """Duration in seconds. WAV is parsed natively; other formats shell out to ffprobe."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                return round(wav.getnframes() / float(wav.getframerate()), 2)
        except wave.Error:
            pass
    if not ffprobe_available():
        logger.warning("ffprobe missing; duration unknown")
        return 0.0
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        return probe_duration(path)
    finally:
        Path(path).unlink(missing_ok=True)


def probe_duration(path: str) -> float:
    probe = get_settings().ffprobe_path
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return round(float(json.loads(out.stdout)["format"]["duration"]), 2)
    except Exception:  # noqa: BLE001
        return 0.0


async def probe_duration_async(path: str) -> float:
    return await asyncio.to_thread(probe_duration, path)


def audio_health() -> tuple[bool, str]:
    if ffmpeg_available() and ffprobe_available():
        return True, "FFmpeg + ffprobe detected"
    return False, "FFmpeg not found on PATH — rendering is unavailable"
