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

    skill_names = [
        _string_value(skill.get("canonical_name")) or _string_value(skill.get("skill_name"))
        for skill in skills
    ]
    skill_names = [name for name in skill_names if name]
    skill_evidence = [
        _line(
            _string_value(skill.get("canonical_name"))
            or _string_value(skill.get("skill_name"))
            or "Skill",
            skill.get("evidence_text"),
        )
        for skill in skills
        if _string_value(skill.get("evidence_text"))
    ]
    skill_parts: list[str] = []
    if skill_names:
        skill_parts.append("Primary skills: " + "; ".join(skill_names[:40]))
    if skill_evidence:
        skill_parts.append("Evidence: " + " | ".join(skill_evidence[:12]))
    _append_block(
        blocks,
        block_type="skills",
        block_index=0,
        block_label="Candidate skills",
        parts=skill_parts,
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


__all__ = [
    "CandidateSemanticBlock",
    "build_candidate_semantic_blocks",
    "normalize_semantic_block_text",
]
