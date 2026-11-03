"""Split extracted segments into overlapping, page-aware chunks for retrieval."""

import re
from dataclasses import dataclass

from .extract import Segment

TARGET_CHARS = 1800  # ~450 tokens: big enough for context, small enough to retrieve precisely
MAX_CHARS = 2600
OVERLAP_CHARS = 250

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    text: str
    page_start: int | None
    page_end: int | None
    section: str


@dataclass
class _Unit:
    text: str
    page: int | None
    section: str


def _split_long(text: str, limit: int) -> list[str]:
    """Split text longer than `limit` at sentence boundaries, then word boundaries."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if len(sentence) > limit:
            words = sentence.split()
            sentence_parts, part = [], ""
            for word in words:
                if part and len(part) + 1 + len(word) > limit:
                    sentence_parts.append(part)
                    part = word
                else:
                    part = f"{part} {word}" if part else word
            if part:
                sentence_parts.append(part)
        else:
            sentence_parts = [sentence]
        for piece in sentence_parts:
            if current and len(current) + 1 + len(piece) > limit:
                pieces.append(current)
                current = piece
            else:
                current = f"{current} {piece}" if current else piece
    if current:
        pieces.append(current)
    return pieces


def _units(segments: list[Segment]) -> list[_Unit]:
    units: list[_Unit] = []
    for segment in segments:
        for paragraph in re.split(r"\n\s*\n", segment.text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for piece in _split_long(paragraph, MAX_CHARS - OVERLAP_CHARS):
                units.append(_Unit(piece, segment.page, segment.section))
    return units


def _overlap_tail(text: str) -> str:
    if len(text) <= OVERLAP_CHARS:
        return text
    tail = text[-OVERLAP_CHARS:]
    # Start the overlap at a sentence (or at least a word) boundary.
    sentence = _SENTENCE_END.search(tail)
    if sentence:
        return tail[sentence.end() :]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def chunk_segments(segments: list[Segment]) -> list[Chunk]:
    chunks: list[Chunk] = []
    parts: list[str] = []
    pages: list[int] = []
    section = ""
    size = 0
    has_new = False  # whether `parts` holds anything beyond the carried-over overlap

    def flush(carry_overlap: bool) -> None:
        nonlocal parts, pages, size, has_new
        if not has_new:
            return
        text = "\n\n".join(parts).strip()
        if text:
            chunks.append(
                Chunk(
                    text=text,
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                    section=section,
                )
            )
        overlap = _overlap_tail(text) if carry_overlap else ""
        parts = [overlap] if overlap else []
        pages = pages[-1:] if overlap and pages else []
        size = len(overlap)
        has_new = False

    for unit in _units(segments):
        new_section = unit.section != section
        if has_new and (size + len(unit.text) > TARGET_CHARS or (new_section and size >= TARGET_CHARS // 2)):
            # Don't carry text from one section into the next.
            flush(carry_overlap=not new_section)
        if not has_new:
            if new_section and parts:
                # A section starts in a carried-over chunk: drop the overlap from the old section.
                parts, pages, size = [], [], 0
            section = unit.section
        parts.append(unit.text)
        has_new = True
        if unit.page is not None:
            pages.append(unit.page)
        size += len(unit.text) + 2
    flush(carry_overlap=False)
    return chunks
