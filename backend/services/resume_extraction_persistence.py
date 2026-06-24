"""
Service helpers for persisting scored resume-extraction results.

This module sits above the raw SQL helper in
`backend.db.resume_extraction_persistence` and below the operator-facing
scripts.

It gives the rest of the repository a stable way to talk about:

- deciding whether an extraction result is complete enough to persist
- deciding whether a no-resume JobAdder candidate is still worth persisting as
  a profile-only contact
- normalising one accepted result into a persistence payload
- hashing provenance payloads before they are written to `source_records`
- keeping business-level persistence rules out of the CLI scripts

Why this module exists
----------------------
The project now has three distinct concerns:

- extracting structured candidate data reliably
- deciding when that structured data is safe enough to become canonical state
- deciding when a candidate without a usable CV is still valuable enough to
  persist as a profile-only record

The database helper should only care about writes. It should not decide whether
the extraction result deserves persistence in the first place.

That decision belongs here.

Current policy
--------------
The current persistence policy is intentionally conservative but no longer
drop-happy:

- extraction failures still do not persist
- scored extraction results do persist
- the persisted record keeps the quality status and score
- callers can later filter for `pass` versus `review`/`rerun` in the UI
- no-resume JobAdder candidates may be persisted separately through a profile-
  only path that keeps identity/contact data and source provenance without
  pretending that a CV extraction happened

This keeps every CV in the database while still making quality visible.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any
from urllib.parse import quote

from backend.db.resume_extraction_persistence import (
    find_existing_resume_content_match,
    persist_jobadder_candidate_profile_snapshot,
    persist_dropbox_duplicate_resume_snapshot,
    persist_resume_extraction_snapshot,
)


def persist_accepted_resume_extraction_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one accepted resume extraction result into the canonical schema.

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

    - the source system is one of the accepted resume-ingestion sources
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

    _validate_result_is_persistable(result, allowed_quality_statuses={"pass"})
    persistence_payload = build_resume_extraction_persistence_payload(result)
    return persist_resume_extraction_snapshot(persistence_payload)


def persist_scored_resume_extraction_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one scored resume extraction result into the canonical schema.

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
        If the result is missing required fields or does not yet have a scored
        quality assessment.

    Notes
    -----
    This is the shared persistence rule for the clean backend database:

    - extraction failures do not persist
    - scored CVs do persist
    - quality score and quality status stay attached to the persisted record
    - callers can later decide whether `review` or `rerun` rows should drive
      downstream automation
    """

    _validate_result_is_persistable(
        result,
        allowed_quality_statuses={"pass", "review", "rerun"},
    )
    persistence_payload = build_resume_extraction_persistence_payload(result)
    return persist_resume_extraction_snapshot(persistence_payload)


def find_existing_resume_duplicate_match(
    *,
    cleaned_resume_text: str,
) -> dict[str, Any] | None:
    """
    Return one existing canonical resume match for cleaned resume text.

    Notes
    -----
    This helper exists so ingest scripts can short-circuit expensive LLM
    extraction work when the resume text already maps to a canonical resume
    document in Supabase.
    """

    sanitized_resume_text = _sanitize_text_preserve_structure(cleaned_resume_text)
    if sanitized_resume_text is None or sanitized_resume_text.strip() == "":
        return None

    return find_existing_resume_content_match(
        content_hash=_hash_text(sanitized_resume_text),
    )


def persist_dropbox_duplicate_resume_match(
    *,
    extraction_input: dict[str, Any],
    matched_resume: dict[str, Any],
) -> dict[str, Any]:
    """
    Reuse an existing canonical resume for a duplicate Dropbox CV upload.

    Notes
    -----
    This path is intentionally narrower than full scored extraction:

    - the Dropbox file still gets canonical provenance rows
    - the existing person/candidate/document are reused
    - the expensive structured extraction model call is skipped
    """

    persistence_payload = build_dropbox_duplicate_resume_persistence_payload(
        extraction_input=extraction_input,
        matched_resume=matched_resume,
    )
    return persist_dropbox_duplicate_resume_snapshot(persistence_payload)


def persist_jobadder_candidate_profile_without_resume(
    ingest_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one JobAdder candidate as a profile-only record when no CV exists.

    Parameters
    ----------
    ingest_payload : dict[str, Any]
        JobAdder ingest payload returned by
        `build_jobadder_candidate_ingest_shell(...)`.

    Returns
    -------
    dict[str, Any]
        Persistence summary returned by the lower-level database helper.

    Raises
    ------
    RuntimeError
        If the ingest payload is not a JobAdder payload or still has a selected
        resume attachment.

    Notes
    -----
    This helper exists to address the specific business case where a candidate
    still matters operationally even though JobAdder does not expose a usable
    resume attachment yet.

    The current profile-only path is intentionally narrow. It keeps:

    - person identity/contact fields
    - candidate status and last-contacted timestamp
    - source notes and attachment summary as provenance

    It does not pretend there is:

    - a resume document
    - a structured extraction result
    - a skill extraction

    Example
    -------
    A caller can persist a no-resume candidate directly from the ingest shell:

        from backend.services.jobadder_ingest import (
            build_jobadder_candidate_ingest_shell,
        )
        from backend.services.resume_extraction_persistence import (
            persist_jobadder_candidate_profile_without_resume,
        )

        ingest_payload = build_jobadder_candidate_ingest_shell(
            jobadder_account=2236,
            candidate_id=13812978,
        )
        persisted = persist_jobadder_candidate_profile_without_resume(
            ingest_payload
        )
        print(persisted["candidate_id"])
    """

    _validate_ingest_payload_is_profile_only_persistable(ingest_payload)
    persistence_payload = build_jobadder_candidate_profile_persistence_payload(
        ingest_payload
    )
    return persist_jobadder_candidate_profile_snapshot(persistence_payload)


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

    Example
    -------
    The returned payload contains three provenance slices such as:

        payload["candidate_source_payload"]
        payload["resume_source_payload"]
        payload["extraction_source_payload"]
    """

    extraction_input = result["extraction_input"]
    candidate_context = _sanitize_json_ready_value(
        extraction_input["candidate_context"]
    )
    latest_resume = _sanitize_json_ready_value(
        extraction_input.get("latest_resume", {})
    )
    cleaned_candidate_notes = _sanitize_json_ready_value(
        extraction_input.get("cleaned_candidate_notes", [])
    )
    prompt_input_metrics = _sanitize_json_ready_value(
        extraction_input.get("prompt_input_metrics", {})
    )
    structured_extraction = _sanitize_json_ready_value(result["structured_extraction"])
    quality_assessment = _sanitize_json_ready_value(result["quality_assessment"])
    cv_source_assessment = _sanitize_json_ready_value(
        result["cv_source_assessment"]
    )
    cleaned_resume_text = _sanitize_text_preserve_structure(
        extraction_input.get("cleaned_resume_text")
    )

    (
        full_name,
        first_name,
        last_name,
    ) = _select_candidate_name_fields(
        source_system=result["source_system"],
        candidate_context=candidate_context,
        structured_extraction=structured_extraction,
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

    # Preserve the candidate-facing source slices separately because they answer
    # different later questions:
    #
    # - candidate_source_payload: what upstream context did we ingest?
    # - resume_source_payload: which resume artefact did we use?
    # - extraction_source_payload: what accepted structured interpretation did
    #   we derive from that source material?
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
        "cleaned_candidate_notes": cleaned_candidate_notes,
        "latest_resume": latest_resume,
        "cleaned_resume_text": cleaned_resume_text,
        "resume_content_hash": _hash_text(
            cleaned_resume_text or ""
        ),
        "resume_source_uri": _build_resume_source_uri(
            source_system=result["source_system"],
            jobadder_account=result.get("jobadder_account"),
            export_source_uri=result.get("export_source_uri"),
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


def build_dropbox_duplicate_resume_persistence_payload(
    *,
    extraction_input: dict[str, Any],
    matched_resume: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the provenance-only persistence payload for a duplicate Dropbox CV.
    """

    source_system = extraction_input.get("source_system")
    if source_system != "dropbox":
        raise RuntimeError(
            "Dropbox duplicate resume reuse only supports source_system='dropbox'."
        )

    source_candidate_id = extraction_input.get("source_candidate_id")
    if not isinstance(source_candidate_id, str) or source_candidate_id.strip() == "":
        raise RuntimeError(
            "Dropbox duplicate resume reuse requires a source_candidate_id path."
        )

    candidate_context = _sanitize_json_ready_value(
        extraction_input.get("candidate_context", {})
    )
    latest_resume = _sanitize_json_ready_value(extraction_input.get("latest_resume", {}))
    cleaned_resume_text = _sanitize_text_preserve_structure(
        extraction_input.get("cleaned_resume_text")
    )
    if cleaned_resume_text is None or cleaned_resume_text.strip() == "":
        raise RuntimeError(
            "Dropbox duplicate resume reuse requires cleaned resume text."
        )

    matched_document_id = matched_resume.get("document_id")
    matched_person_id = matched_resume.get("person_id")
    matched_candidate_id = matched_resume.get("candidate_id")
    if matched_document_id is None or matched_person_id is None or matched_candidate_id is None:
        raise RuntimeError(
            "Dropbox duplicate resume reuse requires matched document, person, and candidate IDs."
        )

    quality_status = _clean_optional_string(matched_resume.get("quality_status")) or "pass"
    quality_score = matched_resume.get("quality_score")
    duplicate_match_payload = {
        "match_strategy": "resume_content_hash",
        "matched_document_id": matched_document_id,
        "matched_document_title": _clean_optional_string(
            matched_resume.get("document_title")
        ),
        "matched_person_id": matched_person_id,
        "matched_candidate_id": matched_candidate_id,
        "matched_quality_status": quality_status,
        "matched_quality_score": quality_score,
    }
    resume_content_hash = _hash_text(cleaned_resume_text)
    candidate_source_payload = {
        "candidate_context": candidate_context,
        "latest_resume": latest_resume,
        "duplicate_resume_match": duplicate_match_payload,
    }
    resume_source_payload = {
        "latest_resume": latest_resume,
        "resume_content_hash": resume_content_hash,
        "duplicate_resume_match": duplicate_match_payload,
    }
    extraction_source_payload = {
        "deduplication_strategy": "resume_content_hash",
        "llm_extraction_skipped": True,
        "quality_assessment": {
            "status": quality_status,
            "quality_score": quality_score,
            "reasons": ["existing_resume_content_hash_match"],
        },
        "matched_existing_resume": duplicate_match_payload,
        "structured_extraction": {},
    }

    return {
        "source_system": "dropbox",
        "source_candidate_id": source_candidate_id,
        "import_run_id": _build_dropbox_duplicate_import_run_id(
            source_candidate_id=source_candidate_id
        ),
        "quality_status": quality_status,
        "quality_score": quality_score,
        "matched_document_id": matched_document_id,
        "matched_person_id": matched_person_id,
        "matched_candidate_id": matched_candidate_id,
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
        "latest_resume": latest_resume,
        "cleaned_resume_text": cleaned_resume_text,
        "resume_content_hash": resume_content_hash,
        "resume_updated_at": _clean_optional_string(latest_resume.get("created_at")),
        "resume_source_uri": _build_resume_source_uri(
            source_system="dropbox",
            jobadder_account=None,
            export_source_uri=source_candidate_id,
            source_candidate_id=source_candidate_id,
            attachment_id=latest_resume.get("attachment_id"),
        ),
    }


def build_jobadder_candidate_profile_persistence_payload(
    ingest_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the narrow persistence payload for one no-resume JobAdder candidate.

    Parameters
    ----------
    ingest_payload : dict[str, Any]
        JobAdder ingest payload returned by
        `build_jobadder_candidate_ingest_shell(...)`.

    Returns
    -------
    dict[str, Any]
        Normalised payload ready for the profile-only SQL persistence helper.

    Notes
    -----
    The key design choice here is that "no CV" should still produce a useful,
    provenance-bearing canonical write when the source payload contains enough
    person/candidate signal to matter later.

    We therefore preserve two distinct provenance slices:

    - `candidate_source_payload`: the richer upstream JobAdder snapshot
    - `profile_source_payload`: the smaller statement of what profile-only
      candidate data we decided to persist and why

    Example
    -------
    The returned payload contains provenance such as:

        payload["candidate_source_payload"]["notes"]["cleaned_items"]
        payload["profile_source_payload"]["persistence_reason"]
    """

    candidate_payload = _sanitize_json_ready_value(ingest_payload["candidate"])
    attachments_payload = _sanitize_json_ready_value(
        ingest_payload.get("attachments", {})
    )
    notes_payload = _sanitize_json_ready_value(ingest_payload.get("notes", {}))
    ingest_shell = _sanitize_json_ready_value(ingest_payload.get("ingest_shell", {}))
    candidate_context = _sanitize_json_ready_value(ingest_shell.get("core_identity", {}))
    cleaned_candidate_notes = _sanitize_json_ready_value(
        notes_payload.get("cleaned_items", [])
    )

    first_name = _clean_optional_string(
        candidate_context.get("first_name")
    ) or _clean_optional_string(candidate_payload.get("firstName"))
    last_name = _clean_optional_string(
        candidate_context.get("last_name")
    ) or _clean_optional_string(candidate_payload.get("lastName"))
    full_name = _build_full_name(
        first_name=first_name,
        last_name=last_name,
    )

    primary_email = _clean_optional_string(
        candidate_context.get("email")
    ) or _clean_optional_string(candidate_payload.get("email"))
    primary_phone = _clean_optional_string(
        candidate_context.get("mobile")
    ) or _clean_optional_string(candidate_payload.get("mobile"))
    location = _clean_optional_string(
        candidate_context.get("location")
    ) or _clean_optional_string(candidate_payload.get("location"))
    linkedin_url = _pick_first_present_key(
        candidate_payload,
        "linkedinUrl",
        "linkedInUrl",
        "linkedin",
    )
    current_title = _pick_first_present_key(
        candidate_payload,
        "currentTitle",
        "currentPosition",
        "title",
    )
    current_employer = _pick_first_present_key(
        candidate_payload,
        "currentEmployer",
        "currentCompany",
        "employer",
        "company",
    )

    candidate_source_payload = {
        "candidate": candidate_payload,
        "attachments": attachments_payload,
        "notes": notes_payload,
        "ingest_shell": ingest_shell,
        "latest_resume": None,
    }
    profile_source_payload = {
        "persistence_reason": "no_resume_attachment",
        "candidate_context": candidate_context,
        "attachments_summary": {
            "attachment_count": attachments_payload.get("attachment_count"),
            "resume_attachment_count": attachments_payload.get(
                "resume_attachment_count"
            ),
        },
        "cleaned_candidate_notes": cleaned_candidate_notes,
    }

    return {
        "source_system": ingest_payload["source_system"],
        "source_candidate_id": ingest_payload["source_candidate_id"],
        "jobadder_account": ingest_payload.get("jobadder_account"),
        "import_run_id": _build_profile_only_import_run_id(
            ingest_payload=ingest_payload
        ),
        "candidate_status": _clean_optional_string(
            candidate_context.get("status")
        ) or _clean_optional_string(candidate_payload.get("status")),
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
        "summary": None,
        "last_contacted_at": _select_latest_note_timestamp(cleaned_candidate_notes),
        "resume_updated_at": None,
        "cleaned_candidate_notes": cleaned_candidate_notes,
        "candidate_source_payload": candidate_source_payload,
        "candidate_source_payload_hash": _hash_json_ready_payload(
            candidate_source_payload
        ),
        "profile_source_payload": profile_source_payload,
        "profile_source_payload_hash": _hash_json_ready_payload(
            profile_source_payload
        ),
        "profile_persistence_reason": "no_resume_attachment",
    }


def _validate_result_is_persistable(
    result: dict[str, Any],
    *,
    allowed_quality_statuses: set[str],
) -> None:
    """
    Validate that one extraction result is currently safe to persist.

    Notes
    -----
    The current write path requires a scored result, but the caller decides
    which quality bands are acceptable for that specific workflow.

    Example
    -------
    A caller can pass:

        allowed_quality_statuses={"pass", "review", "rerun"}

    when the goal is to keep every scored CV, or:

        allowed_quality_statuses={"pass"}

    when the goal is to persist only high-confidence CVs.
    """

    if result.get("source_system") not in {
        "jobadder",
        "dropbox",
        "recruiterflow",
        "outlook",
    }:
        raise RuntimeError(
            "Only JobAdder, Dropbox, Recruiterflow, and Outlook extraction results are currently supported for persistence."
        )

    quality_assessment = result.get("quality_assessment")
    if not isinstance(quality_assessment, dict):
        raise RuntimeError(
            "The extraction result is missing `quality_assessment`, so persistence "
            "cannot determine whether the result was scored."
        )

    quality_status = quality_assessment.get("status")
    if quality_status not in allowed_quality_statuses:
        raise RuntimeError(
            "This persistence path does not accept the current "
            f'`quality_assessment.status` value: {quality_status!r}.'
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

    latest_resume = extraction_input.get("latest_resume")
    if not isinstance(latest_resume, dict):
        raise RuntimeError("`extraction_input.latest_resume` must be a dictionary-like object.")

    if latest_resume.get("attachment_id") in (None, ""):
        raise RuntimeError(
            "Resume extraction persistence requires a real selected resume artefact. "
            "`extraction_input.latest_resume.attachment_id` is missing."
        )

    if _clean_optional_string(latest_resume.get("file_name")) is None:
        raise RuntimeError(
            "Resume extraction persistence requires a selected resume file name. "
            "`extraction_input.latest_resume.file_name` is missing."
        )


def _validate_ingest_payload_is_profile_only_persistable(
    ingest_payload: dict[str, Any],
) -> None:
    """
    Validate that one JobAdder ingest payload is suitable for profile-only persistence.

    Notes
    -----
    The profile-only path is intentionally reserved for candidates without a
    usable selected resume attachment. If a resume exists, callers should use
    the normal CV extraction path instead so the system does not split one
    candidate across two inconsistent write policies.

    Example
    -------
    An ingest payload with:

        {"latest_resume": None}

    can pass this validator, while a payload with:

        {"latest_resume": {"attachmentId": 12345}}

    is rejected here.
    """

    if ingest_payload.get("source_system") != "jobadder":
        raise RuntimeError(
            "Only JobAdder ingest payloads are currently supported for "
            "profile-only persistence."
        )

    for required_key in (
        "source_candidate_id",
        "candidate",
        "attachments",
        "notes",
        "ingest_shell",
    ):
        if required_key not in ingest_payload:
            raise RuntimeError(
                f"The JobAdder ingest payload is missing `{required_key}`."
            )

    if ingest_payload.get("latest_resume") is not None:
        raise RuntimeError(
            "Profile-only persistence is only intended for candidates without "
            "a selected resume attachment."
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
    source_system = result["source_system"]
    return f"{source_system}_resume_extraction:{candidate_id}:{timestamp}"


def _build_profile_only_import_run_id(*, ingest_payload: dict[str, Any]) -> str:
    """
    Build a simple import-run identifier for no-resume profile-only persistence.

    Example
    -------
    A JobAdder candidate such as `13812978` might yield:

        jobadder_candidate_profile_only:13812978:2026-05-14T18:00:00+00:00
    """

    candidate_id = ingest_payload["source_candidate_id"]
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"jobadder_candidate_profile_only:{candidate_id}:{timestamp}"


def _build_dropbox_duplicate_import_run_id(*, source_candidate_id: str) -> str:
    """
    Build a simple import-run identifier for Dropbox duplicate-content reuse.
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    return f"dropbox_resume_duplicate:{source_candidate_id}:{timestamp}"


def _build_resume_source_uri(
    *,
    source_system: str,
    jobadder_account: int | None,
    export_source_uri: str | None,
    source_candidate_id: int | str,
    attachment_id: int | str | None,
) -> str | None:
    """
    Build a stable backend-local URI for the selected resume source.

    Notes
    -----
    This is intentionally an internal-style URI rather than a direct vendor
    URL. It gives the canonical `documents` row a meaningful source reference
    even though the backend is not storing a browser-openable attachment link
    yet.

    Example
    -------
    A JobAdder call with:

        jobadder_account=2236
        source_candidate_id=16496678
        attachment_id=12345

    returns:

        "jobadder://accounts/2236/candidates/16496678/attachments/12345"

    while a Recruiterflow call with:

        source_system="recruiterflow"
        export_source_uri="/exports/Recruiterflow.zip"
        source_candidate_id=4847
        attachment_id=5679

    returns:

        "recruiterflow:///exports/Recruiterflow.zip/candidates/4847/files/5679"
    """

    if attachment_id is None:
        return None

    if source_system == "jobadder":
        if jobadder_account is None:
            return None
        return (
            f"jobadder://accounts/{jobadder_account}/candidates/"
            f"{source_candidate_id}/attachments/{attachment_id}"
        )

    if source_system == "recruiterflow":
        if not isinstance(export_source_uri, str) or export_source_uri.strip() == "":
            return None
        return (
            f"recruiterflow://{export_source_uri}/candidates/"
            f"{source_candidate_id}/files/{attachment_id}"
        )

    if source_system == "dropbox":
        if not isinstance(export_source_uri, str) or export_source_uri.strip() == "":
            return None
        encoded_path = quote(export_source_uri, safe="/")
        return (
            f"dropbox://{encoded_path}"
            f"#candidate={quote(str(source_candidate_id), safe='/')}"
            f"&attachment={quote(str(attachment_id), safe='/')}"
        )

    if source_system == "outlook":
        return None

    return None


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

    Example
    -------
    A call with:

        first_name="Roger"
        last_name="Campbell"

    returns:

        "Roger Campbell"
    """

    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None and part != ""
    ).strip()
    if joined_name != "":
        return joined_name
    return "Unknown Candidate"


def _select_candidate_name_fields(
    *,
    source_system: str,
    candidate_context: dict[str, Any],
    structured_extraction: dict[str, Any],
) -> tuple[str, str | None, str | None]:
    """
    Resolve canonical candidate-name fields from source metadata and extraction output.

    Notes
    -----
    JobAdder and Recruiterflow already carry structured upstream name fields,
    so they remain the primary source there.

    Direct Dropbox CV ingestion is different: the upstream source is just a
    file path plus filename heuristics, so when the LLM extracts a credible
    name from the CV body we should prefer that over the filename guess.
    """

    context_first_name = _clean_optional_string(candidate_context.get("first_name"))
    context_last_name = _clean_optional_string(candidate_context.get("last_name"))
    context_full_name = _clean_optional_string(candidate_context.get("full_name"))
    if context_full_name is None and (
        context_first_name is not None or context_last_name is not None
    ):
        context_full_name = _build_full_name(
            first_name=context_first_name,
            last_name=context_last_name,
        )

    extracted_first_name = _clean_optional_string(structured_extraction.get("first_name"))
    extracted_last_name = _clean_optional_string(structured_extraction.get("last_name"))
    extracted_full_name = _clean_optional_string(structured_extraction.get("full_name"))

    if source_system == "dropbox":
        preferred_first_name = extracted_first_name or context_first_name
        preferred_last_name = extracted_last_name or context_last_name
        preferred_full_name = extracted_full_name or context_full_name
    else:
        preferred_first_name = context_first_name or extracted_first_name
        preferred_last_name = context_last_name or extracted_last_name
        preferred_full_name = context_full_name or extracted_full_name

    if preferred_first_name is None and preferred_last_name is None and preferred_full_name is not None:
        preferred_first_name, preferred_last_name = _split_full_name(preferred_full_name)

    full_name = preferred_full_name or _build_full_name(
        first_name=preferred_first_name,
        last_name=preferred_last_name,
    )
    return full_name, preferred_first_name, preferred_last_name


def _split_full_name(full_name: str) -> tuple[str | None, str | None]:
    """
    Split one full-name string into first/last-name components.
    """

    parts = [part for part in full_name.split() if part]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _pick_first_nonempty(
    values: list[Any],
    *,
    fallback_value: Any,
) -> str | None:
    """
    Return the first non-empty string from a list, otherwise a fallback value.

    Example
    -------
    A call such as:

        _pick_first_nonempty(["", "roger@example.com"], fallback_value=None)

    returns:

        "roger@example.com"
    """

    for value in values:
        cleaned_value = _clean_optional_string(value)
        if cleaned_value is not None:
            return cleaned_value

    return _clean_optional_string(fallback_value)


def _pick_first_present_key(source: dict[str, Any], *keys: str) -> str | None:
    """
    Return the first non-empty string found for the supplied dictionary keys.

    Example
    -------
    A call such as:

        _pick_first_present_key(
            {"currentPosition": "Data Analyst"},
            "currentTitle",
            "currentPosition",
        )

    returns:

        "Data Analyst"
    """

    for key in keys:
        cleaned_value = _clean_optional_string(source.get(key))
        if cleaned_value is not None:
            return cleaned_value

    return None


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

    cleaned_value = value.replace("\x00", "").strip()
    if cleaned_value == "":
        return None
    return cleaned_value


def _sanitize_text_preserve_structure(value: Any) -> str | None:
    """
    Return a NUL-safe string while preserving meaningful whitespace structure.

    Example
    -------
    A resume body like:

        "Line 1\\x00\\n\\nLine 2"

    becomes:

        "Line 1\\n\\nLine 2"
    """

    if not isinstance(value, str):
        return None

    sanitized_value = value.replace("\x00", "")
    return sanitized_value if sanitized_value != "" else None


def _sanitize_json_ready_value(value: Any) -> Any:
    """
    Recursively strip NUL bytes from JSON-ready payload values.

    Notes
    -----
    Postgres text fields and JSONB string values both reject embedded NUL
    bytes. Sanitising once at the shared persistence boundary keeps every
    source path consistent.
    """

    if isinstance(value, str):
        return value.replace("\x00", "")

    if isinstance(value, list):
        return [_sanitize_json_ready_value(item) for item in value]

    if isinstance(value, tuple):
        return [_sanitize_json_ready_value(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _sanitize_json_ready_value(nested_value)
            for key, nested_value in value.items()
        }

    return value


def _hash_text(text: str) -> str:
    """
    Hash source text for document/provenance deduplication.

    Example
    -------
    Two identical cleaned resume-text strings produce the same SHA-256 hash,
    which lets the persistence layer spot obvious duplicate resume content.
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

    import json

    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_jobadder_candidate_profile_persistence_payload",
    "build_dropbox_duplicate_resume_persistence_payload",
    "build_resume_extraction_persistence_payload",
    "find_existing_resume_duplicate_match",
    "persist_jobadder_candidate_profile_without_resume",
    "persist_accepted_resume_extraction_result",
    "persist_dropbox_duplicate_resume_match",
    "persist_scored_resume_extraction_result",
]
