"""
Service helpers for persisting JobAdder jobs and Dropbox job-spec documents.

This module sits above the raw SQL helper in `backend.db.job_spec_persistence`
and below operator-facing scripts.

It gives the rest of the repository a stable way to talk about:

- validating that one JobAdder job payload is usable for persistence
- validating that one Dropbox job-spec file payload is usable for persistence
- normalising those two source payloads into one persistence snapshot
- hashing provenance payloads before they are written to `source_records`
- keeping business-level persistence rules out of CLI scripts

Why this module exists
----------------------
The current evidence now supports a much more specific question than earlier
research-only checks:

    "Can we persist one real JobAdder opportunity and one real Dropbox job-spec
    document into the canonical schema in a repeatable way?"

The database helper should only care about writes. It should not decide
whether the supplied source payloads are structurally good enough to become
canonical state in the first place.

That decision belongs here.

Current policy
--------------
The current persistence policy is intentionally narrow:

- only one JobAdder job record is in scope per call
- only one Dropbox job-spec document is in scope per call
- the JobAdder job record is the primary structured opportunity source
- the Dropbox file is the primary job-spec document source
- neither helper attempts candidate/application ingestion yet

This keeps the first job/job-spec write slice conservative while the wider
ingestion design continues to settle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

from backend.db.job_spec_persistence import persist_jobadder_job_spec_snapshot


def persist_jobadder_job_with_dropbox_job_spec(
    *,
    jobadder_account: int,
    job_detail_response: dict[str, Any],
    dropbox_account_id: str,
    dropbox_job_spec_file: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder job plus one Dropbox job-spec document.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for provenance and source URIs.

    job_detail_response : dict[str, Any]
        Live JobAdder job-detail wrapper returned by the backend preview route.

    dropbox_account_id : str
        Dropbox account identifier tied to the downloaded job-spec file.

    dropbox_job_spec_file : dict[str, Any]
        Normalised Dropbox file/extraction payload prepared by the operator
        script.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level database helper.

    Example
    -------
    A caller can take one live JobAdder job-detail response plus one downloaded
    Dropbox PDF and persist them directly:

        persisted = persist_jobadder_job_with_dropbox_job_spec(
            jobadder_account=2236,
            job_detail_response=job_detail_response,
            dropbox_account_id="dbid:AAExample",
            dropbox_job_spec_file=dropbox_job_spec_file,
        )
        print(persisted["job_id"])
    """

    persistence_payload = build_jobadder_job_spec_persistence_payload(
        jobadder_account=jobadder_account,
        job_detail_response=job_detail_response,
        dropbox_account_id=dropbox_account_id,
        dropbox_job_spec_file=dropbox_job_spec_file,
    )
    return persist_jobadder_job_spec_snapshot(persistence_payload)


def build_jobadder_job_spec_persistence_payload(
    *,
    jobadder_account: int,
    job_detail_response: dict[str, Any],
    dropbox_account_id: str,
    dropbox_job_spec_file: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one job plus one job-spec file.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for provenance and source URIs.

    job_detail_response : dict[str, Any]
        Live JobAdder job-detail wrapper returned by the backend preview route.

    dropbox_account_id : str
        Dropbox account identifier tied to the downloaded job-spec file.

    dropbox_job_spec_file : dict[str, Any]
        Normalised Dropbox file/extraction payload prepared by the operator
        script.

    Returns
    -------
    dict[str, Any]
        Normalised payload ready for the direct SQL persistence helper.

    Notes
    -----
    The persistence payload intentionally preserves more provenance than the
    canonical tables can represent directly today.

    In particular, the source-record payloads keep:

    - the live JobAdder job-detail wrapper
    - the Dropbox file metadata
    - the extracted job-spec text metrics
    - the inferred `tw...` vacancy code

    That makes the canonical writes traceable even before the project has a
    fuller first-class ingestion-run model for jobs and job specs.

    Example
    -------
    The returned payload contains two provenance slices such as:

        payload["job_source_payload"]
        payload["job_spec_source_payload"]
    """

    _validate_job_detail_response(
        jobadder_account=jobadder_account,
        job_detail_response=job_detail_response,
    )
    _validate_dropbox_job_spec_file(
        dropbox_account_id=dropbox_account_id,
        dropbox_job_spec_file=dropbox_job_spec_file,
    )

    job_payload = job_detail_response["job"]
    assert isinstance(job_payload, dict)

    source_job_id = _coerce_positive_int(job_payload.get("jobId"), field_name="jobId")
    job_title = _require_nonempty_string(job_payload.get("jobTitle"), field_name="jobTitle")
    job_description = _clean_optional_string(
        job_payload.get("jobDescription") or job_payload.get("description")
    )
    company_name = _pick_nested_name(job_payload, "company")
    status = _pick_nested_name(job_payload, "status") or _clean_optional_string(
        job_payload.get("status")
    )
    work_type = _pick_nested_name(job_payload, "workType")
    employment_type = _pick_nested_name(job_payload, "employmentType")
    workplace_type = _pick_nested_name(job_payload, "workplaceType")
    owner_name = _pick_nested_name(job_payload, "owner") or _build_person_like_name(
        job_payload.get("owner")
    )
    salary_min, salary_max, currency = _extract_salary_fields(job_payload)
    job_location = _build_job_location(job_payload)
    opened_at = _pick_first_present_key(
        job_payload,
        "openedAt",
        "openDate",
        "createdAt",
    )
    closed_at = _pick_first_present_key(
        job_payload,
        "closedAt",
        "closeDate",
    )
    updated_from_source_at = _pick_first_present_key(
        job_payload,
        "updatedAt",
        "lastUpdatedAt",
    )

    job_spec_title = _require_nonempty_string(
        dropbox_job_spec_file.get("file_name"),
        field_name="dropbox_job_spec_file.file_name",
    )
    job_spec_source_uri = _require_nonempty_string(
        dropbox_job_spec_file.get("path"),
        field_name="dropbox_job_spec_file.path",
    )
    job_spec_extracted_text = _require_nonempty_string(
        dropbox_job_spec_file.get("extracted_text"),
        field_name="dropbox_job_spec_file.extracted_text",
    )

    tw_code = _extract_tw_code(
        [
            job_title,
            job_spec_title,
            job_spec_source_uri,
        ]
    )

    job_source_payload = {
        "jobadder_account": jobadder_account,
        "job_detail_response": job_detail_response,
        "job_source_uri": _build_jobadder_job_source_uri(
            jobadder_account=jobadder_account,
            job_id=source_job_id,
        ),
        "tw_code": tw_code,
    }
    job_spec_source_payload = {
        "dropbox_account_id": dropbox_account_id,
        "file_name": job_spec_title,
        "path": job_spec_source_uri,
        "mime_type": _clean_optional_string(dropbox_job_spec_file.get("content_type")),
        "byte_count": dropbox_job_spec_file.get("byte_count"),
        "file_metadata": dropbox_job_spec_file.get("file_metadata"),
        "extractor": dropbox_job_spec_file.get("extractor"),
        "character_count": dropbox_job_spec_file.get("character_count"),
        "page_count": dropbox_job_spec_file.get("page_count"),
        "tw_code": tw_code,
    }

    return {
        "source_system": "jobadder_dropbox_job_spec",
        "jobadder_account": jobadder_account,
        "dropbox_account_id": dropbox_account_id,
        "import_run_id": _build_import_run_id(source_job_id=source_job_id),
        "source_job_id": source_job_id,
        "tw_code": tw_code,
        "company_name": company_name,
        "job_title": job_title,
        "job_description": job_description,
        "job_location": job_location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
        "work_type": work_type,
        "source": "jobadder",
        "owner_name": owner_name,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "status": status,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "updated_from_source_at": updated_from_source_at,
        "job_source_payload": job_source_payload,
        "job_source_payload_hash": _hash_json_ready_payload(job_source_payload),
        "job_spec_title": job_spec_title,
        "job_spec_source_uri": job_spec_source_uri,
        "job_spec_mime_type": _clean_optional_string(
            dropbox_job_spec_file.get("content_type")
        ),
        "job_spec_content_hash": _hash_text(job_spec_extracted_text),
        "job_spec_extracted_text": job_spec_extracted_text,
        "job_spec_source_payload": job_spec_source_payload,
        "job_spec_source_payload_hash": _hash_json_ready_payload(
            job_spec_source_payload
        ),
    }


def _validate_job_detail_response(
    *,
    jobadder_account: int,
    job_detail_response: dict[str, Any],
) -> None:
    """
    Validate that one live JobAdder job-detail response is safe to persist.

    Example
    -------
    A response object missing `job.jobId` or `job.jobTitle` is rejected here
    before any database write is attempted.
    """

    if jobadder_account < 1:
        raise RuntimeError("JobAdder account must be at least 1.")

    if not isinstance(job_detail_response, dict):
        raise RuntimeError("JobAdder job detail response must be an object.")

    job_payload = job_detail_response.get("job")
    if not isinstance(job_payload, dict):
        raise RuntimeError("JobAdder job detail response is missing `job`.")

    _coerce_positive_int(job_payload.get("jobId"), field_name="job.jobId")
    _require_nonempty_string(job_payload.get("jobTitle"), field_name="job.jobTitle")


def _validate_dropbox_job_spec_file(
    *,
    dropbox_account_id: str,
    dropbox_job_spec_file: dict[str, Any],
) -> None:
    """
    Validate that one Dropbox job-spec file payload is safe to persist.

    Example
    -------
    A payload missing the Dropbox path or extracted text is rejected here
    before any database write is attempted.
    """

    if not isinstance(dropbox_account_id, str) or dropbox_account_id.strip() == "":
        raise RuntimeError("Dropbox account ID must be a non-empty string.")

    if not isinstance(dropbox_job_spec_file, dict):
        raise RuntimeError("Dropbox job spec file payload must be an object.")

    _require_nonempty_string(
        dropbox_job_spec_file.get("path"),
        field_name="dropbox_job_spec_file.path",
    )
    _require_nonempty_string(
        dropbox_job_spec_file.get("file_name"),
        field_name="dropbox_job_spec_file.file_name",
    )
    _require_nonempty_string(
        dropbox_job_spec_file.get("extracted_text"),
        field_name="dropbox_job_spec_file.extracted_text",
    )


def _build_import_run_id(*, source_job_id: int) -> str:
    """
    Build a stable import-run identifier for job/job-spec persistence bookkeeping.

    Example
    -------
    A job such as `936462` might yield:

        jobadder_job_spec:936462:2026-05-19T18:00:00+00:00
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    return f"jobadder_job_spec:{source_job_id}:{timestamp}"


def _build_jobadder_job_source_uri(*, jobadder_account: int, job_id: int) -> str:
    """
    Build a stable backend-local URI for one JobAdder job source record.

    Example
    -------
    A call with:

        jobadder_account=2236
        job_id=936462

    returns:

        "jobadder://accounts/2236/jobs/936462"
    """

    return f"jobadder://accounts/{jobadder_account}/jobs/{job_id}"


def _pick_nested_name(payload: dict[str, Any], key: str) -> str | None:
    """
    Return the first sensible string-like name from a nested provider object.

    Example
    -------
    If `payload["company"] == {"name": "B2C2"}`, this helper returns
    `"B2C2"`.
    """

    nested_value = payload.get(key)

    if isinstance(nested_value, str):
        return _clean_optional_string(nested_value)

    if not isinstance(nested_value, dict):
        return None

    for candidate_key in ("name", "value", "title"):
        cleaned_value = _clean_optional_string(nested_value.get(candidate_key))
        if cleaned_value is not None:
            return cleaned_value

    return _build_person_like_name(nested_value)


def _build_person_like_name(value: Any) -> str | None:
    """
    Build a readable display name from a nested provider person-like object.

    Example
    -------
    An object such as:

        {"firstName": "Tom", "lastName": "Owens"}

    becomes:

        "Tom Owens"
    """

    if not isinstance(value, dict):
        return None

    direct_name = _clean_optional_string(value.get("name"))
    if direct_name is not None:
        return direct_name

    first_name = _clean_optional_string(
        value.get("firstName") or value.get("first_name")
    )
    last_name = _clean_optional_string(
        value.get("lastName") or value.get("last_name")
    )
    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None
    ).strip()
    if joined_name != "":
        return joined_name

    return _clean_optional_string(value.get("email"))


def _extract_salary_fields(job_payload: dict[str, Any]) -> tuple[Decimal | None, Decimal | None, str | None]:
    """
    Extract the first narrow salary fields from a JobAdder job payload.

    Example
    -------
    A nested provider object such as:

        {"salary": {"rateLow": 125000, "rateHigh": 125000, "currency": "GBP"}}

    becomes:

        (Decimal("125000"), Decimal("125000"), "GBP")
    """

    salary_payload = job_payload.get("salary")
    if not isinstance(salary_payload, dict):
        salary_payload = {}

    salary_min = _safe_decimal(
        salary_payload.get("rateLow") or salary_payload.get("minimum")
    )
    salary_max = _safe_decimal(
        salary_payload.get("rateHigh") or salary_payload.get("maximum")
    )
    currency = _clean_optional_string(
        salary_payload.get("currency") or job_payload.get("currency")
    )

    return salary_min, salary_max, currency


def _build_job_location(job_payload: dict[str, Any]) -> str | None:
    """
    Build the first narrow location string from a JobAdder job payload.

    Example
    -------
    If the payload exposes:

        {"location": {"city": "London", "country": "United Kingdom"}}

    this helper returns:

        "London, United Kingdom"
    """

    raw_location = job_payload.get("location")
    if isinstance(raw_location, str):
        return _clean_optional_string(raw_location)

    if not isinstance(raw_location, dict):
        return None

    direct_name = _pick_nested_name({"location": raw_location}, "location")
    if direct_name is not None:
        return direct_name

    location_parts = [
        _clean_optional_string(raw_location.get("city")),
        _clean_optional_string(raw_location.get("state")),
        _clean_optional_string(raw_location.get("country")),
    ]
    joined_location = ", ".join(part for part in location_parts if part is not None)
    if joined_location != "":
        return joined_location

    return None


def _extract_tw_code(text_values: list[str | None]) -> str | None:
    """
    Extract the first `tw...` vacancy code from a small set of candidate strings.

    Example
    -------
    Given values such as:

        ["tw398 - KDB Developer", "/jobs/tw398 - B2C2/..."]

    this helper returns:

        "tw398"
    """

    for value in text_values:
        cleaned_value = _clean_optional_string(value)
        if cleaned_value is None:
            continue

        match = re.search(r"\btw\d+\b", cleaned_value, flags=re.IGNORECASE)
        if match is not None:
            return match.group(0).lower()

    return None


def _coerce_positive_int(value: Any, *, field_name: str) -> int:
    """
    Coerce a provider value into a positive integer or raise clearly.

    Example
    -------
    Passing:

        value="936462"

    returns:

        936462
    """

    try:
        coerced_value = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be a positive integer.") from exc

    if coerced_value < 1:
        raise RuntimeError(f"{field_name} must be a positive integer.")

    return coerced_value


def _safe_decimal(value: Any) -> Decimal | None:
    """
    Convert a provider number into an optional `Decimal` safely.

    Example
    -------
    These values become:

        125000 -> Decimal("125000")
        "125000" -> Decimal("125000")
        None -> None
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _pick_first_present_key(source: dict[str, Any], *keys: str) -> str | None:
    """
    Return the first non-empty string found for the supplied dictionary keys.

    Example
    -------
    A call such as:

        _pick_first_present_key(job, "updatedAt", "lastUpdatedAt")

    returns the first non-empty value found in that order.
    """

    for key in keys:
        cleaned_value = _clean_optional_string(source.get(key))
        if cleaned_value is not None:
            return cleaned_value

    return None


def _require_nonempty_string(value: Any, *, field_name: str) -> str:
    """
    Return a stripped non-empty string or raise clearly.

    Example
    -------
    Passing:

        value=" tw398 - KDB Developer "

    returns:

        "tw398 - KDB Developer"
    """

    cleaned_value = _clean_optional_string(value)
    if cleaned_value is None:
        raise RuntimeError(f"{field_name} must be a non-empty string.")
    return cleaned_value


def _clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or `None` when the input is blank-like.

    Example
    -------
    Inputs such as:

        "  London  "
        ""
        None

    become:

        "London"
        None
        None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    if cleaned_value == "":
        return None
    return cleaned_value


def _hash_text(text: str) -> str:
    """
    Hash extracted document text for document/provenance deduplication.

    Example
    -------
    Two identical extracted job-spec text strings produce the same SHA-256
    hash, which lets the persistence layer spot obvious duplicate job-spec
    documents.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    """
    Hash one provenance payload after a stable JSON-style normalisation step.

    Example
    -------
    Two payloads with the same keys and values but different dictionary order
    still produce the same hash because the JSON serialisation is sorted.
    """

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_jobadder_job_spec_persistence_payload",
    "persist_jobadder_job_with_dropbox_job_spec",
]
