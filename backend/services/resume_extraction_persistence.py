"""
Service helpers for persisting accepted resume-extraction results.

This module sits above the raw SQL helper in
`backend.db.resume_extraction_persistence` and below the operator-facing
scripts.

It gives the rest of the repository a stable way to talk about:

- deciding whether an extraction result is safe to persist
- normalising one accepted result into a persistence payload
- hashing provenance payloads before they are written to `source_records`
- keeping business-level persistence rules out of the CLI scripts

Why this module exists
----------------------
The project now has two distinct concerns:

- extracting structured candidate data reliably
- deciding when that structured data is safe enough to become canonical state

The database helper should only care about writes. It should not decide whether
the extraction result deserves persistence in the first place.

That decision belongs here.

Current policy
--------------
The first persistence policy is intentionally narrow:

- only accepted JobAdder extraction results are persisted
- "accepted" currently means `quality_assessment.status == "pass"`
- review/rerun/failure results stay as local batch artefacts for now

This keeps the first write path conservative while the wider ingestion design
is still settling.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from backend.db.resume_extraction_persistence import (
    persist_jobadder_resume_extraction_snapshot,
)


def persist_accepted_resume_extraction_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one accepted JobAdder extraction result into the canonical schema.

    Parameters
    ----------
    result : dict[str, Any]
        Final extraction result payload returned by the live extraction flow.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level database helper.

    Raises
    ------
    RuntimeError
        If the result is missing required fields or is not currently safe to
        persist.

    Notes
    -----
    This helper deliberately validates three things before any SQL write is
    attempted:

    - the source system is JobAdder
    - the quality gate accepted the result with `status == "pass"`
    - the payload still contains the extraction/source fields needed to build a
      provenance-bearing persistence snapshot

    Example
    -------
    A caller can take the final quality-gated result and persist it directly:

        from backend.services.resume_extraction_persistence import (
            persist_accepted_resume_extraction_result,
        )

        persisted = persist_accepted_resume_extraction_result(result)
        print(persisted["candidate_id"])
    """

    _validate_result_is_persistable(result)
    persistence_payload = build_resume_extraction_persistence_payload(result)
    return persist_jobadder_resume_extraction_snapshot(persistence_payload)


def build_resume_extraction_persistence_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one accepted extraction result.

    Parameters
    ----------
    result : dict[str, Any]
        Final extraction result payload returned by the extraction pipeline.

    Returns
    -------
    dict[str, Any]
        Normalised payload ready for the direct SQL persistence helper.

    Notes
    -----
    The persistence payload intentionally preserves more provenance than the
    canonical tables can represent directly today.

    In particular, the source-record payloads keep:

    - the candidate snapshot
    - the selected resume snapshot
    - the cleaned recruiter notes
    - the accepted structured extraction
    - the quality and richness assessments that justified persistence

    That makes the canonical writes traceable even before the project has a
    full first-class ingestion-run model.
    """

    extraction_input = result["extraction_input"]
    candidate_context = extraction_input["candidate_context"]
    latest_resume = extraction_input.get("latest_resume", {})
    cleaned_candidate_notes = extraction_input.get("cleaned_candidate_notes", [])
    prompt_input_metrics = extraction_input.get("prompt_input_metrics", {})
    structured_extraction = result["structured_extraction"]
    quality_assessment = result["quality_assessment"]
    cv_source_assessment = result["cv_source_assessment"]

    first_name = _clean_optional_string(candidate_context.get("first_name"))
    last_name = _clean_optional_string(candidate_context.get("last_name"))
    full_name = _build_full_name(
        first_name=first_name,
        last_name=last_name,
    )

    primary_email = _pick_first_nonempty(
        structured_extraction.get("emails", []),
        fallback_value=candidate_context.get("email"),
    )
    primary_phone = _pick_first_nonempty(
        structured_extraction.get("phones", []),
        fallback_value=candidate_context.get("mobile"),
    )

    location = _clean_optional_string(
        structured_extraction.get("location")
    ) or _clean_optional_string(candidate_context.get("location"))
    linkedin_url = _clean_optional_string(structured_extraction.get("linkedin_url"))
    current_title = _clean_optional_string(structured_extraction.get("current_title"))
    current_employer = _clean_optional_string(
        structured_extraction.get("current_employer")
    )

    candidate_source_payload = {
        "candidate_context": candidate_context,
        "latest_resume": latest_resume,
        "cleaned_candidate_notes": cleaned_candidate_notes,
        "prompt_input_metrics": prompt_input_metrics,
    }
    resume_source_payload = {
        "latest_resume": latest_resume,
        "prompt_truncation": result.get("prompt_truncation", {}),
        "resume_content_hash": _hash_text(
            extraction_input.get("cleaned_resume_text") or ""
        ),
    }
    extraction_source_payload = {
        "model_profile": result.get("model_profile", {}),
        "quality_gate": result.get("quality_gate", {}),
        "quality_assessment": quality_assessment,
        "cv_source_assessment": cv_source_assessment,
        "prompt_truncation": result.get("prompt_truncation", {}),
        "structured_extraction": structured_extraction,
    }

    return {
        "source_system": result["source_system"],
        "source_candidate_id": result["source_candidate_id"],
        "jobadder_account": result.get("jobadder_account"),
        "import_run_id": _build_import_run_id(result=result),
        "quality_status": quality_assessment.get("status"),
        "quality_score": quality_assessment.get("quality_score"),
        "candidate_status": _clean_optional_string(candidate_context.get("status")),
        "availability_status": None,
        "current_title": current_title,
        "current_employer": current_employer,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "primary_phone": primary_phone,
        "linkedin_url": linkedin_url,
        "location": location,
        "headline": current_title,
        "summary": _clean_optional_string(
            structured_extraction.get("professional_summary")
        ),
        "last_contacted_at": _select_latest_note_timestamp(cleaned_candidate_notes),
        "resume_updated_at": _clean_optional_string(latest_resume.get("created_at")),
        "latest_resume": latest_resume,
        "cleaned_resume_text": extraction_input.get("cleaned_resume_text"),
        "resume_content_hash": _hash_text(
            extraction_input.get("cleaned_resume_text") or ""
        ),
        "resume_source_uri": _build_jobadder_resume_source_uri(
            jobadder_account=result.get("jobadder_account"),
            source_candidate_id=result["source_candidate_id"],
            attachment_id=latest_resume.get("attachment_id"),
        ),
        "skills": list(structured_extraction.get("skills", [])),
        "tools_and_platforms": list(
            structured_extraction.get("tools_and_platforms", [])
        ),
        "candidate_source_payload": candidate_source_payload,
        "candidate_source_payload_hash": _hash_json_ready_payload(
            candidate_source_payload
        ),
        "resume_source_payload": resume_source_payload,
        "resume_source_payload_hash": _hash_json_ready_payload(resume_source_payload),
        "extraction_source_payload": extraction_source_payload,
        "extraction_source_payload_hash": _hash_json_ready_payload(
            extraction_source_payload
        ),
    }


def _validate_result_is_persistable(result: dict[str, Any]) -> None:
    """
    Validate that one extraction result is currently safe to persist.

    Notes
    -----
    The current write path is intentionally conservative. It accepts only
    quality-gated `pass` results so canonical tables are not fed by outputs the
    deterministic scorer already considers uncertain.
    """

    if result.get("source_system") != "jobadder":
        raise RuntimeError(
            "Only JobAdder extraction results are currently supported for persistence."
        )

    quality_assessment = result.get("quality_assessment")
    if not isinstance(quality_assessment, dict):
        raise RuntimeError(
            "The extraction result is missing `quality_assessment`, so persistence "
            "cannot determine whether the result was accepted."
        )

    if quality_assessment.get("status") != "pass":
        raise RuntimeError(
            "Only extraction results with `quality_assessment.status == \"pass\"` "
            "can be persisted at the moment."
        )

    for required_top_level_key in (
        "source_candidate_id",
        "extraction_input",
        "structured_extraction",
    ):
        if required_top_level_key not in result:
            raise RuntimeError(
                f"The extraction result is missing `{required_top_level_key}`."
            )

    extraction_input = result["extraction_input"]
    if not isinstance(extraction_input, dict):
        raise RuntimeError("`extraction_input` must be a dictionary-like object.")

    for required_input_key in (
        "candidate_context",
        "latest_resume",
        "cleaned_resume_text",
        "cleaned_candidate_notes",
    ):
        if required_input_key not in extraction_input:
            raise RuntimeError(
                f"`extraction_input` is missing `{required_input_key}`."
            )


def _build_import_run_id(*, result: dict[str, Any]) -> str:
    """
    Build a simple stable import-run identifier for persistence bookkeeping.

    Example
    -------
    A result for candidate `16496678` might yield:

        jobadder_resume_extraction:16496678:2026-05-11T12:00:00+00:00
    """

    candidate_id = result["source_candidate_id"]
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"jobadder_resume_extraction:{candidate_id}:{timestamp}"


def _build_jobadder_resume_source_uri(
    *,
    jobadder_account: int | None,
    source_candidate_id: int | str,
    attachment_id: int | str | None,
) -> str | None:
    """
    Build a stable backend-local URI for the selected JobAdder resume source.

    Notes
    -----
    This is intentionally an internal-style URI rather than a direct vendor URL.
    It gives the canonical `documents` row a meaningful source reference even
    though the backend is not storing a browser-openable attachment link yet.
    """

    if jobadder_account is None or attachment_id is None:
        return None

    return (
        f"jobadder://accounts/{jobadder_account}/candidates/"
        f"{source_candidate_id}/attachments/{attachment_id}"
    )


def _select_latest_note_timestamp(
    note_items: list[dict[str, Any]],
) -> str | None:
    """
    Return the latest note timestamp from cleaned recruiter-note items.

    Example
    -------
    If the cleaned notes contain both:

    - `created_at`
    - `updated_at`

    this helper prefers the latest non-empty value across the set.
    """

    timestamps: list[str] = []

    for note in note_items:
        for key in ("updated_at", "created_at"):
            raw_value = note.get(key)
            if isinstance(raw_value, str) and raw_value.strip() != "":
                timestamps.append(raw_value.strip())
                break

    if not timestamps:
        return None

    return max(timestamps)


def _build_full_name(*, first_name: str | None, last_name: str | None) -> str:
    """
    Build one display-safe full name from candidate-name parts.
    """

    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None and part != ""
    ).strip()
    if joined_name != "":
        return joined_name
    return "Unknown Candidate"


def _pick_first_nonempty(
    values: list[Any],
    *,
    fallback_value: Any,
) -> str | None:
    """
    Return the first non-empty string from a list, otherwise a fallback value.
    """

    for value in values:
        cleaned_value = _clean_optional_string(value)
        if cleaned_value is not None:
            return cleaned_value

    return _clean_optional_string(fallback_value)


def _clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or `None` when the input is blank-like.
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    if cleaned_value == "":
        return None
    return cleaned_value


def _hash_text(text: str) -> str:
    """
    Hash source text for document/provenance deduplication.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    """
    Hash one provenance payload after a stable JSON-style normalisation step.
    """

    import json

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_resume_extraction_persistence_payload",
    "persist_accepted_resume_extraction_result",
]
