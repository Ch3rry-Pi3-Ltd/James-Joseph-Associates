"""
Structured semantic blocks for candidate-level retrieval.

This module builds the first structured semantic representation of a candidate
from canonical fields already stored in Supabase.

The goal is to give semantic search cleaner retrieval units than raw resume
chunks alone:

- profile facts
- extracted skills
- summary / current-role context

Raw CV chunks can still exist as secondary evidence later, but this structured
layer is the first recruiter-facing semantic surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from backend.services.document_chunking import estimate_token_count


_WHITESPACE_PATTERN = re.compile(r"\s+")
_DEFAULT_RESUME_CONTEXT_CHARACTER_LIMIT = 1800


@dataclass(frozen=True)
class CandidateSemanticBlock:
    """
    One structured semantic block for candidate retrieval.
    """

    block_type: str
    block_index: int
    block_label: str
    block_text: str
    token_count: int


def normalize_semantic_block_text(text: str) -> str:
    """
    Return a compact single-string representation for semantic blocks.
    """

    normalized = _WHITESPACE_PATTERN.sub(" ", text.strip())
    return normalized.strip()


def build_candidate_semantic_blocks(
    *,
    candidate: dict[str, Any],
    skills: list[dict[str, Any]] | None = None,
) -> list[CandidateSemanticBlock]:
    """
    Build structured semantic blocks from one canonical candidate snapshot.
    """

    skills = skills or []
    blocks: list[CandidateSemanticBlock] = []

    profile_lines = [
        _line("Name", candidate.get("full_name")),
        _line("Current title", candidate.get("current_title")),
        _line("Current company", candidate.get("current_company_name")),
        _line("Location", candidate.get("location")),
        _line("Headline", candidate.get("headline")),
        _line("Candidate status", candidate.get("candidate_status")),
        _line("Availability", candidate.get("availability_status")),
        _line("Notice period", candidate.get("notice_period")),
        _line("Resume updated at", candidate.get("resume_updated_at")),
    ]
    _append_block(
        blocks,
        block_type="profile",
        block_index=0,
        block_label="Candidate profile",
        parts=profile_lines,
    )

    focus_parts = [
        _line("Current title", candidate.get("current_title")),
        _line("Headline", candidate.get("headline")),
        _line("Current company", candidate.get("current_company_name")),
        _line("Summary", candidate.get("summary")),
    ]
    _append_block(
        blocks,
        block_type="focus",
        block_index=0,
        block_label="Role focus",
        parts=focus_parts,
    )

    skill_entries = [
        _skill_entry_text(skill)
        for skill in skills
    ]
    skill_entries = _ordered_unique_values([entry for entry in skill_entries if entry])[:24]
    for skill_block_index, skill_chunk in enumerate(
        _chunk_values(skill_entries, chunk_size=8)
    ):
        _append_block(
            blocks,
            block_type="skills",
            block_index=skill_block_index,
            block_label=f"Candidate skills {skill_block_index + 1}",
            parts=["Primary skills: " + "; ".join(skill_chunk)],
        )

    summary_parts = [
        _line("Summary", candidate.get("summary")),
        _line("Resume title", candidate.get("document_title")),
        _line("Resume source", candidate.get("document_source_uri")),
    ]
    _append_block(
        blocks,
        block_type="summary",
        block_index=0,
        block_label="Career summary",
        parts=summary_parts,
    )

    resume_context = _resume_context_text(candidate.get("resume_extracted_text"))
    _append_block(
        blocks,
        block_type="resume_context",
        block_index=0,
        block_label="Resume context",
        parts=[
            _line("Resume excerpt", resume_context),
        ],
    )

    return blocks


def _append_block(
    blocks: list[CandidateSemanticBlock],
    *,
    block_type: str,
    block_index: int,
    block_label: str,
    parts: list[str],
) -> None:
    normalized_parts = [part for part in parts if _string_value(part)]
    if not normalized_parts:
        return

    block_text = normalize_semantic_block_text(
        f"{block_label}. " + " ".join(normalized_parts)
    )
    if block_text == "":
        return

    blocks.append(
        CandidateSemanticBlock(
            block_type=block_type,
            block_index=block_index,
            block_label=block_label,
            block_text=block_text,
            token_count=estimate_token_count(block_text),
        )
    )


def _line(label: str, value: Any) -> str:
    normalized_value = _string_value(value)
    if normalized_value == "":
        return ""
    return f"{label}: {normalized_value}"


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _ordered_unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def _chunk_values(values: list[str], *, chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")

    return [
        values[index : index + chunk_size]
        for index in range(0, len(values), chunk_size)
    ]


def _skill_entry_text(skill: dict[str, Any]) -> str:
    skill_name = (
        _string_value(skill.get("canonical_name"))
        or _string_value(skill.get("skill_name"))
    )
    evidence_text = normalize_semantic_block_text(
        _string_value(skill.get("evidence_text"))
    )
    if skill_name == "":
        return ""
    if evidence_text == "":
        return skill_name
    return f"{skill_name}: {evidence_text}"


def _resume_context_text(value: Any) -> str:
    normalized_value = normalize_semantic_block_text(_string_value(value))
    if normalized_value == "":
        return ""

    clipped_value = normalized_value[:_DEFAULT_RESUME_CONTEXT_CHARACTER_LIMIT].strip()
    if len(clipped_value) < len(normalized_value):
        clipped_value = clipped_value.rstrip(" .,;:") + " ..."
    return clipped_value


__all__ = [
    "CandidateSemanticBlock",
    "build_candidate_semantic_blocks",
    "normalize_semantic_block_text",
]
