"""
Helpers for using one uploaded CV as a transient semantic retrieval query.

This service does not persist the uploaded file. It extracts and cleans the
resume text, then uses that text directly as the semantic query against the
existing canonical CV corpus.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.services.candidate_retrieval import search_candidates_hybrid
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.text_cleaning import clean_resume_text


class UploadedResumeSearchError(RuntimeError):
    """
    Raised when one uploaded CV cannot be turned into a retrieval query.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or []


def search_candidates_by_uploaded_resume(
    *,
    content_bytes: bytes,
    file_name: str | None = None,
    content_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Extract one uploaded CV and use it as a transient semantic search query.
    """

    bounded_limit = max(1, min(int(limit), 100))

    try:
        extracted_resume = extract_text_from_resume_bytes(
            content_bytes=content_bytes,
            file_name=file_name,
            content_type=content_type,
        )
    except ResumeTextExtractionError as exc:
        raise UploadedResumeSearchError(
            exc.message,
            stage=exc.stage,
            details=exc.details,
        ) from exc

    cleaned_text = clean_resume_text(extracted_resume.get("text"))
    if cleaned_text.strip() == "":
        raise UploadedResumeSearchError(
            "Uploaded CV did not produce usable text after extraction.",
            stage="text_cleaning",
            details=[
                {"file_name": file_name},
                {"content_type": content_type},
            ],
        )

    results = search_candidates_hybrid(
        query=cleaned_text,
        limit=bounded_limit,
        include_text=False,
        include_semantic=True,
    )

    return {
        "file_name": extracted_resume.get("file_name") or file_name,
        "content_type": content_type,
        "extractor": extracted_resume.get("extractor"),
        "page_count": extracted_resume.get("page_count"),
        "character_count": len(cleaned_text),
        "cleaned_text_preview": _truncate_preview(cleaned_text),
        "limit": bounded_limit,
        "results": [
            _normalize_candidate_resume_search_result(result) for result in results
        ],
    }


def _truncate_preview(value: str, *, max_characters: int = 320) -> str:
    normalized_value = value.strip()
    if len(normalized_value) <= max_characters:
        return normalized_value
    return normalized_value[: max_characters - 3].rstrip() + "..."


def _normalize_candidate_resume_search_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": _normalize_string_value(result.get("candidate_id")),
        "person_id": _normalize_string_value(result.get("person_id")),
        "full_name": _normalize_optional_string_value(result.get("full_name")),
        "current_title": _normalize_optional_string_value(
            result.get("current_title")
        ),
        "candidate_status": _normalize_optional_string_value(
            result.get("candidate_status")
        ),
        "current_company_name": _normalize_optional_string_value(
            result.get("current_company_name")
        ),
        "resume_updated_at": _normalize_optional_datetime_value(
            result.get("resume_updated_at")
        ),
        "document_id": _normalize_string_value(result.get("document_id")),
        "document_title": _normalize_optional_string_value(
            result.get("document_title")
        ),
        "document_source_uri": _normalize_optional_string_value(
            result.get("document_source_uri")
        ),
        "match_score": float(result.get("match_score") or 0.0),
        "match_excerpt": _normalize_optional_string_value(
            result.get("match_excerpt")
        ),
    }


def _normalize_string_value(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_optional_string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_optional_datetime_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


__all__ = [
    "UploadedResumeSearchError",
    "search_candidates_by_uploaded_resume",
]
