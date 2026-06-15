"""
Document chunking helpers for semantic retrieval backfill.

This module turns one long extracted document text into smaller retrieval units
that can later receive embeddings.

It exists because the current canonical schema already stores full extracted
document text, but semantic retrieval needs chunk-sized records rather than one
large blob per CV or job specification.
"""

from __future__ import annotations

import re


_WHITESPACE_PATTERN = re.compile(r"\s+")
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def normalize_chunk_source_text(text: str) -> str:
    """
    Return a compact, retrieval-friendly text string.

    Notes
    -----
    - Keep newlines only long enough to preserve rough paragraph boundaries.
    - Remove repeated whitespace so chunk sizes are more predictable.
    """

    normalized_lines = [
        _WHITESPACE_PATTERN.sub(" ", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    normalized_lines = [line for line in normalized_lines if line != ""]
    return "\n".join(normalized_lines).strip()


def estimate_token_count(text: str) -> int:
    """
    Return a lightweight token estimate based on whitespace-delimited words.
    """

    normalized = text.strip()
    if normalized == "":
        return 0
    return len(normalized.split())


def chunk_document_text(
    text: str,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    """
    Split one extracted document text into overlap-aware retrieval chunks.

    Strategy
    --------
    1. Normalize the source text.
    2. Prefer paragraph-level grouping when possible.
    3. Split oversized paragraphs into sentence groups.
    4. Fall back to fixed character windows only when sentence boundaries are
       still too large.
    """

    normalized_text = normalize_chunk_source_text(text)
    if normalized_text == "":
        return []

    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be zero or positive.")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")

    paragraphs = _split_into_paragraph_like_units(normalized_text, max_chars=max_chars)
    base_chunks = _merge_units_into_chunks(paragraphs, max_chars=max_chars)
    if overlap_chars == 0 or len(base_chunks) <= 1:
        return base_chunks

    return _apply_overlap(base_chunks, overlap_chars=overlap_chars)


def _split_into_paragraph_like_units(text: str, *, max_chars: int) -> list[str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(text)
        if paragraph.strip() != ""
    ]
    if not paragraphs:
        paragraphs = [text]

    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue

        units.extend(_split_large_paragraph(paragraph, max_chars=max_chars))

    return units


def _split_large_paragraph(paragraph: str, *, max_chars: int) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_PATTERN.split(paragraph)
        if sentence.strip() != ""
    ]
    if len(sentences) <= 1:
        return _split_fixed_width(paragraph, max_chars=max_chars)

    units: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence)
        proposed_length = sentence_length if current_length == 0 else current_length + 1 + sentence_length
        if proposed_length <= max_chars:
            current_parts.append(sentence)
            current_length = proposed_length
            continue

        if current_parts:
            units.append(" ".join(current_parts).strip())
            current_parts = []
            current_length = 0

        if sentence_length <= max_chars:
            current_parts.append(sentence)
            current_length = sentence_length
            continue

        units.extend(_split_fixed_width(sentence, max_chars=max_chars))

    if current_parts:
        units.append(" ".join(current_parts).strip())

    return units


def _split_fixed_width(text: str, *, max_chars: int) -> list[str]:
    units: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        units.append(text[start:end].strip())
        start = end
    return [unit for unit in units if unit != ""]


def _merge_units_into_chunks(units: list[str], *, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for unit in units:
        unit_length = len(unit)
        proposed_length = unit_length if current_length == 0 else current_length + 2 + unit_length
        if proposed_length <= max_chars:
            current_parts.append(unit)
            current_length = proposed_length
            continue

        if current_parts:
            chunks.append("\n\n".join(current_parts).strip())

        current_parts = [unit]
        current_length = unit_length

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    return [chunk for chunk in chunks if chunk != ""]


def _apply_overlap(chunks: list[str], *, overlap_chars: int) -> list[str]:
    overlapped_chunks: list[str] = []
    previous_chunk = ""

    for chunk in chunks:
        if previous_chunk == "":
            overlapped_chunks.append(chunk)
            previous_chunk = chunk
            continue

        overlap_text = previous_chunk[-overlap_chars:].strip()
        if overlap_text == "":
            overlapped_chunks.append(chunk)
        else:
            overlapped_chunks.append(f"{overlap_text}\n\n{chunk}".strip())
        previous_chunk = chunk

    return overlapped_chunks


__all__ = [
    "chunk_document_text",
    "estimate_token_count",
    "normalize_chunk_source_text",
]
