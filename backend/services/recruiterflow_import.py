"""
Service helpers for the first narrow Recruiterflow static import slice.

This module turns parsed Recruiterflow ZIP export records into normalized
payloads that the lower-level DB helper can persist into the canonical schema.

It gives the rest of the repository a stable way to talk about:

- flattening Recruiterflow job records into canonical job fields
- flattening Recruiterflow candidate records into canonical person/candidate
  fields
- preserving raw Recruiterflow source payloads for provenance
- extracting nested candidate-job relationship snapshots for later application
  writes

Important scope boundary
------------------------
This module does not download Dropbox files and does not execute SQL.

Its job is narrower:

- validate the parsed Recruiterflow record shape
- build one importer-friendly payload
- delegate the final write to the DB module
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from decimal import Decimal
from typing import Any

from backend.db.recruiterflow_persistence import (
    persist_recruiterflow_candidate_file_reference as persist_recruiterflow_candidate_file_reference_snapshot,
    persist_recruiterflow_candidate_file_content as persist_recruiterflow_candidate_file_content_snapshot,
    persist_recruiterflow_candidate_snapshot,
    persist_recruiterflow_job_file_reference as persist_recruiterflow_job_file_reference_snapshot,
    persist_recruiterflow_job_snapshot,
)
from backend.services.resume_text import ResumeTextExtractionError


def persist_recruiterflow_job(
    *,
    export_source_uri: str,
    member_name: str,
    job_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow job record into the canonical schema.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the job record.

    member_name : str
        ZIP member name that contained the job JSON chunk.

    job_payload : dict[str, Any]
        One Recruiterflow job object parsed from the export.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level DB helper.

    Example
    -------
    A caller can take one parsed job record and persist it directly:

        summary = persist_recruiterflow_job(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="job/1.134.json",
            job_payload=job_record,
        )
        print(summary["job_id"])
    """

    persistence_payload = build_recruiterflow_job_persistence_payload(
        export_source_uri=export_source_uri,
        member_name=member_name,
        job_payload=job_payload,
    )
    return persist_recruiterflow_job_snapshot(persistence_payload)


def build_recruiterflow_job_persistence_payload(
    *,
    export_source_uri: str,
    member_name: str,
    job_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one Recruiterflow job record.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the job record.

    member_name : str
        ZIP member name that contained the job JSON chunk.

    job_payload : dict[str, Any]
        One Recruiterflow job object parsed from the export.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Example
    -------
    The returned payload contains provenance slices such as:

        payload["job_source_payload"]
        payload["tw_code"]
    """

    source_job_id = _coerce_positive_int(job_payload.get("id"), field_name="job.id")
    job_title = _require_nonempty_string(
        _pick_first_present_string(job_payload, "name", "title"),
        field_name="job.name",
    )
    job_description = _clean_optional_string(job_payload.get("about_position"))
    company_name = _extract_job_company_name(job_payload)
    workplace_type = _extract_nested_name(job_payload.get("remote_status"))
    employment_type = _extract_nested_name(job_payload.get("employment_type"))
    work_type = _extract_nested_name(job_payload.get("department"))
    owner_name = _extract_person_name_from_list(job_payload.get("hiring_team"))
    salary_min = _coerce_optional_decimal(job_payload.get("salary_range_start"))
    salary_max = _coerce_optional_decimal(job_payload.get("salary_range_end"))
    currency = _clean_optional_string(job_payload.get("salary_range_currency"))
    status = _extract_nested_name(job_payload.get("job_status")) or (
        "Open" if job_payload.get("is_open") is True else "Closed"
    )
    job_location = _build_locations_text(job_payload.get("locations"))
    opened_at = _pick_first_present_string(job_payload, "last_opened", "created_at")
    updated_from_source_at = _pick_first_present_string(
        job_payload,
        "last_opened",
        "created_at",
    )
    tw_code = _extract_tw_code([job_title, job_description])

    job_source_payload = {
        "export_source_uri": export_source_uri,
        "member_name": member_name,
        "source_job_id": source_job_id,
        "tw_code": tw_code,
        "job_payload": job_payload,
    }

    return {
        "source_system": "recruiterflow_job",
        "source_job_id": source_job_id,
        "tw_code": tw_code,
        "company_name": company_name,
        "job_title": job_title,
        "job_description": job_description,
        "job_location": job_location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
        "work_type": work_type,
        "source": "recruiterflow",
        "owner_name": owner_name,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "status": status,
        "opened_at": opened_at,
        "closed_at": None,
        "updated_from_source_at": updated_from_source_at,
        "job_source_payload": job_source_payload,
        "job_source_payload_hash": _hash_json_ready_payload(job_source_payload),
        "import_run_id": _build_import_run_id(
            prefix="recruiterflow_job",
            source_record_id=str(source_job_id),
            member_name=member_name,
        ),
    }


def persist_recruiterflow_candidate(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate record into the canonical schema.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        One Recruiterflow candidate object parsed from the export.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level DB helper.

    Example
    -------
    A caller can take one parsed candidate record and persist it directly:

        summary = persist_recruiterflow_candidate(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=candidate_record,
        )
        print(summary["candidate_id"])
    """

    persistence_payload = build_recruiterflow_candidate_persistence_payload(
        export_source_uri=export_source_uri,
        member_name=member_name,
        candidate_payload=candidate_payload,
    )
    return persist_recruiterflow_candidate_snapshot(persistence_payload)


def persist_recruiterflow_candidate_file_reference(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate file as a canonical document reference.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Candidate object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `candidate.files`.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level DB helper.

    Example
    -------
    A caller can persist one nested candidate file reference directly:

        summary = persist_recruiterflow_candidate_file_reference(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=candidate_record,
            file_payload=candidate_record["files"][0],
        )
    """

    persistence_payload = build_recruiterflow_candidate_file_reference_payload(
        export_source_uri=export_source_uri,
        member_name=member_name,
        candidate_payload=candidate_payload,
        file_payload=file_payload,
    )
    return persist_recruiterflow_candidate_file_reference_snapshot(
        persistence_payload
    )


def build_recruiterflow_candidate_persistence_payload(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one Recruiterflow candidate record.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        One Recruiterflow candidate object parsed from the export.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Example
    -------
    The returned payload contains provenance slices such as:

        payload["candidate_source_payload"]
        payload["job_links"]
    """

    source_candidate_id = _coerce_positive_int(
        candidate_payload.get("id"),
        field_name="candidate.id",
    )
    first_name = _clean_optional_string(candidate_payload.get("first_name"))
    last_name = _clean_optional_string(candidate_payload.get("last_name"))
    fallback_name = _clean_optional_string(candidate_payload.get("name"))
    full_name = _build_full_name(
        first_name=first_name,
        last_name=last_name,
        fallback_name=fallback_name,
    )
    primary_email = _pick_first_string_value(candidate_payload.get("email"))
    primary_phone = _pick_first_string_value(candidate_payload.get("phone_number"))
    linkedin_url = _clean_optional_string(candidate_payload.get("linkedin_profile"))
    location = _build_candidate_location(candidate_payload.get("location"))
    headline = _clean_optional_string(candidate_payload.get("current_designation"))
    summary = _clean_optional_string(candidate_payload.get("candidate_summary"))
    candidate_status = _extract_nested_name(candidate_payload.get("status"))
    current_title = _clean_optional_string(candidate_payload.get("current_designation"))
    current_employer = _clean_optional_string(
        candidate_payload.get("current_organization")
    )
    last_contacted_at = _pick_first_present_string(
        candidate_payload,
        "last_contacted",
        "latest_activity_time",
        "last_engaged",
    )
    resume_updated_at = _extract_latest_file_upload_time(candidate_payload.get("files"))
    social_profiles = _build_social_profiles(candidate_payload)

    job_links = _build_candidate_job_links(
        candidate_payload=candidate_payload,
        export_source_uri=export_source_uri,
        member_name=member_name,
    )
    tw_code = _extract_tw_code(
        [
            full_name,
            *[job_link.get("job_title") for job_link in job_links],
        ]
    )

    candidate_source_payload = {
        "export_source_uri": export_source_uri,
        "member_name": member_name,
        "source_candidate_id": source_candidate_id,
        "tw_code": tw_code,
        "candidate_payload": candidate_payload,
    }

    return {
        "source_system": "recruiterflow_candidate",
        "source_candidate_id": source_candidate_id,
        "tw_code": tw_code,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "primary_phone": primary_phone,
        "linkedin_url": linkedin_url,
        "location": location,
        "headline": headline,
        "summary": summary,
        "candidate_status": candidate_status,
        "availability_status": None,
        "current_title": current_title,
        "current_employer": current_employer,
        "last_contacted_at": last_contacted_at,
        "resume_updated_at": resume_updated_at,
        "social_profiles": social_profiles,
        "job_links": job_links,
        "candidate_source_payload": candidate_source_payload,
        "candidate_source_payload_hash": _hash_json_ready_payload(
            candidate_source_payload
        ),
        "import_run_id": _build_import_run_id(
            prefix="recruiterflow_candidate",
            source_record_id=str(source_candidate_id),
            member_name=member_name,
        ),
    }


def build_recruiterflow_candidate_file_reference_payload(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one Recruiterflow candidate file.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Candidate object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `candidate.files`.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Example
    -------
    The returned payload contains provenance slices such as:

        payload["candidate_file_source_payload"]
        payload["source_file_record_id"]
    """

    source_candidate_id = _coerce_positive_int(
        candidate_payload.get("id"),
        field_name="candidate.id",
    )
    source_file_key = _build_recruiterflow_file_source_key(
        file_payload=file_payload,
        field_name="candidate.files",
    )
    document_title = _require_nonempty_string(
        _pick_first_present_string(file_payload, "filename", "name"),
        field_name="candidate.files.filename",
    )
    source_uri = _clean_optional_string(
        _pick_first_present_string(file_payload, "link", "url")
    )
    upload_time = _pick_first_present_string(file_payload, "upload_time", "created_at")
    content_hash = _clean_optional_string(
        _pick_first_present_string(file_payload, "content_hash", "checksum")
    )
    mime_type = _guess_mime_type(document_title)

    candidate_file_source_payload = {
        "export_source_uri": export_source_uri,
        "member_name": member_name,
        "source_candidate_id": source_candidate_id,
        "source_file_id": source_file_key,
        "candidate_name": _clean_optional_string(candidate_payload.get("name")),
        "candidate_file_payload": file_payload,
    }

    return {
        "source_candidate_id": source_candidate_id,
        "source_file_record_id": f"{source_candidate_id}:{source_file_key}",
        "document_title": document_title,
        "source_uri": source_uri,
        "mime_type": mime_type,
        "content_hash": content_hash,
        "uploaded_at": upload_time,
        "candidate_file_source_payload": candidate_file_source_payload,
        "candidate_file_source_payload_hash": _hash_json_ready_payload(
            candidate_file_source_payload
        ),
        "import_run_id": _build_import_run_id(
            prefix="recruiterflow_candidate_file_reference",
            source_record_id=f"{source_candidate_id}:{source_file_key}",
            member_name=member_name,
        ),
    }


def persist_recruiterflow_job_file_reference(
    *,
    export_source_uri: str,
    member_name: str,
    job_payload: dict[str, Any],
    file_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Recruiterflow job file as a canonical document reference.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the job record.

    member_name : str
        ZIP member name that contained the job JSON chunk.

    job_payload : dict[str, Any]
        Job object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `job.files`.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level DB helper.
    """

    persistence_payload = build_recruiterflow_job_file_reference_payload(
        export_source_uri=export_source_uri,
        member_name=member_name,
        job_payload=job_payload,
        file_payload=file_payload,
    )
    return persist_recruiterflow_job_file_reference_snapshot(persistence_payload)


def persist_recruiterflow_candidate_file_content(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
    downloaded_file: dict[str, Any] | None,
    extraction_result: dict[str, Any] | None = None,
    extraction_error: ResumeTextExtractionError | None = None,
    download_error_message: str | None = None,
) -> dict[str, Any]:
    """
    Persist one Recruiterflow candidate file download/extraction attempt.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Candidate object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `candidate.files`.

    downloaded_file : dict[str, Any] | None
        Download result for the file reference, or `None` when the byte
        download failed before persistence.

    extraction_result : dict[str, Any] | None
        Successful resume text extraction result, when available.

    extraction_error : ResumeTextExtractionError | None
        Structured extraction failure, when parsing failed after a successful
        download.

    download_error_message : str | None
        Plain-text download failure message, when the file bytes could not be
        fetched at all.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level DB helper.
    """

    persistence_payload = build_recruiterflow_candidate_file_content_persistence_payload(
        export_source_uri=export_source_uri,
        member_name=member_name,
        candidate_payload=candidate_payload,
        file_payload=file_payload,
        downloaded_file=downloaded_file,
        extraction_result=extraction_result,
        extraction_error=extraction_error,
        download_error_message=download_error_message,
    )
    return persist_recruiterflow_candidate_file_content_snapshot(persistence_payload)


def build_recruiterflow_job_file_reference_payload(
    *,
    export_source_uri: str,
    member_name: str,
    job_payload: dict[str, Any],
    file_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one Recruiterflow job file.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the job record.

    member_name : str
        ZIP member name that contained the job JSON chunk.

    job_payload : dict[str, Any]
        Job object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `job.files`.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.
    """

    source_job_id = _coerce_positive_int(job_payload.get("id"), field_name="job.id")
    source_file_key = _build_recruiterflow_file_source_key(
        file_payload=file_payload,
        field_name="job.files",
    )
    job_title = _require_nonempty_string(
        _pick_first_present_string(job_payload, "name", "title"),
        field_name="job.name",
    )
    document_title = _require_nonempty_string(
        _pick_first_present_string(file_payload, "filename", "name"),
        field_name="job.files.filename",
    )
    source_uri = _clean_optional_string(
        _pick_first_present_string(file_payload, "link", "url")
    )
    content_hash = _clean_optional_string(
        _pick_first_present_string(file_payload, "content_hash", "checksum")
    )
    mime_type = _guess_mime_type(document_title)

    job_file_source_payload = {
        "export_source_uri": export_source_uri,
        "member_name": member_name,
        "source_job_id": source_job_id,
        "source_file_id": source_file_key,
        "job_title": job_title,
        "job_file_payload": file_payload,
    }

    return {
        "source_job_id": source_job_id,
        "source_file_record_id": f"{source_job_id}:{source_file_key}",
        "job_title": job_title,
        "document_title": document_title,
        "source_uri": source_uri,
        "mime_type": mime_type,
        "content_hash": content_hash,
        "job_file_source_payload": job_file_source_payload,
        "job_file_source_payload_hash": _hash_json_ready_payload(
            job_file_source_payload
        ),
        "import_run_id": _build_import_run_id(
            prefix="recruiterflow_job_file_reference",
            source_record_id=f"{source_job_id}:{source_file_key}",
            member_name=member_name,
        ),
    }


def build_recruiterflow_candidate_file_content_persistence_payload(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
    downloaded_file: dict[str, Any] | None,
    extraction_result: dict[str, Any] | None = None,
    extraction_error: ResumeTextExtractionError | None = None,
    download_error_message: str | None = None,
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one candidate-file content attempt.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the ZIP export that contained the candidate record.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Candidate object that owns the nested file reference.

    file_payload : dict[str, Any]
        Nested Recruiterflow file object from `candidate.files`.

    downloaded_file : dict[str, Any] | None
        Download result for the file reference, or `None` when the byte
        download failed.

    extraction_result : dict[str, Any] | None
        Successful extraction result, when available.

    extraction_error : ResumeTextExtractionError | None
        Structured extraction failure, when parsing failed after a successful
        download.

    download_error_message : str | None
        Plain-text download failure message, when the file bytes could not be
        fetched at all.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Example
    -------
    A successful PDF extraction returns a payload with:

        - `sync_status = "extracted"`
        - `content_hash = "..."`,
        - `extracted_text = "..."`

    while an unsupported `.doc` result returns:

        - `sync_status = "unsupported"`
        - `content_hash = "..."`,
        - `extracted_text = None`
    """

    source_candidate_id = _coerce_positive_int(
        candidate_payload.get("id"),
        field_name="candidate.id",
    )
    source_file_key = _build_recruiterflow_file_source_key(
        file_payload=file_payload,
        field_name="candidate.files",
    )
    document_title = _require_nonempty_string(
        _pick_first_present_string(file_payload, "filename", "name"),
        field_name="candidate.files.filename",
    )
    source_uri = _clean_optional_string(
        _pick_first_present_string(file_payload, "link", "url")
    )
    byte_count = None
    content_hash = None
    mime_type = _guess_mime_type(document_title)
    extracted_text = None
    character_count = None
    extractor_name = None
    page_count = None

    if downloaded_file is not None:
        raw_content_bytes = downloaded_file.get("content_bytes")
        if isinstance(raw_content_bytes, bytes):
            byte_count = len(raw_content_bytes)
            content_hash = hashlib.sha256(raw_content_bytes).hexdigest()

        downloaded_content_type = _clean_optional_string(
            downloaded_file.get("content_type")
        )
        if downloaded_content_type is not None:
            mime_type = downloaded_content_type

    error_message = download_error_message
    error_stage = None

    if extraction_result is not None:
        extracted_text = _clean_optional_string(extraction_result.get("text"))
        character_count = extraction_result.get("character_count")
        extractor_name = _clean_optional_string(extraction_result.get("extractor"))
        page_count = extraction_result.get("page_count")
        sync_status = "extracted"
    elif extraction_error is not None:
        error_message = str(extraction_error)
        error_stage = extraction_error.stage
        sync_status = (
            "unsupported"
            if extraction_error.stage == "input_validation"
            and "not supported" in extraction_error.message.lower()
            else "failed"
        )
    elif download_error_message is not None:
        sync_status = "failed"
    else:
        raise RuntimeError(
            "A Recruiterflow candidate file-content payload requires either a "
            "successful extraction result or a download/extraction failure."
        )

    candidate_file_content_source_payload = {
        "export_source_uri": export_source_uri,
        "member_name": member_name,
        "source_candidate_id": source_candidate_id,
        "source_file_id": source_file_key,
        "candidate_name": _clean_optional_string(candidate_payload.get("name")),
        "candidate_file_payload": file_payload,
        "download_summary": {
            "source_uri": source_uri,
            "mime_type": mime_type,
            "byte_count": byte_count,
            "content_hash": content_hash,
        },
        "extraction_summary": {
            "sync_status": sync_status,
            "extractor": extractor_name,
            "character_count": character_count,
            "page_count": page_count,
            "error_stage": error_stage,
            "error_message": error_message,
        },
    }

    return {
        "source_candidate_id": source_candidate_id,
        "source_file_record_id": f"{source_candidate_id}:{source_file_key}",
        "document_title": document_title,
        "source_uri": source_uri,
        "mime_type": mime_type,
        "content_hash": content_hash,
        "extracted_text": extracted_text,
        "character_count": character_count,
        "sync_status": sync_status,
        "error_message": error_message,
        "candidate_file_content_source_payload": candidate_file_content_source_payload,
        "candidate_file_content_source_payload_hash": _hash_json_ready_payload(
            candidate_file_content_source_payload
        ),
        "import_run_id": _build_import_run_id(
            prefix="recruiterflow_candidate_file_content",
            source_record_id=f"{source_candidate_id}:{source_file_key}",
            member_name=member_name,
        ),
    }


def _build_candidate_job_links(
    *,
    candidate_payload: dict[str, Any],
    export_source_uri: str,
    member_name: str,
) -> list[dict[str, Any]]:
    """
    Build normalized candidate-job link payloads from one Recruiterflow record.

    Example
    -------
    A candidate linked to `tw337 - Client Services Senior Associate` returns a
    normalized item containing the source job ID, stage name, and stable source
    payload hash for that relationship.
    """

    candidate_id = _coerce_positive_int(candidate_payload.get("id"), field_name="candidate.id")
    candidate_name = _clean_optional_string(candidate_payload.get("name"))
    current_title = _clean_optional_string(candidate_payload.get("current_designation"))
    current_employer = _clean_optional_string(candidate_payload.get("current_organization"))
    social_profiles = _build_social_profiles(candidate_payload)
    job_links: list[dict[str, Any]] = []

    for raw_job_link in candidate_payload.get("jobs", []):
        if not isinstance(raw_job_link, dict):
            continue

        source_job_id_raw = raw_job_link.get("job_id")
        if source_job_id_raw is None:
            continue

        source_job_id = _coerce_positive_int(
            source_job_id_raw,
            field_name="candidate.jobs.job_id",
        )
        job_title = _pick_first_present_string(raw_job_link, "title", "name")
        source_payload = {
            "export_source_uri": export_source_uri,
            "member_name": member_name,
            "source_candidate_id": candidate_id,
            "source_job_id": source_job_id,
            "candidate_name": candidate_name,
            "job_link_payload": raw_job_link,
        }
        job_links.append(
            {
                "source_job_id": source_job_id,
                "source_record_id": f"{candidate_id}:{source_job_id}",
                "job_title": job_title,
                "application_status": _clean_optional_string(
                    raw_job_link.get("stage_name")
                ),
                "source": _clean_optional_string(candidate_payload.get("source_name"))
                or "recruiterflow",
                "current_position": current_title,
                "current_employer": current_employer,
                "social_profiles": social_profiles,
                "applied_at": _pick_first_present_string(
                    raw_job_link,
                    "added_time",
                    "stage_moved",
                ),
                "source_payload": source_payload,
                "source_payload_hash": _hash_json_ready_payload(source_payload),
            }
        )

    return job_links


def _extract_job_company_name(job_payload: dict[str, Any]) -> str | None:
    """
    Return the best available company/client name from a Recruiterflow job.

    Example
    -------
    If the job payload exposes:

        {"client": {"name": "Pirum Systems"}}

    this helper returns `"Pirum Systems"`.
    """

    direct_name = _pick_first_present_string(
        job_payload,
        "client_company_name",
        "company_name",
        "client_name",
    )
    if direct_name is not None:
        return direct_name

    for key in ("client", "company"):
        nested_value = job_payload.get(key)
        if isinstance(nested_value, dict):
            nested_name = _extract_nested_name(nested_value)
            if nested_name is not None:
                return nested_name

    return None


def _extract_person_name_from_list(value: Any) -> str | None:
    """
    Return the first sensible person-like name from a list payload.

    Example
    -------
    A hiring-team list containing:

        [{"name": "Tom Owens"}]

    returns `"Tom Owens"`.
    """

    if not isinstance(value, list):
        return None

    for item in value:
        if not isinstance(item, dict):
            continue
        full_name = _clean_optional_string(item.get("name"))
        if full_name is not None:
            return full_name

        first_name = _clean_optional_string(item.get("first_name"))
        last_name = _clean_optional_string(item.get("last_name"))
        if first_name or last_name:
            return " ".join(part for part in (first_name, last_name) if part).strip()

    return None


def _build_locations_text(value: Any) -> str | None:
    """
    Build one readable location string from a Recruiterflow locations payload.

    Example
    -------
    A list such as:

        [{"city": "London", "country": "United Kingdom"}]

    becomes:

        "London, United Kingdom"
    """

    if not isinstance(value, list):
        return None

    rendered_locations: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        direct_name = _pick_first_present_string(item, "name", "location")
        if direct_name is not None:
            rendered_locations.append(direct_name)
            continue

        parts = [
            _clean_optional_string(item.get("city")),
            _clean_optional_string(item.get("state")),
            _clean_optional_string(item.get("country")),
        ]
        rendered_text = ", ".join(part for part in parts if part)
        if rendered_text != "":
            rendered_locations.append(rendered_text)

    if not rendered_locations:
        return None

    return " | ".join(rendered_locations)


def _build_candidate_location(value: Any) -> str | None:
    """
    Build one readable candidate location string from a Recruiterflow payload.

    Example
    -------
    A payload such as:

        {"city": "Santiago", "country": "Chile"}

    becomes:

        "Santiago, Chile"
    """

    if not isinstance(value, dict):
        return None

    direct_location = _pick_first_present_string(value, "location")
    if direct_location is not None:
        return direct_location

    parts = [
        _clean_optional_string(value.get("city")),
        _clean_optional_string(value.get("state")),
        _clean_optional_string(value.get("country")),
    ]
    rendered_text = ", ".join(part for part in parts if part)
    return rendered_text or None


def _build_social_profiles(candidate_payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Build one narrow social-profiles payload from a Recruiterflow candidate.

    Example
    -------
    A candidate with LinkedIn and GitHub URLs returns:

        {
            "linkedin_url": "https://...",
            "github_url": "https://..."
        }
    """

    mapping = {
        "linkedin_url": "linkedin_profile",
        "github_url": "github_profile",
        "twitter_url": "twitter_profile",
        "facebook_url": "facebook_profile",
        "xing_url": "xing_profile",
        "angellist_url": "angellist_profile",
        "dribbble_url": "dribbble_profile",
        "behance_url": "behance_profile",
    }
    social_profiles = {
        target_key: cleaned_value
        for target_key, source_key in mapping.items()
        if (cleaned_value := _clean_optional_string(candidate_payload.get(source_key)))
        is not None
    }
    return social_profiles or None


def _extract_latest_file_upload_time(files_payload: Any) -> str | None:
    """
    Return the latest file upload timestamp from a candidate files payload.

    Example
    -------
    A candidate files list with multiple `upload_time` values returns the
    highest timestamp string found.
    """

    if not isinstance(files_payload, list):
        return None

    upload_times = [
        cleaned_value
        for item in files_payload
        if isinstance(item, dict)
        if (cleaned_value := _clean_optional_string(item.get("upload_time"))) is not None
    ]
    return max(upload_times) if upload_times else None


def _guess_mime_type(file_name: str) -> str | None:
    """
    Return the best-effort MIME type inferred from one file name.

    Example
    -------
    Passing:

        "Candidate CV.pdf"

    returns:

        "application/pdf"
    """

    guessed_type, _ = mimetypes.guess_type(file_name)
    return _clean_optional_string(guessed_type)


def _build_recruiterflow_file_source_key(
    *,
    file_payload: dict[str, Any],
    field_name: str,
) -> str:
    """
    Return one stable upstream key for a Recruiterflow file payload.

    Notes
    -----
    Recruiterflow is not fully consistent here. Candidate files often expose
    `id`, while some job files expose `file_id` instead. We accept both and
    fall back to a deterministic hash of the filename/link pair when neither
    numeric identifier is present.

    Example
    -------
    A payload with:

        {"id": 5679, "filename": "Candidate CV.pdf"}

    returns:

        "5679"
    """

    for key_name in ("id", "file_id"):
        raw_value = file_payload.get(key_name)
        if raw_value is None:
            continue
        return str(_coerce_positive_int(raw_value, field_name=f"{field_name}.{key_name}"))

    file_name = _clean_optional_string(
        _pick_first_present_string(file_payload, "filename", "name")
    )
    source_uri = _clean_optional_string(
        _pick_first_present_string(file_payload, "link", "url")
    )
    if file_name is None and source_uri is None:
        raise RuntimeError(
            f"{field_name} must expose an id, file_id, filename, or link."
        )

    fallback_payload = {
        "filename": file_name,
        "source_uri": source_uri,
    }
    return _hash_json_ready_payload(fallback_payload)[:24]


def _pick_first_string_value(value: Any) -> str | None:
    """
    Return the first non-empty string from a string-or-list-of-strings payload.

    Example
    -------
    Inputs such as:

        ["ada@example.com", "alt@example.com"]

    return:

        "ada@example.com"
    """

    if isinstance(value, str):
        return _clean_optional_string(value)

    if not isinstance(value, list):
        return None

    for item in value:
        cleaned_value = _clean_optional_string(item)
        if cleaned_value is not None:
            return cleaned_value
    return None


def _build_full_name(
    *,
    first_name: str | None,
    last_name: str | None,
    fallback_name: str | None,
) -> str:
    """
    Build one required person full name from Recruiterflow name fields.

    Example
    -------
    Passing:

        first_name="Bernardita"
        last_name="Gutierrez"

    returns:

        "Bernardita Gutierrez"
    """

    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None
    ).strip()
    if joined_name != "":
        return joined_name
    if fallback_name is not None:
        return fallback_name
    raise RuntimeError("A Recruiterflow candidate full name is required.")


def _extract_nested_name(value: Any) -> str | None:
    """
    Return the first sensible string-like name from a nested payload.

    Example
    -------
    If `remote_status == {"name": "On-site"}`, this helper returns
    `"On-site"`.
    """

    if isinstance(value, str):
        return _clean_optional_string(value)
    if not isinstance(value, dict):
        return None
    for key in ("name", "value", "title"):
        cleaned_value = _clean_optional_string(value.get(key))
        if cleaned_value is not None:
            return cleaned_value
    return None


def _pick_first_present_string(source: dict[str, Any], *keys: str) -> str | None:
    """
    Return the first non-empty string found for the supplied dictionary keys.

    Example
    -------
    A call such as:

        _pick_first_present_string(candidate, "name", "title")

    returns the first non-empty value found in that order.
    """

    for key in keys:
        cleaned_value = _clean_optional_string(source.get(key))
        if cleaned_value is not None:
            return cleaned_value
    return None


def _extract_tw_code(text_values: list[str | None]) -> str | None:
    """
    Extract the first `tw...` vacancy code from a small set of candidate strings.

    Example
    -------
    Given values such as:

        ["tw337 - Client Services Senior Associate", "Candidate linked to tw337"]

    this helper returns:

        "tw337"
    """

    for value in text_values:
        cleaned_value = _clean_optional_string(value)
        if cleaned_value is None:
            continue

        match = re.search(r"\btw\d+\b", cleaned_value, flags=re.IGNORECASE)
        if match is not None:
            return match.group(0).lower()

    return None


def _require_nonempty_string(value: str | None, *, field_name: str) -> str:
    """
    Return one required non-empty string or raise clearly.

    Example
    -------
    Passing:

        value="tw337 - Client Services Senior Associate"

    returns the stripped string unchanged.
    """

    cleaned_value = _clean_optional_string(value)
    if cleaned_value is None:
        raise RuntimeError(f"{field_name} must be a non-empty string.")
    return cleaned_value


def _coerce_positive_int(value: Any, *, field_name: str) -> int:
    """
    Coerce a provider value into a positive integer or raise clearly.

    Example
    -------
    Passing:

        value="4847"

    returns:

        4847
    """

    try:
        coerced_value = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be a positive integer.") from exc

    if coerced_value < 1:
        raise RuntimeError(f"{field_name} must be a positive integer.")

    return coerced_value


def _coerce_optional_decimal(value: Any) -> Decimal | None:
    """
    Return a Decimal for a numeric-like value, otherwise `None`.

    Example
    -------
    Passing:

        value=125000

    returns:

        Decimal("125000")
    """

    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or `None` when the input is blank-like.

    Example
    -------
    Inputs such as:

        "  Applied  "
        ""
        None

    become:

        "Applied"
        None
        None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    return cleaned_value or None


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    """
    Return a stable SHA-256 hash for one JSON-ready payload.

    Example
    -------
    A provenance payload can be hashed with:

        _hash_json_ready_payload({"source_job_id": 102})
    """

    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _build_import_run_id(
    *,
    prefix: str,
    source_record_id: str,
    member_name: str,
) -> str:
    """
    Build one stable importer run identifier for a narrow Recruiterflow record.

    Example
    -------
    A call such as:

        _build_import_run_id(
            prefix="recruiterflow_job",
            source_record_id="102",
            member_name="job/1.134.json",
        )

    returns a readable run ID that preserves the source chunk context.
    """

    return f"{prefix}:{source_record_id}:{member_name}"


__all__ = [
    "build_recruiterflow_candidate_file_content_persistence_payload",
    "build_recruiterflow_candidate_file_reference_payload",
    "build_recruiterflow_candidate_persistence_payload",
    "build_recruiterflow_job_file_reference_payload",
    "build_recruiterflow_job_persistence_payload",
    "persist_recruiterflow_candidate_file_content",
    "persist_recruiterflow_candidate_file_reference",
    "persist_recruiterflow_candidate",
    "persist_recruiterflow_job_file_reference",
    "persist_recruiterflow_job",
]
