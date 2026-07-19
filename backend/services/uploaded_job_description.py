"""
Helpers for extracting one uploaded job description into plain text.

This service does not persist the uploaded file. It extracts and cleans the
document text so the frontend can load it into the role-brief workspace before
running retrieval or shortlist actions.
"""

from __future__ import annotations

from typing import Any

from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.text_cleaning import clean_resume_text


class UploadedJobDescriptionError(RuntimeError):
    """
    Raised when one uploaded job description cannot be turned into usable text.
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


def extract_uploaded_job_description(
    *,
    content_bytes: bytes,
    file_name: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """
    Extract one uploaded job description into cleaned plain text.
    """

    try:
        extracted_document = extract_text_from_resume_bytes(
            content_bytes=content_bytes,
            file_name=file_name,
            content_type=content_type,
        )
    except ResumeTextExtractionError as exc:
        raise UploadedJobDescriptionError(
            exc.message,
            stage=exc.stage,
            details=exc.details,
        ) from exc

    cleaned_text = clean_resume_text(extracted_document.get("text"))
    if cleaned_text.strip() == "":
        raise UploadedJobDescriptionError(
            "Uploaded job description did not produce usable text after extraction.",
            stage="text_cleaning",
            details=[
                {"file_name": file_name},
                {"content_type": content_type},
            ],
        )

    return {
        "file_name": extracted_document.get("file_name") or file_name,
        "content_type": content_type,
        "extractor": extracted_document.get("extractor"),
        "page_count": extracted_document.get("page_count"),
        "character_count": len(cleaned_text),
        "cleaned_text_preview": _truncate_preview(cleaned_text),
        "job_description_text": cleaned_text,
    }


def _truncate_preview(value: str, *, max_characters: int = 320) -> str:
    normalized_value = value.strip()
    if len(normalized_value) <= max_characters:
        return normalized_value
    return normalized_value[: max_characters - 3].rstrip() + "..."


__all__ = [
    "UploadedJobDescriptionError",
    "extract_uploaded_job_description",
]
