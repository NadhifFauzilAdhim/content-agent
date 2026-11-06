"""Audio validation and assembly with FFmpeg.

Long-form narration is generated in sentence-aligned chunks. Chunks are concatenated with short,
level-matched gaps and a light loudness pass so joins do not click or jump, then validated with
ffprobe before they are allowed into the video stage.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from app.adapters.media import probe_duration
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.ports.tts import TTSContentError

log = get_logger("factory.tts.audio")

MIME_BY_EXT = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "pcm": "audio/L16",
    "m4a": "audio/mp4",
}


def sniff_format(data: bytes) -> str | None:
    """Guess the container from the first bytes; catches truncated or HTML error bodies."""
    if len(data) < 16:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if data[4:8] == b"ftyp":
        return "m4a"
    return None


def validate_audio(data: bytes, *, mime: str, provider: str, min_bytes: int = 1024) -> None:
    if not data or len(data) < min_bytes:
        raise TTSContentError(
            f"{provider}: generated audio is empty or truncated ({len(data)} bytes)"
        )
    looks_pcm = mime in ("audio/L16", "audio/pcm") or mime == "application/octet-stream"
    if not looks_pcm and sniff_format(data) is None:
        raise TTSContentError(
            f"{provider}: generated audio is not a recognised WAV/MP3/Opus file"
        )


def validate_wav(data: bytes, *, provider: str) -> None:
    """Strict check used before handing narration to the video stage."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise TTSContentError(f"{provider}: narration is not a valid WAV file")
    import io

    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getnframes() <= 0:
                raise TTSContentError(f"{provider}: narration has no audio frames")
    except wave.Error as exc:
        raise TTSContentError(f"{provider}: narration WAV is unreadable ({exc})") from exc


def wav_bytes(pcm: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


@dataclass(slots=True)
class AudioProbe:
    duration_s: float
    sample_rate: int
    channels: int
    bytes: int


def _ffmpeg_bin() -> str | None:
    return shutil.which(get_settings().ffmpeg_path)


def probe(data: bytes) -> AudioProbe | None:
    if not _ffmpeg_bin():
        return None
    with tempfile.TemporaryDirectory(prefix="tts-probe-") as tmp:
        path = Path(tmp) / "audio.bin"
        path.write_bytes(data)
        return probe_file(path)


def probe_file(path: Path) -> AudioProbe | None:
    import json
    import subprocess

    probe_bin = shutil.which(get_settings().ffprobe_path)
    if not probe_bin:
        return None
    try:
        out = subprocess.run(
            [probe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        payload = json.loads(out.stdout or "{}")
        stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), {})
        duration = float(payload.get("format", {}).get("duration") or 0)
        return AudioProbe(
            duration_s=round(duration, 2),
            sample_rate=int(stream.get("sample_rate") or 0),
            channels=int(stream.get("channels") or 0),
            bytes=path.stat().st_size,
        )
    except Exception:  # noqa: BLE001 - probing is best effort
        return None


async def _ffmpeg(args: list[str], *, timeout: float = 900) -> None:
    proc = await asyncio.create_subprocess_exec(
        get_settings().ffmpeg_path,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise TTSContentError("Audio assembly timed out") from None
    if proc.returncode:
        raise TTSContentError(
            "Audio assembly failed: " + stderr.decode(errors="replace")[-300:]
        )


async def combine(
    chunks: list[bytes],
    *,
    mime: str,
    gap_ms: int = 220,
    output_format: str = "wav",
) -> bytes:
    """Concatenate chunks in order with a short gap and a gentle loudness match.

    Falls back to a lossless byte-level concatenation for WAV inputs when FFmpeg is missing.
    """
    if len(chunks) == 1:
        return chunks[0]
    suffix = ".wav" if output_format == "wav" else ".mp3"
    if not _ffmpeg_bin():
        if output_format != "wav":
            raise TTSContentError("FFmpeg is required to combine MP3 chunks")
        return _concat_wav(chunks)
    with tempfile.TemporaryDirectory(prefix="tts-combine-") as tmp:
        root = Path(tmp)
        inputs: list[str] = []
        for i, data in enumerate(chunks):
            part = root / f"part-{i:03d}.audio"
            part.write_bytes(data)
            inputs.append(str(part))
        silence = root / "silence.wav"
        await _ffmpeg([
            "-y", "-f", "lavfi", "-i",
            f"anullsrc=r=44100:cl=mono:d={gap_ms / 1000:.3f}",
            "-t", f"{gap_ms / 1000:.3f}", str(silence),
        ])
        args: list[str] = ["-y"]
        for part in [*inputs, str(silence)]:
            args += ["-i", str(part)]
        n = len(inputs)
        joined = []
        for i in range(n):
            joined.append(f"[{i}:a]")
            if i < n - 1:
                joined.append(f"[{n}:a]")
        filter_complex = (
            "".join(joined)
            + f"concat=n={len(inputs) * 2 - 1}:v=0:a=1[cat];"
            "[cat]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
        )
        out = root / f"combined{suffix}"
        codec = ["-c:a", "pcm_s16le"] if suffix == ".wav" else ["-c:a", "libmp3lame", "-b:a", "192k"]
        await _ffmpeg(
            [*args, "-filter_complex", filter_complex, "-map", "[out]", "-ar", "44100", "-ac", "1",
             *codec, str(out)]
        )
        return out.read_bytes()


def _concat_wav(chunks: list[bytes]) -> bytes:
    import io

    frames: list[bytes] = []
    params: tuple[int, int, int] | None = None
    for data in chunks:
        data = _resample_to_wav(data) if sniff_format(data) != "wav" else data
        with wave.open(io.BytesIO(data), "rb") as wav:
            current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            if params is None:
                params = current
            if current != params:
                raise TTSContentError("Cannot concatenate WAV chunks with different formats")
            frames.append(wav.readframes(wav.getnframes()))
    channels, width, rate = params or (1, 2, 44100)
    silence = b"\x00" * (channels * width * int(rate * 0.22))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        for i, frame in enumerate(frames):
            out.writeframes(frame)
            if i < len(frames) - 1:
                out.writeframes(silence)
    return buffer.getvalue()


def _resample_to_wav(data: bytes, *, rate: int = 44100) -> bytes:
    """Convert any container to mono 16-bit WAV. Best effort: returns the input when impossible."""
    if not _ffmpeg_bin():
        return data
    import subprocess

    with tempfile.TemporaryDirectory(prefix="tts-resample-") as tmp:
        src = Path(tmp) / "in.audio"
        src.write_bytes(data)
        out = Path(tmp) / "out.wav"
        subprocess.run(
            [
                get_settings().ffmpeg_path, "-y", "-i", str(src),
                "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(out),
            ],
            capture_output=True,
            timeout=180,
            check=False,
        )
        return out.read_bytes() if out.exists() else data


async def normalise(data: bytes, *, mime: str, target_format: str = "wav") -> bytes:
    """Re-encode to the target container with loudness normalisation."""
    if not _ffmpeg_bin():
        return data
    with tempfile.TemporaryDirectory(prefix="tts-normalise-") as tmp:
        root = Path(tmp)
        src = root / "in.audio"
        src.write_bytes(data)
        out = root / ("out.wav" if target_format == "wav" else "out.mp3")
        codec = ["-c:a", "pcm_s16le"] if target_format == "wav" else ["-c:a", "libmp3lame", "-b:a", "192k"]
        await _ffmpeg([
            "-y", "-i", str(src), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1",
            *codec, str(out),
        ])
        return out.read_bytes()


def duration_of(data: bytes) -> float:
    """Duration in seconds without writing to the storage root."""
    probed = probe(data)
    if probed and probed.duration_s:
        return probed.duration_s
    if data[:4] == b"RIFF":
        import io

        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                return round(wav.getnframes() / float(wav.getframerate()), 2)
        except wave.Error:
            pass
    return 0.0


__all__ = [
    "AudioProbe",
    "MIME_BY_EXT",
    "combine",
    "duration_of",
    "normalise",
    "probe",
    "probe_duration",
    "sniff_format",
    "validate_audio",
    "validate_wav",
    "wav_bytes",
]
