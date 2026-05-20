"""
Service helpers for persisting JobAdder application snapshots.

This module sits above the raw SQL helper in
`backend.db.application_persistence` and below operator-facing scripts.

It gives the rest of the repository a stable way to talk about:

- validating that one JobAdder application detail payload is usable
- validating that one JobAdder candidate detail payload is usable
- normalizing those two source payloads into one persistence snapshot
- hashing provenance payloads before they are written to `source_records`
- keeping business-level persistence rules out of CLI scripts

Why this module exists
----------------------
The project has now proved enough of the surrounding source landscape to stop
treating applications as abstract future entities.

For the `tw398` slice, we already know:

- JobAdder applications carry the vacancy context
- JobAdder candidate attachments are the structured CV source
- Dropbox `.eml` files preserve advert-response provenance
- Dropbox CV files can mirror the JobAdder attachment bytes exactly

That changes the next question:

    "How do we turn one live application plus one live candidate detail payload
    into a repeatable canonical write without making scripts own the business
    rules?"

This module is the answer to that narrow question.

Current policy
--------------
The first application persistence path is intentionally conservative:

- one application per call
- one candidate detail payload per call
- canonical job row must already exist or be discoverable by a conservative
  fallback
- application status is flattened to one best available text field
- candidate identity follows the same cautious reconciliation order already
  used by the resume-persistence path

This keeps the first write slice explicit while the wider ingestion design
continues to settle.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from backend.db.application_persistence import (
    persist_jobadder_application_snapshot,
)


def persist_jobadder_application_with_candidate(
    *,
    jobadder_account: int,
    application_detail_response: dict[str, Any],
    candidate_detail_response: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder application plus one JobAdder candidate snapshot.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for provenance and source URIs.

    application_detail_response : dict[str, Any]
        Live JobAdder application-detail wrapper returned by the backend route.

    candidate_detail_response : dict[str, Any]
        Live JobAdder candidate-detail wrapper returned by the backend route.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level database helper.

    Example
    -------
    A caller can take one live application detail plus one live candidate
    detail and persist them directly:

        persisted = persist_jobadder_application_with_candidate(
            jobadder_account=2236,
            application_detail_response=application_detail_response,
            candidate_detail_response=candidate_detail_response,
        )
        print(persisted["application_id"])
    """

    persistence_payload = build_jobadder_application_persistence_payload(
        jobadder_account=jobadder_account,
        application_detail_response=application_detail_response,
        candidate_detail_response=candidate_detail_response,
    )
    return persist_jobadder_application_snapshot(persistence_payload)


def build_jobadder_application_persistence_payload(
    *,
    jobadder_account: int,
    application_detail_response: dict[str, Any],
    candidate_detail_response: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one application/candidate pair.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for provenance and source URIs.

    application_detail_response : dict[str, Any]
        Live JobAdder application-detail wrapper returned by the backend route.

    candidate_detail_response : dict[str, Any]
        Live JobAdder candidate-detail wrapper returned by the backend route.

    Returns
    -------
    dict[str, Any]
        Normalized payload ready for the direct SQL persistence helper.

    Notes
    -----
    The returned payload intentionally preserves more provenance than the
    canonical tables can represent directly today.

    In particular, the source-record payloads keep:

    - the full application detail wrapper
    - the full candidate detail wrapper
    - the inferred `tw...` vacancy code
    - the local flattening decisions used for canonical application fields

    That makes the eventual write traceable even before the project has a
    broader first-class ingestion-run model for applications.

    Example
    -------
    The returned payload contains provenance slices such as:

        payload["application_source_payload"]
        payload["candidate_source_payload"]
    """

    _validate_application_detail_response(
        jobadder_account=jobadder_account,
        application_detail_response=application_detail_response,
    )
    _validate_candidate_detail_response(
        candidate_detail_response=candidate_detail_response,
    )

    application_payload = application_detail_response["application"]
    candidate_payload = candidate_detail_response["candidate"]
    assert isinstance(application_payload, dict)
    assert isinstance(candidate_payload, dict)

    source_application_id = _coerce_positive_int(
        application_payload.get("applicationId"),
        field_name="application.applicationId",
    )
    source_candidate_id = _coerce_positive_int(
        candidate_payload.get("candidateId"),
        field_name="candidate.candidateId",
    )
    source_job_id = _coerce_positive_int(
        _pick_nested_value(application_payload, "job", "jobId")
        or application_payload.get("jobId")
        or application_payload.get("jobReference"),
        field_name="application.job.jobId",
    )

    linked_candidate_id = _coerce_positive_int(
        _pick_nested_value(application_payload, "candidate", "candidateId")
        or source_candidate_id,
        field_name="application.candidate.candidateId",
    )
    if linked_candidate_id != source_candidate_id:
        raise RuntimeError(
            "Application detail candidate ID does not match candidate detail candidate ID."
        )

    first_name = _pick_first_present_string(
        candidate_payload,
        "firstName",
        "first_name",
    )
    last_name = _pick_first_present_string(
        candidate_payload,
        "lastName",
        "last_name",
    )
    full_name = _build_full_name(
        first_name=first_name,
        last_name=last_name,
    )

    primary_email = _pick_first_present_string(
        candidate_payload,
        "email",
        "primaryEmail",
    )
    primary_phone = _pick_first_present_string(
        candidate_payload,
        "mobile",
        "phone",
        "telephone",
    )
    linkedin_url = _pick_first_present_string(
        candidate_payload,
        "linkedinUrl",
        "linkedInUrl",
        "linkedin",
    )
    location = _pick_first_present_string(
        candidate_payload,
        "location",
        "address",
    )
    candidate_status = _pick_nested_name(candidate_payload, "status") or _pick_first_present_string(
        candidate_payload,
        "status",
    )

    current_title = _pick_first_present_string(
        candidate_payload,
        "currentTitle",
        "currentPosition",
        "title",
    ) or _pick_nested_value(candidate_payload, "employment", "current", "position")
    current_employer = _pick_first_present_string(
        candidate_payload,
        "currentEmployer",
        "currentCompany",
        "employer",
        "company",
    ) or _pick_nested_value(candidate_payload, "employment", "current", "employer")

    job_title = _pick_nested_value(application_payload, "job", "jobTitle") or _pick_first_present_string(
        application_payload,
        "jobTitle",
    )

    application_status = _pick_nested_value(
        application_payload,
        "status",
        "workflow",
        "stage",
    ) or _pick_nested_name(application_payload, "status") or _pick_first_present_string(
        application_payload,
        "status",
    )
    application_source = _pick_first_present_string(application_payload, "source")
    rating = _pick_first_present_string(
        application_payload,
        "rating",
    ) or _pick_nested_name(application_payload, "rating")
    candidate_rating = _pick_first_present_string(
        application_payload,
        "candidateRating",
    ) or _pick_nested_name(application_payload, "candidateRating")
    applied_at = _pick_first_present_string(
        application_payload,
        "appliedAt",
        "createdAt",
    )

    last_contacted_at = _pick_first_present_string(
        candidate_payload,
        "lastContactedAt",
        "updatedAt",
    )
    resume_updated_at = _pick_first_present_string(
        candidate_payload,
        "resumeUpdatedAt",
        "updatedAt",
    )

    tw_code = _extract_tw_code(
        [
            job_title,
            _pick_first_present_string(application_payload, "jobTitle"),
        ]
    )

    social_profiles = _build_social_profiles(
        linkedin_url=linkedin_url,
        candidate_payload=candidate_payload,
    )

    candidate_source_payload = {
        "jobadder_account": jobadder_account,
        "candidate_detail_response": candidate_detail_response,
        "tw_code": tw_code,
    }
    application_source_payload = {
        "jobadder_account": jobadder_account,
        "application_detail_response": application_detail_response,
        "source_job_id": source_job_id,
        "job_title": job_title,
        "tw_code": tw_code,
        "flattened_application_status": application_status,
    }

    return {
        "source_system": "jobadder_application",
        "jobadder_account": jobadder_account,
        "import_run_id": _build_import_run_id(
            source_application_id=source_application_id
        ),
        "source_candidate_id": source_candidate_id,
        "source_application_id": source_application_id,
        "source_job_id": source_job_id,
        "tw_code": tw_code,
        "job_title": job_title,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "primary_phone": primary_phone,
        "linkedin_url": linkedin_url,
        "location": location,
        "headline": current_title,
        "summary": None,
        "candidate_status": candidate_status,
        "availability_status": None,
        "current_title": current_title,
        "current_position": current_title,
        "current_employer": current_employer,
        "last_contacted_at": last_contacted_at,
        "resume_updated_at": resume_updated_at,
        "application_status": application_status,
        "source": application_source,
        "rating": rating,
        "candidate_rating": candidate_rating,
        "social_profiles": social_profiles,
        "applied_at": applied_at,
        "candidate_source_payload": candidate_source_payload,
        "candidate_source_payload_hash": _hash_json_ready_payload(
            candidate_source_payload
        ),
        "application_source_payload": application_source_payload,
        "application_source_payload_hash": _hash_json_ready_payload(
            application_source_payload
        ),
    }


def _validate_application_detail_response(
    *,
    jobadder_account: int,
    application_detail_response: dict[str, Any],
) -> None:
    """
    Validate that one live JobAdder application-detail response is safe to persist.

    Example
    -------
    A response object missing `application.applicationId` or a usable job ID is
    rejected here before any database write is attempted.
    """

    if jobadder_account < 1:
        raise RuntimeError("JobAdder account must be at least 1.")

    if not isinstance(application_detail_response, dict):
        raise RuntimeError("JobAdder application detail response must be an object.")

    application_payload = application_detail_response.get("application")
    if not isinstance(application_payload, dict):
        raise RuntimeError(
            "JobAdder application detail response is missing `application`."
        )

    _coerce_positive_int(
        application_payload.get("applicationId"),
        field_name="application.applicationId",
    )
    _coerce_positive_int(
        _pick_nested_value(application_payload, "job", "jobId")
        or application_payload.get("jobId")
        or application_payload.get("jobReference"),
        field_name="application.job.jobId",
    )


def _validate_candidate_detail_response(
    *,
    candidate_detail_response: dict[str, Any],
) -> None:
    """
    Validate that one live JobAdder candidate-detail response is safe to persist.

    Example
    -------
    A response object missing `candidate.candidateId` or the candidate's name
    is rejected here before any database write is attempted.
    """

    if not isinstance(candidate_detail_response, dict):
        raise RuntimeError("JobAdder candidate detail response must be an object.")

    candidate_payload = candidate_detail_response.get("candidate")
    if not isinstance(candidate_payload, dict):
        raise RuntimeError("JobAdder candidate detail response is missing `candidate`.")

    _coerce_positive_int(
        candidate_payload.get("candidateId"),
        field_name="candidate.candidateId",
    )

    first_name = _pick_first_present_string(candidate_payload, "firstName", "first_name")
    last_name = _pick_first_present_string(candidate_payload, "lastName", "last_name")
    _build_full_name(first_name=first_name, last_name=last_name)


def _build_import_run_id(*, source_application_id: int) -> str:
    """
    Build a stable import-run identifier for application persistence bookkeeping.

    Example
    -------
    An application such as `12204918` might yield:

        jobadder_application:12204918:2026-05-20T18:00:00+00:00
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    return f"jobadder_application:{source_application_id}:{timestamp}"


def _build_full_name(*, first_name: str | None, last_name: str | None) -> str:
    """
    Build one required person full name from the available name parts.

    Example
    -------
    Passing:

        first_name="Sanjeev"
        last_name="Sarda"

    returns:

        "Sanjeev Sarda"
    """

    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None
    ).strip()
    if joined_name == "":
        raise RuntimeError("A candidate full name is required for persistence.")
    return joined_name


def _pick_nested_name(payload: dict[str, Any], key: str) -> str | None:
    """
    Return the first sensible string-like name from a nested provider object.

    Example
    -------
    If `payload["status"] == {"name": "Applied"}`, this helper returns
    `"Applied"`.
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

    return None


def _pick_nested_value(payload: dict[str, Any], *keys: str) -> str | None:
    """
    Return one nested string-like value from a provider payload safely.

    Example
    -------
    Calling:

        _pick_nested_value(application, "job", "jobTitle")

    returns the nested `jobTitle` when the payload shape matches.
    """

    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    if isinstance(current, str):
        return _clean_optional_string(current)

    if isinstance(current, (int, float)) and not isinstance(current, bool):
        return str(current)

    return None


def _pick_first_present_string(source: dict[str, Any], *keys: str) -> str | None:
    """
    Return the first non-empty string found for the supplied dictionary keys.

    Example
    -------
    A call such as:

        _pick_first_present_string(candidate, "email", "primaryEmail")

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

        ["tw398 - KDB Developer", "Suitable application for tw398"]

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


def _build_social_profiles(
    *,
    linkedin_url: str | None,
    candidate_payload: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Build the first narrow social-profiles payload for canonical applications.

    Notes
    -----
    The current schema stores `applications.social_profiles` as JSON. For this
    first slice we keep that payload intentionally small and factual.

    Example
    -------
    If the candidate exposes only a LinkedIn URL, this helper returns:

        {"linkedin_url": "https://..."}
    """

    social_profiles: dict[str, Any] = {}

    if linkedin_url is not None:
        social_profiles["linkedin_url"] = linkedin_url

    raw_social_profiles = candidate_payload.get("socialProfiles")
    if isinstance(raw_social_profiles, dict):
        for key, value in raw_social_profiles.items():
            if key not in social_profiles:
                social_profiles[key] = value

    return social_profiles or None


def _coerce_positive_int(value: Any, *, field_name: str) -> int:
    """
    Coerce a provider value into a positive integer or raise clearly.

    Example
    -------
    Passing:

        value="12204918"

    returns:

        12204918
    """

    try:
        coerced_value = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be a positive integer.") from exc

    if coerced_value < 1:
        raise RuntimeError(f"{field_name} must be a positive integer.")

    return coerced_value


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
    if cleaned_value == "":
        return None
    return cleaned_value


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    """
    Hash one provenance payload after a stable JSON-style normalization step.

    Example
    -------
    Two payloads with the same keys and values but different dictionary order
    still produce the same hash because the JSON serialization is sorted.
    """

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_jobadder_application_persistence_payload",
    "persist_jobadder_application_with_candidate",
]
