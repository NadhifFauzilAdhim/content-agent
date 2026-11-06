"""Sentence/paragraph-aware chunking for long-form narration.

The splitter never cuts mid-sentence unless a single sentence exceeds the provider limit; in that
case it falls back to clause punctuation, then words. Chunk order is preserved and each chunk is
kept small enough that a failure only costs one chunk of regeneration.
"""

from __future__ import annotations

import re

from app.ports.tts import Chunk, TTSInvalidRequestError

_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])(\s+)")
_CLAUSE_END = re.compile(r"(?<=[,;:—–])(\s+)")
_PARAGRAPH = re.compile(r"\n\s*\n")


def _split_keep(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split on a delimiter while keeping it attached to the preceding fragment."""
    parts = pattern.split(text)
    out: list[str] = []
    for i in range(0, len(parts) - 1, 2):
        out.append(parts[i] + (parts[i + 1] if i + 1 < len(parts) else ""))
    if len(parts) % 2 == 1:
        out.append(parts[-1])
    return [p for p in out if p.strip()]


def _hard_split(text: str, limit: int) -> list[str]:
    words = text.split()
    out, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit or not current:
            current = candidate
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out


def split_text(text: str, limit: int, *, min_chunk: int = 120) -> list[Chunk]:
    """Split ``text`` into ordered chunks of at most ``limit`` characters."""
    if limit < 40:
        raise TTSInvalidRequestError("Chunk size must be at least 40 characters")
    normalised = re.sub(r"[ \t]+", " ", text.strip())
    if len(normalised) <= limit:
        return [Chunk(0, normalised)] if normalised else []

    units: list[str] = []
    for paragraph in _PARAGRAPH.split(normalised):
        for sentence in _split_keep(paragraph, _SENTENCE_END):
            if len(sentence) <= limit:
                units.append(sentence)
                continue
            for clause in _split_keep(sentence, _CLAUSE_END):
                if len(clause) <= limit:
                    units.append(clause)
                else:
                    units.extend(_hard_split(clause, limit))

    chunks: list[Chunk] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit.strip()}".strip() if current else unit.strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(Chunk(len(chunks), current.strip()))
        current = unit.strip()
    if current.strip():
        chunks.append(Chunk(len(chunks), current.strip()))
    return chunks


def reassemble(chunks: list[Chunk]) -> str:
    return " ".join(chunk.text.strip() for chunk in sorted(chunks, key=lambda c: c.index))


def char_offsets(chunks: list[Chunk]) -> list[tuple[int, int]]:
    """Character ranges of each chunk in the reassembled text (for logging/QC)."""
    offsets, cursor = [], 0
    for chunk in sorted(chunks, key=lambda c: c.index):
        length = len(chunk.text.strip())
        offsets.append((cursor, cursor + length))
        cursor += length + 1
    return offsets
