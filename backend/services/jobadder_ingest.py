"""
JobAdder candidate-ingest preparation helpers.

This module sits one level above the raw JobAdder API read helpers.

Why this module exists
----------------------
We already have lower-level pieces that can:

- load the stored JobAdder OAuth connection from Postgres
- refresh an expired JobAdder access token
- fetch one candidate from JobAdder
- fetch other JobAdder resources through small read-only service helpers

The next problem is different:

    "Can the backend take several JobAdder reads and turn them into one
    internal ingest-ready payload shell?"

That is what this module is for.

Scope of this first version
---------------------------
This module intentionally does not do everything.

It does not:

- run an LLM
- parse resume text itself
- write canonical candidate records
- write document records
- talk to Dropbox
- talk to Azure Blob Storage

It only prepares the raw source-side materials that later ingestion stages
will need.

Specifically, given a JobAdder account ID and a candidate ID, this module:

1. loads the stored JobAdder OAuth connection
2. makes sure the access token is usable
3. refreshes the token if needed
4. fetches the full candidate record
5. fetches the candidate's attachment list
6. fetches the candidate's notes
7. identifies the latest likely-resume attachment
8. returns one normalised internal dictionary
9. can optionally download the selected resume bytes transiently
10. can optionally extract plain text from the selected resume document bytes

Why start here
--------------
This is the right first orchestration layer because it separates two concerns:

- raw provider transport details
- ingest preparation decisions

The lower-level `backend.services.jobadder_api` module should stay focused on
single endpoint reads.

This module should stay focused on combining those reads into something the
rest of the backend can use.

Example
-------
Later, another service or route can call:

    build_jobadder_candidate_ingest_shell(
        jobadder_account=2236,
        candidate_id=16496678,
    )

and receive a structure that contains:

- the full JobAdder candidate payload
- the candidate's attachments list
- the candidate's notes list
- the best current guess at the latest resume attachment
- a smaller ingest shell for later LLM/CV work

Later, another helper in this same module can take that one step further:

    download_latest_jobadder_resume_for_candidate(
        jobadder_account=2236,
        candidate_id=16496678,
    )

and return:

- the ingest shell
- the selected resume metadata
- the transient downloaded file bytes

And a later helper in this same module can take that one stage further again:

    extract_latest_jobadder_resume_text_for_candidate(
        jobadder_account=2236,
        candidate_id=16496678,
    )

and return:

- the ingest shell
- the selected resume metadata
- the transient downloaded file bytes
- the extracted resume text bundle

In plain language:

- this module answers the question:

    "Can we get one candidate and their latest likely CV reference out of
    JobAdder in one clean step?"

- it can now download the selected CV binary transiently
- it can now parse the selected CV into plain text
- it does not yet create or update canonical records
"""

from datetime import datetime, timezone
from typing import Any, Callable

from backend.db.jobadder_oauth import (
    get_jobadder_oauth_connection,
    save_jobadder_oauth_connection,
)
from backend.services.jobadder_api import (
    JobAdderApiError,
    download_jobadder_candidate_attachment,
    fetch_jobadder_candidate_attachments,
    fetch_jobadder_candidate_detail,
    fetch_jobadder_candidate_notes,
)
from backend.services.jobadder_oauth import (
    JobAdderOAuthExchangeError,
    is_jobadder_access_token_expired,
    refresh_jobadder_access_token,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.text_cleaning import (
    clean_jobadder_note_text,
    clean_resume_text,
)


class JobAdderIngestPreparationError(RuntimeError):
    """
    Raised when the backend cannot prepare a JobAdder candidate ingest payload.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    stage : str
        Small machine-readable label for the orchestration stage that failed.

        Examples:
        - `connection_load`
        - `connection_refresh`
        - `candidate_read`
        - `attachments_read`
        - `notes_read`

    status_code : int | None
        Upstream HTTP status code when the failure came from JobAdder.

    details : list[dict[str, Any]]
        Small safe structured details that can help route handlers, logs, or
        tests explain what happened without leaking secrets.

    Example
    -------
    A caller might catch this exception and inspect:

        error.stage
        error.status_code
        error.details

    to decide whether the failure came from:

    - a missing local OAuth connection
    - a failed refresh-token request
    - a failed candidate read
    - a failed attachments read
    - a failed notes read

    Notes
    -----
    - This exception is for backend control flow.
    - It deliberately avoids carrying token values.
    - Route handlers can catch it later and convert it into the project's
      standard error response shape.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.status_code = status_code
        self.details = details or []

    def __str__(self) -> str:
        """
        Return the human-readable error message only.

        Example
        -------
        Converting the exception to a string:

            str(error)

        returns just the main safe explanation, while the richer structured
        context stays on `error.stage`, `error.status_code`, and `error.details`.

        In plain language:

        - printing the exception should show the main explanation
        - the extra structured context stays on attributes
        """

        return self.message


def build_jobadder_candidate_ingest_shell(
    *,
    jobadder_account: int,
    candidate_id: int,
) -> dict[str, Any]:
    """
    Build one internal JobAdder candidate-ingest preparation payload.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier to fetch and prepare for ingestion.

    Returns
    -------
    dict[str, Any]
        Normalised internal dictionary containing:

        - source-system identifiers
        - the stored JobAdder account context
        - the full JobAdder candidate payload
        - the full candidate attachments payload
        - the full candidate notes payload
        - the latest likely-resume attachment reference, if found
        - a smaller ingest-ready shell for downstream stages

    Raises
    ------
    ValueError
        If the JobAdder account ID or candidate ID is invalid.

    JobAdderIngestPreparationError
        If the stored JobAdder connection cannot be loaded, refreshed, or used
        to read the required JobAdder resources safely.

    Example
    -------
    A typical call looks like:

        build_jobadder_candidate_ingest_shell(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    And a successful result contains keys such as:

        {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "candidate": {...},
            "attachments": {...},
            "notes": {...},
            "latest_resume": {...} or None,
            "ingest_shell": {...},
        }

    Notes
    -----
    - This helper is the first orchestration layer for JobAdder ingestion work.
    - It intentionally stops before downloading the resume file itself.
    - That boundary matters because file retrieval, PDF parsing, and LLM-based
      extraction will likely evolve separately from the provider record reads.

    In plain language:

    - get the candidate
    - get their attachments
    - get their notes
    - pick the most likely latest CV
    - return one clean bundle for the next ingestion step
    """
    # Reject obviously invalid identifiers before touching storage or the
    # provider.
    #
    # This early validation keeps failure modes simple:
    # - bad caller input fails immediately
    # - local storage problems fail in the connection loader
    # - provider problems fail in the read helpers
    #
    # That layering makes the system much easier to reason about than a single
    # large function that starts making external calls before it has validated
    # its own inputs.
    if jobadder_account < 1:
        raise ValueError("JobAdder jobadder_account must be at least 1.")

    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")

    # Load one connection row that is already safe to use for reads.
    #
    # By the time this helper returns, we expect:
    # - a non-empty access token
    # - a non-empty API URL
    # - a refreshed token if the previously stored one was expired
    #
    # In other words, the orchestration below can focus on the actual business
    # task of reading candidate data rather than repeatedly checking OAuth
    # plumbing concerns.
    stored_connection = _load_jobadder_connection_for_ingest(
        jobadder_account=jobadder_account,
    )

    # Use the same successful connection for both reads.
    #
    # Why this matters:
    # - The first read may force a refresh because the stored access token has
    #   expired.
    # - If that happens, we want the second read to reuse the refreshed token
    #   and refreshed API URL from the saved connection row.
    # - Reusing the winning connection keeps the orchestration deterministic and
    #   avoids accidentally mixing stale and fresh credentials in one ingest
    #   preparation run.
    candidate_detail, successful_connection = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        stage_name="candidate_read",
        provider_failure_message="JobAdder candidate detail read failed.",
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_detail(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
    )

    candidate_attachments, successful_connection = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=successful_connection,
        stage_name="attachments_read",
        provider_failure_message="JobAdder candidate attachments read failed.",
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_attachments(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
    )

    # Pull candidate notes into the same ingest bundle rather than treating
    # them as a separate later concern.
    #
    # That is important because notes often carry:
    # - recruiter/candidate communication history
    # - hiring context
    # - free-text facts that may matter later for matching or outreach
    #
    # In other words, notes are part of the candidate ingestion story, not an
    # optional sidecar.
    candidate_notes, successful_connection = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=successful_connection,
        stage_name="notes_read",
        provider_failure_message="JobAdder candidate notes read failed.",
        read_callable=lambda *, api_url, access_token: fetch_jobadder_candidate_notes(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
        ),
    )

    # Pull the flat attachment list out of the normalised response wrapper.
    #
    # The lower-level API helper deliberately returns a wrapper rather than a
    # bare list so the caller can keep useful metadata such as:
    # - links
    # - endpoint URL
    # - raw payload
    #
    # At this layer, we mainly care about the actual attachment items because
    # we are about to apply resume-selection heuristics to them.
    attachment_items = candidate_attachments.get("items", [])

    # Filter first, then sort.
    #
    # This two-step approach is intentionally easy to read:
    # - first decide which attachments even look like resumes
    # - then decide which one is the latest among that smaller set
    #
    # That separation keeps the heuristics beginner-friendly and makes later
    # debugging much easier when the client asks, "Why did we pick this file?"
    resume_attachments = [
        attachment
        for attachment in attachment_items
        if _looks_like_resume_attachment(attachment)
    ]
    latest_resume = _select_latest_resume_attachment(resume_attachments)
    note_items = candidate_notes.get("notes", [])
    cleaned_candidate_notes = _build_cleaned_candidate_note_items(note_items)

    # Pull the successful candidate object and connection metadata into local
    # names before building the final return shape.
    #
    # This is slightly more verbose than reading everything inline, but the
    # verbosity is useful:
    # - it makes the data flow explicit
    # - it reduces visual clutter in the final returned dictionary
    # - it gives later maintainers one obvious place to inspect if they need to
    #   understand which source values feed which output values
    candidate_payload = candidate_detail["candidate"]
    api_url = successful_connection["api_url"]
    jobadder_instance = successful_connection.get("jobadder_instance")

    # The top-level return includes two layers on purpose:
    #
    # 1. rich source payloads:
    #    - full candidate object
    #    - full attachment list
    #
    # 2. smaller ingest shell:
    #    - the minimum structured metadata that downstream ingestion steps can
    #      rely on without re-reading the entire source payload shape
    #
    # The intuition here is important:
    # - early in an integration, you still want the rich raw payloads because
    #   you are learning what the source system really sends
    # - but you also want to start defining a smaller internal contract that
    #   later parsing, matching, and upsert code can depend on
    #
    # Returning both gives you flexibility now without forcing every later
    # stage to stay coupled to the full JobAdder response structure forever.
    return {
        "source_system": "jobadder",
        "jobadder_account": jobadder_account,
        "jobadder_instance": (
            jobadder_instance if isinstance(jobadder_instance, str) else None
        ),
        "api_url": api_url,
        "source_candidate_id": candidate_id,
        "candidate": candidate_payload,
        "attachments": {
            "items": attachment_items,
            "attachment_count": candidate_attachments.get("attachment_count", 0),
            "resume_attachment_count": len(resume_attachments),
            "links": candidate_attachments.get("links", {}),
        },
        "notes": {
            "items": note_items,
            "cleaned_items": cleaned_candidate_notes,
            "note_count": candidate_notes.get("note_count", 0),
            "total_count": candidate_notes.get("total_count"),
            "links": candidate_notes.get("links", {}),
        },
        "latest_resume": latest_resume,
        "ingest_shell": {
            # This smaller shell is the beginning of a stable internal contract.
            #
            # The intention is that later steps such as:
            # - CV download
    # - document parsing
            # - LLM extraction
            # - canonical upsert
            #
            # can depend on this smaller structure rather than each of them
            # needing to understand every detail of JobAdder's raw response
            # shapes.
            "source_system": "jobadder",
            "source_candidate_id": candidate_id,
            "source_updated_at": candidate_payload.get("updatedAt"),
            "core_identity": {
                # Core identity fields are the easiest high-confidence fields to
                # take directly from JobAdder rather than inferring from a CV.
                #
                # Later, if a CV parser finds conflicting text, this structured
                # JobAdder data should usually remain the preferred source for
                # first-party contact identity.
                "first_name": candidate_payload.get("firstName"),
                "last_name": candidate_payload.get("lastName"),
                "email": candidate_payload.get("email"),
                "mobile": candidate_payload.get("mobile"),
            },
            "jobadder_metadata": {
                # Keep a small subset of JobAdder-native metadata close to the
                # ingest shell.
                #
                # These values are often useful for:
                # - auditing source data
                # - deciding whether a candidate changed upstream
                # - exposing source-system context in admin/debug flows
                #
                # They are also the sort of fields that tend to remain useful
                # even if the richer raw payload shape evolves later.
                "jobadder_account": jobadder_account,
                "jobadder_instance": (
                    jobadder_instance if isinstance(jobadder_instance, str) else None
                ),
                "api_url": api_url,
                "status": candidate_payload.get("status"),
                "skill_tags": candidate_payload.get("skillTags"),
                "created_at": candidate_payload.get("createdAt"),
                "updated_at": candidate_payload.get("updatedAt"),
            },
            # Keep a smaller cleaned note-text bundle inside the ingest shell
            # so later stages do not need to parse the full raw note payload
            # just to reason over note text.
            #
            # The raw note payload remains available at the top level for audit
            # and debugging work.
            "candidate_notes": cleaned_candidate_notes,
            "resume_source": _build_resume_source_reference(latest_resume),
        },
    }


def download_latest_jobadder_resume_for_candidate(
    *,
    jobadder_account: int,
    candidate_id: int,
) -> dict[str, Any]:
    """
    Download the latest likely-resume attachment for one JobAdder candidate.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier whose latest likely resume should be
        downloaded.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `source_system`
        - `jobadder_account`
        - `jobadder_instance`
        - `api_url`
        - `source_candidate_id`
        - `candidate`
        - `notes`
        - `latest_resume`
        - `resume_source`
        - `downloaded_resume`
        - `ingest_shell`

    Raises
    ------
    ValueError
        If the JobAdder account ID or candidate ID is invalid.

    JobAdderIngestPreparationError
        If the stored JobAdder connection cannot be loaded, refreshed, or used
        safely, or if no likely resume attachment exists for the candidate.

    Example
    -------
    A typical call looks like:

        download_latest_jobadder_resume_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    and a successful result contains:

        {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "notes": {...},
            "latest_resume": {...},
            "resume_source": {...},
            "downloaded_resume": {
                "content_bytes": b"...",
                "content_type": "application/pdf",
                "content_length": 123456,
                "file_name": "Roger Campbell - CV 2025.pdf",
                "endpoint_url": "...",
            },
            "ingest_shell": {...},
        }

    Notes
    -----
    - This helper is intentionally still a transient retrieval step.
    - It does not store the CV anywhere.
    - It does not parse the resume document.
    - It does not run an LLM.
    - It exists to bridge the current gap between:
        - "we can identify the right resume attachment"
        - and
        - "we can feed the real file bytes into later parsing logic"

    In plain language:

    - build the ingest shell first
    - confirm a likely resume exists
    - re-use the resume metadata already selected by the ingest shell
    - download the actual attachment bytes
    - return both the metadata and the transient file content
    """

    # Start from the existing ingest shell rather than reimplementing the
    # candidate-read and attachments-read flow from scratch.
    #
    # This is an important boundary choice:
    # - `build_jobadder_candidate_ingest_shell(...)` already knows how to:
    #     - load the connection
    #     - refresh if needed
    #     - read candidate detail
    #     - read attachments
    #     - choose the latest likely resume
    # - duplicating that logic here would create two orchestration paths that
    #   could drift apart over time
    ingest_bundle = build_jobadder_candidate_ingest_shell(
        jobadder_account=jobadder_account,
        candidate_id=candidate_id,
    )

    latest_resume = ingest_bundle.get("latest_resume")

    # Treat "no resume found" as a clear, explicit orchestration failure for
    # this helper.
    #
    # That is different from the earlier ingest-shell helper, where missing a
    # resume is still a valid partial result.
    #
    # Here, the caller has asked specifically to download the latest resume, so
    # returning success without a resume would be misleading.
    if not isinstance(latest_resume, dict):
        raise JobAdderIngestPreparationError(
            "No likely JobAdder resume attachment was found for this candidate.",
            stage="resume_selection",
            details=[
                {"jobadder_account": jobadder_account},
                {"candidate_id": candidate_id},
            ],
        )

    raw_attachment_id = latest_resume.get("attachmentId")
    attachment_id = _safe_int(raw_attachment_id)

    # Re-validate the selected attachment ID before attempting a binary
    # download.
    #
    # The selection helper works with raw source payloads, so it is worth
    # asserting here that the chosen attachment actually has a usable numeric
    # identifier before we try to build a download URL from it.
    if attachment_id is None or attachment_id < 1:
        raise JobAdderIngestPreparationError(
            "The selected JobAdder resume attachment is missing a usable attachment ID.",
            stage="resume_selection",
            details=[
                {"jobadder_account": jobadder_account},
                {"candidate_id": candidate_id},
            ],
        )

    # Re-load a read-ready connection for the binary download step.
    #
    # This may look slightly repetitive because the ingest shell already
    # completed earlier reads, but it is the safer choice for now:
    # - it guarantees the binary download starts from a fresh read-ready
    #   connection row
    # - it keeps the helper resilient even if a token expires between the shell
    #   preparation step and the attachment download step
    # - it avoids coupling this public helper too tightly to the internal
    #   intermediate connection objects used by the earlier orchestration
    #   helpers
    stored_connection = _load_jobadder_connection_for_ingest(
        jobadder_account=jobadder_account,
    )

    downloaded_resume, successful_connection = _perform_jobadder_read_with_refresh_retry(
        jobadder_account=jobadder_account,
        stored_connection=stored_connection,
        stage_name="resume_download",
        provider_failure_message="JobAdder candidate resume download failed.",
        read_callable=lambda *, api_url, access_token: download_jobadder_candidate_attachment(
            api_url=api_url,
            access_token=access_token,
            candidate_id=candidate_id,
            attachment_id=attachment_id,
        ),
    )

    # Keep the successful connection context visible at the top level of the
    # returned bundle.
    #
    # This mirrors the earlier ingest-shell structure and makes the final
    # result easier to reason about:
    # - which JobAdder account was used?
    # - which instance was used?
    # - which API base actually succeeded?
    api_url = successful_connection["api_url"]
    jobadder_instance = successful_connection.get("jobadder_instance")

    return {
        "source_system": "jobadder",
        "jobadder_account": jobadder_account,
        "jobadder_instance": (
            jobadder_instance if isinstance(jobadder_instance, str) else None
        ),
        "api_url": api_url,
        "source_candidate_id": candidate_id,
        "candidate": ingest_bundle["candidate"],
        "notes": ingest_bundle["notes"],
        "latest_resume": latest_resume,
        "resume_source": ingest_bundle["ingest_shell"]["resume_source"],
        "downloaded_resume": downloaded_resume,
        "ingest_shell": ingest_bundle["ingest_shell"],
    }


def extract_latest_jobadder_resume_text_for_candidate(
    *,
    jobadder_account: int,
    candidate_id: int,
) -> dict[str, Any]:
    """
    Download the latest likely JobAdder resume and extract plain text from it.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    candidate_id : int
        JobAdder candidate identifier whose latest likely resume should be
        downloaded and parsed.

    Returns
    -------
    dict[str, Any]
        Normalised dictionary containing:

        - `source_system`
        - `jobadder_account`
        - `jobadder_instance`
        - `api_url`
        - `source_candidate_id`
        - `candidate`
        - `notes`
        - `latest_resume`
        - `resume_source`
        - `downloaded_resume`
        - `extracted_resume_text`
        - `ingest_shell`

    Raises
    ------
    ValueError
        If the JobAdder account ID or candidate ID is invalid.

    JobAdderIngestPreparationError
        If the stored JobAdder connection cannot be loaded, refreshed, or used
        safely, if no likely resume attachment exists, or if the downloaded
        resume document cannot be turned into usable plain text.

    Example
    -------
    A typical call looks like:

        extract_latest_jobadder_resume_text_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    and a successful result contains:

        {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "notes": {...},
            "downloaded_resume": {...},
            "extracted_resume_text": {
                "text": "...",
                "cleaned_text": "...",
                "page_count": 2,
                "extractor": "pypdf",
                "file_name": "Roger Campbell - CV 2025.pdf",
                "character_count": 5120,
            },
            "ingest_shell": {...},
        }

    Notes
    -----
    - This helper is the first complete JobAdder document-to-text bridge.
    - It still stops before any LLM work.
    - It still does not write anything to the database.
    - Its job is narrower and more important than that:
        - get the right candidate
        - get the right resume
        - get the resume bytes
        - get usable plain text
    - That is the last technical boundary before the first structured LLM
      extraction stage.

    In plain language:

    - build the existing resume-download bundle
    - pull the downloaded resume bytes out of that bundle
    - extract plain text from the document
    - clean that extracted text for later reasoning
    - return both the file metadata and the text together
    """

    # Start from the existing binary-download orchestration helper rather than
    # rebuilding the same JobAdder read path again.
    #
    # That boundary matters because we already have one helper that knows how
    # to:
    # - identify the right resume
    # - validate the attachment ID
    # - download the file bytes
    #
    # Reusing it here keeps the responsibilities stacked cleanly:
    # - ingest shell helper -> metadata only
    # - resume download helper -> metadata + bytes
    # - this helper -> metadata + bytes + text
    resume_bundle = download_latest_jobadder_resume_for_candidate(
        jobadder_account=jobadder_account,
        candidate_id=candidate_id,
    )

    downloaded_resume = resume_bundle["downloaded_resume"]
    raw_content_bytes = downloaded_resume.get("content_bytes")
    raw_file_name = downloaded_resume.get("file_name")
    raw_content_type = downloaded_resume.get("content_type")
    file_name = raw_file_name if isinstance(raw_file_name, str) else None
    content_type = (
        raw_content_type if isinstance(raw_content_type, str) else None
    )

    # The text-extraction helper uses its own exception type because it sits at
    # a different abstraction level from provider reads.
    #
    # This orchestration layer converts that document-parsing failure back into
    # the JobAdder ingest error type so callers only need one high-level error
    # family for the whole "candidate -> resume -> text" flow.
    try:
        extracted_resume_text = extract_text_from_resume_bytes(
            content_bytes=raw_content_bytes,
            file_name=file_name,
            content_type=content_type,
        )
    except ResumeTextExtractionError as exc:
        details: list[dict[str, Any]] = [
            {"jobadder_account": jobadder_account},
            {"candidate_id": candidate_id},
            {"resume_text_stage": exc.stage},
        ]

        details.extend(exc.details)

        raise JobAdderIngestPreparationError(
            "JobAdder candidate resume text extraction failed.",
            stage="resume_text_extraction",
            details=details,
        ) from exc

    # Keep both the raw extracted text and the cleaned text together.
    #
    # The cleaned text is the likely input for later LLM work, but keeping the
    # raw extraction output alongside it is still useful for:
    # - debugging document parsing quality
    # - auditing what the parser produced before cleanup
    # - tuning the text-cleaning rules later
    extracted_resume_text["cleaned_text"] = clean_resume_text(
        extracted_resume_text["text"]
    )

    # Keep the final top-level shape parallel to the earlier helpers in this
    # module.
    #
    # The consistency is deliberate:
    # - callers should not need to relearn the bundle structure at each stage
    # - later code can progressively depend on richer keys such as
    #   `extracted_resume_text` without losing the earlier source context
    return {
        "source_system": resume_bundle["source_system"],
        "jobadder_account": resume_bundle["jobadder_account"],
        "jobadder_instance": resume_bundle["jobadder_instance"],
        "api_url": resume_bundle["api_url"],
        "source_candidate_id": resume_bundle["source_candidate_id"],
        "candidate": resume_bundle["candidate"],
        "notes": resume_bundle["notes"],
        "latest_resume": resume_bundle["latest_resume"],
        "resume_source": resume_bundle["resume_source"],
        "downloaded_resume": downloaded_resume,
        "extracted_resume_text": extracted_resume_text,
        "ingest_shell": resume_bundle["ingest_shell"],
    }


def _load_jobadder_connection_for_ingest(*, jobadder_account: int) -> dict[str, Any]:
    """
    Load one stored JobAdder OAuth connection and make sure it is read-ready.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    Returns
    -------
    dict[str, Any]
        Stored JobAdder connection row that contains at least a usable
        `access_token` and `api_url`.

    Raises
    ------
    JobAdderIngestPreparationError
        If the stored connection does not exist, is missing required fields, or
        requires a refresh that cannot be completed.

    Example
    -------
    If account `2236` has a valid stored connection, this helper returns that
    connection row. If the token is expired, it refreshes the token first and
    returns the refreshed saved row instead.

    Notes
    -----
    - This helper mirrors the same backend behaviour already used by the
      integration routes:
        - load the stored connection
        - validate the local fields
        - refresh proactively if the token is expired
    - Keeping that policy here prevents an ingest path from quietly drifting
      away from the route behaviour you already proved live.
    """
    # Start with the one stored connection row for this JobAdder account.
    #
    # The persistence layer treats `jobadder_account` as the natural key, so
    # this lookup is the ingest layer's anchor point for:
    # - loading credentials
    # - deciding whether the account has been connected at all
    # - deciding whether a refresh can happen without re-running the full OAuth
    #   approval flow
    stored_connection = get_jobadder_oauth_connection(jobadder_account)

    if stored_connection is None:
        raise JobAdderIngestPreparationError(
            "Stored JobAdder connection was not found.",
            stage="connection_load",
            details=[{"jobadder_account": jobadder_account}],
        )

    raw_access_token = stored_connection.get("access_token")
    raw_api_url = stored_connection.get("api_url")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    # Validate local storage before making any provider call.
    #
    # This distinction is useful:
    # - if local storage is incomplete, that is our problem
    # - if JobAdder rejects a well-formed request later, that is an upstream
    #   provider problem
    #
    # Keeping those two categories separate leads to much clearer debugging and
    # much clearer user-facing error messages later.
    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        raise JobAdderIngestPreparationError(
            "The stored JobAdder connection is missing an access token.",
            stage="connection_load",
            details=[{"jobadder_account": jobadder_account}],
        )

    if not isinstance(raw_api_url, str) or raw_api_url.strip() == "":
        raise JobAdderIngestPreparationError(
            "The stored JobAdder connection is missing an API URL.",
            stage="connection_load",
            details=[{"jobadder_account": jobadder_account}],
        )

    # Refresh proactively when the stored timing fields indicate the token is at
    # or beyond its safe lifetime.
    #
    # The intuition:
    # - a near-expiry token is a bad foundation for a multi-step ingest read
    # - it is better to refresh once upfront than to let the first or second
    #   provider call fail halfway through
    # - starting with a token we expect to be valid makes later behaviour much
    #   more predictable
    if is_jobadder_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        return _refresh_jobadder_connection_or_raise(
            jobadder_account=jobadder_account,
            refresh_token_value=raw_refresh_token,
        )

    # If we get here, the stored row is locally valid and the token timing
    # suggests it should still be usable.
    #
    # That does not guarantee the provider will accept the token forever, which
    # is why the later read helper still contains a one-time 401 refresh retry.
    # But it does mean this row is a reasonable starting point for the first
    # read attempt.
    return stored_connection


def _refresh_jobadder_connection_or_raise(
    *,
    jobadder_account: int,
    refresh_token_value: Any,
) -> dict[str, Any]:
    """
    Refresh the stored JobAdder token set and persist the replacement row.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used as the natural key for the stored
        connection.

    refresh_token_value : Any
        Raw refresh-token value read from the current stored connection row.

    Returns
    -------
    dict[str, Any]
        Updated stored connection row after a successful refresh and save.

    Raises
    ------
    JobAdderIngestPreparationError
        If the refresh token is missing, the provider refresh fails, or the
        refreshed token set cannot be saved.

    Example
    -------
    This helper is used in two situations:

    - before the first provider read, when the token is already expired
    - after a `401` response, when the token looked valid but JobAdder rejected
      it anyway

    Notes
    -----
    - This helper centralises the refresh-and-save sequence for the ingest
      orchestration layer.
    - That matters because the same sequence may be needed:
        - proactively before the first read
        - reactively after a 401 response
    """
    # A refresh flow cannot even begin without a non-empty refresh token.
    #
    # Keep this validation local and explicit:
    # - it stops us from sending a malformed refresh request
    # - it makes the resulting error clearly about local state, not the
    #   provider
    # - it produces a clearer debugging story for anyone reading logs later
    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        raise JobAdderIngestPreparationError(
            "The stored JobAdder connection is missing a refresh token.",
            stage="connection_refresh",
            details=[{"jobadder_account": jobadder_account}],
        )

    try:
        # Ask JobAdder for a fresh token set using the stored refresh token.
        #
        # This is the critical bridge that lets the integration keep working
        # without making the user repeat the full approval flow every time an
        # access token expires.
        refreshed_token_set = refresh_jobadder_access_token(
            refresh_token=refresh_token_value,
        )
    except JobAdderOAuthExchangeError as exc:
        details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

        if exc.status_code is not None:
            details.append({"provider_status_code": exc.status_code})

        if exc.provider_error is not None:
            details.append({"provider_error": exc.provider_error})

        if exc.provider_error_description is not None:
            details.append(
                {"provider_error_description": exc.provider_error_description}
            )

        raise JobAdderIngestPreparationError(
            "JobAdder token refresh failed.",
            stage="connection_refresh",
            status_code=exc.status_code,
            details=details,
        ) from exc

    try:
        # Persist the refreshed token set immediately.
        #
        # The point is not just to make the current read succeed. The point is
        # also to leave the database in a better state for the next read,
        # route, cron task, or background worker.
        refreshed_connection = save_jobadder_oauth_connection(refreshed_token_set)
    except (RuntimeError, ValueError) as exc:
        raise JobAdderIngestPreparationError(
            "JobAdder token refresh succeeded, but the refreshed connection could not be saved.",
            stage="connection_refresh",
            details=[
                {"jobadder_account": jobadder_account},
                {"reason": str(exc)},
            ],
        ) from exc

    refreshed_access_token = refreshed_connection.get("access_token")
    refreshed_api_url = refreshed_connection.get("api_url")

    # Re-validate the freshly saved row.
    #
    # That may feel defensive, but it is useful defensive code:
    # - the refresh HTTP request may have succeeded
    # - the save helper may have returned a row
    # - and yet that row could still be missing a field we need
    #
    # Failing early here keeps later code simpler, because every later step can
    # assume a refreshed connection is actually usable.
    if (
        not isinstance(refreshed_access_token, str)
        or refreshed_access_token.strip() == ""
    ):
        raise JobAdderIngestPreparationError(
            "The refreshed JobAdder connection is missing an access token.",
            stage="connection_refresh",
            details=[{"jobadder_account": jobadder_account}],
        )

    if not isinstance(refreshed_api_url, str) or refreshed_api_url.strip() == "":
        raise JobAdderIngestPreparationError(
            "The refreshed JobAdder connection is missing an API URL.",
            stage="connection_refresh",
            details=[{"jobadder_account": jobadder_account}],
        )

    # Return the saved refreshed row rather than the raw token set.
    #
    # That choice is subtle but important:
    # - downstream code wants the same shape as normal stored-connection reads
    # - the saved row contains the post-persistence truth
    # - returning one consistent shape keeps callers simpler
    return refreshed_connection


def _perform_jobadder_read_with_refresh_retry(
    *,
    jobadder_account: int,
    stored_connection: dict[str, Any],
    stage_name: str,
    provider_failure_message: str,
    read_callable: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Perform one JobAdder read and retry once with a refreshed token after 401.

    Parameters
    ----------
    jobadder_account : int
        JobAdder account identifier used for refresh saves and error details.

    stored_connection : dict[str, Any]
        Stored JobAdder connection row that already passed the initial local
        validation checks.

    stage_name : str
        Small label describing which orchestration stage is performing the read.

    provider_failure_message : str
        Safe human-readable message to use if the provider read ultimately
        fails.

    read_callable : Callable[..., dict[str, Any]]
        Small function that accepts `api_url` and `access_token` keyword
        arguments and performs one concrete provider read.

    Returns
    -------
    tuple[dict[str, Any], dict[str, Any]]
        Tuple containing:

        - the normalised read result returned by the lower-level API helper
        - the connection row that succeeded for that read

    Raises
    ------
    JobAdderIngestPreparationError
        If the provider read fails definitively or the refresh-and-retry path
        cannot recover from a 401.

    Example
    -------
    This helper wraps both:

    - candidate detail reads
    - candidate attachments reads

    so the caller does not need to duplicate the same:

    - try read
    - if 401, refresh
    - retry once
    - otherwise fail with structured context

    logic in multiple places.

    Notes
    -----
    - Only 401 gets special handling here.
    - That is intentional:
        - 401 often means the access token expired between reads
        - other statuses such as 404 or 429 are different classes of failure
          and should not trigger a blind refresh-and-retry loop
    """
    # Read the values we need out of the stored connection row once up front.
    #
    # This keeps the rest of the function readable and makes it obvious which
    # fields a provider read actually depends on.
    raw_access_token = stored_connection.get("access_token")
    raw_api_url = stored_connection.get("api_url")
    raw_refresh_token = stored_connection.get("refresh_token")

    try:
        # First attempt: use the current stored token as-is.
        #
        # In the common case, this should just work and keep the flow cheap and
        # direct.
        read_result = read_callable(
            api_url=raw_api_url,
            access_token=raw_access_token,
        )
    except JobAdderApiError as exc:
        if exc.status_code == 401:
            # A 401 is the one provider error we treat as potentially
            # recoverable here.
            #
            # The reasoning:
            # - the token may have expired between our local expiry check and
            #   the provider read
            # - the stored token may have gone stale for some provider-side
            #   reason
            # - a single refresh-and-retry is a practical way to recover from
            #   that class of failure
            refreshed_connection = _refresh_jobadder_connection_or_raise(
                jobadder_account=jobadder_account,
                refresh_token_value=raw_refresh_token,
            )

            refreshed_access_token = refreshed_connection.get("access_token")
            refreshed_api_url = refreshed_connection.get("api_url")

            # Retry exactly once.
            #
            # Why exactly once?
            # - one retry is enough to cover the meaningful token-expiry case
            # - more than one retry starts to hide real problems
            # - unbounded retries are especially dangerous in provider
            #   integrations because they can produce confusing partial failure
            #   behaviour and unnecessary upstream traffic
            try:
                read_result = read_callable(
                    api_url=refreshed_api_url,
                    access_token=refreshed_access_token,
                )
            except JobAdderApiError as retry_exc:
                details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

                if retry_exc.status_code is not None:
                    details.append({"provider_status_code": retry_exc.status_code})

                if retry_exc.retry_after is not None:
                    details.append({"retry_after_seconds": retry_exc.retry_after})

                if retry_exc.endpoint_url is not None:
                    details.append({"endpoint_url": retry_exc.endpoint_url})

                raise JobAdderIngestPreparationError(
                    provider_failure_message,
                    stage=stage_name,
                    status_code=retry_exc.status_code,
                    details=details,
                ) from retry_exc

            # Return both:
            # - the successful read result
            # - the refreshed connection row that made it succeed
            #
            # That second return value is what lets the orchestrator reuse the
            # winning connection for later reads in the same ingest run.
            return read_result, refreshed_connection

        # Any non-401 provider failure is treated as final here.
        #
        # That is a conscious tradeoff:
        # - `404` usually means the resource is missing
        # - `429` usually means throttling
        # - `500` may indicate a provider problem
        #
        # Refreshing the token does not meaningfully help those cases, so we
        # surface them with as much safe context as we can.
        details: list[dict[str, Any]] = [{"jobadder_account": jobadder_account}]

        if exc.status_code is not None:
            details.append({"provider_status_code": exc.status_code})

        if exc.retry_after is not None:
            details.append({"retry_after_seconds": exc.retry_after})

        if exc.endpoint_url is not None:
            details.append({"endpoint_url": exc.endpoint_url})

        raise JobAdderIngestPreparationError(
            provider_failure_message,
            stage=stage_name,
            status_code=exc.status_code,
            details=details,
        ) from exc

    # The first attempt succeeded, so the caller can keep using the same
    # connection row for subsequent reads in this orchestration run.
    return read_result, stored_connection


def _looks_like_resume_attachment(attachment: dict[str, Any]) -> bool:
    """
    Return whether one JobAdder attachment looks like a CV/resume.

    Parameters
    ----------
    attachment : dict[str, Any]
        One attachment object returned by JobAdder.

    Returns
    -------
    bool
        `True` when the attachment looks like a resume/CV candidate document.

    Example
    -------
    This helper returns `True` for attachment shapes like:

        {
            "type": "Resume",
            "category": "Resume",
            "fileName": "Roger Campbell - CV 2025.pdf",
            "fileType": "application/pdf",
        }

    and `False` for unrelated candidate attachments.

    Notes
    -----
    - This helper uses a pragmatic heuristic rather than one fragile single
      field.
    - In real tenant data, resume-related signals may appear in:
        - `type`
        - `category`
        - `fileName`
        - `fileType`
    - The goal here is not perfect semantic classification yet.
    - The goal is to identify the most likely candidate resume attachment for
      the next ingestion stage.
    """
    # Pull the relevant source fields out once and normalise them into a simple
    # lowercase comparison shape.
    #
    # Normalising early keeps the heuristic rules below readable and avoids
    # repeating the same string-safety logic in every condition.
    raw_type = attachment.get("type")
    raw_category = attachment.get("category")
    raw_file_name = attachment.get("fileName")
    raw_file_type = attachment.get("fileType")

    attachment_type = raw_type.strip().lower() if isinstance(raw_type, str) else ""
    attachment_category = (
        raw_category.strip().lower() if isinstance(raw_category, str) else ""
    )
    file_name = raw_file_name.strip().lower() if isinstance(raw_file_name, str) else ""
    file_type = raw_file_type.strip().lower() if isinstance(raw_file_type, str) else ""

    # Check the strongest explicit resume signals first.
    #
    # If JobAdder already labels the attachment as a resume in structured
    # fields, we should trust that before falling back to filename heuristics.
    if attachment_type == "resume":
        return True

    if attachment_category == "resume":
        return True

    # Fall back to filename hints next.
    #
    # This is less authoritative than structured provider labels, but real
    # tenant data often still follows human naming conventions such as:
    # - `Roger Campbell - CV 2025.pdf`
    # - `resume.pdf`
    if "cv" in file_name or "resume" in file_name:
        return True

    # The PDF + filename rule is intentionally a little redundant.
    #
    # That redundancy is not accidental. It makes the heuristic easier to tune
    # later if the client's data turns out to contain many PDF attachments that
    # are not CVs.
    if file_type == "application/pdf" and ("cv" in file_name or "resume" in file_name):
        return True

    return False


def _select_latest_resume_attachment(
    attachments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Select the latest likely-resume attachment from a filtered attachment list.

    Parameters
    ----------
    attachments : list[dict[str, Any]]
        Attachments that have already passed the resume-likeliness filter.

    Returns
    -------
    dict[str, Any] | None
        Latest likely resume attachment, or `None` when no resume-like
        attachment exists.

    Example
    -------
    If a candidate has three resume-like attachments from different dates, this
    helper returns the newest one according to the `createdAt` timestamp, with
    attachment ID used as a fallback tie-breaker.

    Notes
    -----
    - We prefer the latest attachment because candidates often upload multiple
      CV revisions over time.
    - We sort primarily by `createdAt` descending.
    - When timestamps are equal or missing, we use the numeric attachment ID as
      a stable fallback tie-breaker where possible.
    """
    # Treat "no candidate resumes found" as a normal outcome, not an error.
    #
    # This matters because a missing resume should not crash the whole ingest
    # preparation step. The caller may still want:
    # - the candidate identity data
    # - the raw attachments list
    # - a later fallback to Dropbox or another file source
    if len(attachments) == 0:
        return None

    # Sort in descending order so the first element is the newest/best match.
    #
    # Using `sorted(...)[0]` instead of a more compact expression is a little
    # more verbose, but it keeps the control flow easy to understand for anyone
    # who is still getting comfortable with Python sorting behaviour.
    return sorted(
        attachments,
        key=_resume_attachment_sort_key,
        reverse=True,
    )[0]


def _resume_attachment_sort_key(attachment: dict[str, Any]) -> tuple[datetime, int]:
    """
    Build a stable sort key for selecting the latest resume attachment.

    Parameters
    ----------
    attachment : dict[str, Any]
        One candidate resume attachment.

    Returns
    -------
    tuple[datetime, int]
        Sort key consisting of:
        - parsed `createdAt` timestamp
        - numeric attachment ID fallback

    Example
    -------
    A more recent attachment such as:

        {"createdAt": "2026-04-20T10:00:00Z", "attachmentId": 21091489}

    sorts after an older one such as:

        {"createdAt": "2025-12-01T09:00:00Z", "attachmentId": 20953945}

    Notes
    -----
    - When `createdAt` is missing or invalid, this helper falls back to the
      Unix epoch rather than raising.
    - That keeps the selector deterministic even on messy source data.
    """
    # Build the two pieces of the sort key separately so the fallback logic is
    # obvious.
    #
    # The intended ranking is:
    # 1. newer timestamps win
    # 2. if timestamps are missing or tied, higher attachment IDs win
    #
    # That is not a perfect universal truth, but it is a pragmatic and
    # explainable rule for this stage of the integration.
    created_at = _parse_optional_datetime(attachment.get("createdAt"))
    attachment_id = _safe_int(attachment.get("attachmentId")) or 0

    return created_at or datetime.fromtimestamp(0, tz=timezone.utc), attachment_id


def _build_resume_source_reference(
    latest_resume: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Build a smaller internal resume-source reference from one attachment object.

    Parameters
    ----------
    latest_resume : dict[str, Any] | None
        Selected latest resume attachment, if one was found.

    Returns
    -------
    dict[str, Any] | None
        Smaller internal resume-source reference, or `None` when no resume
        attachment was found.

    Example
    -------
    A successful result might look like:

        {
            "provider": "jobadder_attachment",
            "external_id": 21091489,
            "file_name": "Roger Campbell - CV 2025.pdf",
            "mime_type": "application/pdf",
            "category": "Resume",
            "type": "Resume",
            "created_at": "2026-04-20T10:00:00Z",
            "self_link": "https://eu2api.jobadder.com/v2/candidates/.../attachments/21091489",
        }

    Notes
    -----
    - The top-level orchestration result already keeps the full attachment list.
    - This helper exists so downstream ingestion steps have one smaller, more
      stable structure to work with.
    - That is the beginning of a provider-agnostic document-source contract
      that can later support Dropbox or other file providers.
    """
    # Keep the absence case explicit.
    #
    # A `None` return here tells later code:
    # - no resume attachment was identified in JobAdder
    # - another source such as Dropbox may need to be consulted later
    # - the candidate ingest shell is still valid, just incomplete on the
    #   document side
    if latest_resume is None:
        return None

    # Pull the link dictionary out carefully because source systems often treat
    # link containers as optional.
    #
    # Normalising that here means later code can rely on the smaller reference
    # shape instead of repeatedly checking whether `links` was missing or had an
    # unexpected type.
    raw_links = latest_resume.get("links")
    links = raw_links if isinstance(raw_links, dict) else {}

    return {
        "provider": "jobadder_attachment",
        "external_id": latest_resume.get("attachmentId"),
        "file_name": latest_resume.get("fileName"),
        "mime_type": latest_resume.get("fileType"),
        "category": latest_resume.get("category"),
        "type": latest_resume.get("type"),
        "created_at": latest_resume.get("createdAt"),
        "self_link": links.get("self"),
    }


def _build_cleaned_candidate_note_items(
    note_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build a smaller candidate-notes bundle that preserves both raw and cleaned text.

    Parameters
    ----------
    note_items : list[dict[str, Any]]
        Raw note objects returned by the JobAdder notes helper.

    Returns
    -------
    list[dict[str, Any]]
        Smaller note dictionaries containing the fields most useful for later
        ingestion and LLM work.

    Example
    -------
    A raw JobAdder note object such as:

        {
            "noteId": "...",
            "type": "Email Reply",
            "text": "Hi Roger,Ã‚\\r\\n\\r\\nThanks...",
            "createdAt": "2026-04-17T12:01:11Z",
        }

    becomes something closer to:

        {
            "note_id": "...",
            "type": "Email Reply",
            "created_at": "2026-04-17T12:01:11Z",
            "updated_at": None,
            "text": "Hi Roger,Ã‚\\r\\n\\r\\nThanks...",
            "cleaned_text": "Hi Roger,\\n\\nThanks...",
        }

    Notes
    -----
    - This helper deliberately keeps both raw and cleaned text.
    - Raw text remains useful for audit/debug work.
    - Cleaned text is the likely input for later extraction and reasoning.
    """

    cleaned_items: list[dict[str, Any]] = []

    # Build a smaller, more stable note shape for downstream use.
    #
    # The raw JobAdder note payload may contain many fields, but later stages
    # usually care most about:
    # - a stable note ID
    # - note type
    # - timestamps
    # - raw note text
    # - cleaned note text
    for note in note_items:
        raw_text = note.get("text")
        note_text = raw_text if isinstance(raw_text, str) else ""

        cleaned_items.append(
            {
                "note_id": note.get("noteId"),
                "type": note.get("type"),
                "created_at": note.get("createdAt"),
                "updated_at": note.get("updatedAt"),
                "text": note_text,
                "cleaned_text": clean_jobadder_note_text(note_text),
            }
        )

    return cleaned_items


def _parse_optional_datetime(value: Any) -> datetime | None:
    """
    Convert a source-system timestamp value into a UTC datetime when possible.

    Parameters
    ----------
    value : Any
        Raw value from a JobAdder payload.

    Returns
    -------
    datetime | None
        Parsed UTC datetime when successful, otherwise `None`.

    Example
    -------
    Input values such as:

        "2026-04-20T10:02:24Z"

    become timezone-aware UTC datetimes, while blank or malformed values become
    `None`.
    """
    # Reject non-strings immediately.
    #
    # Being strict here is useful because this helper is about safe optional
    # parsing, not about guessing every possible source-system shape.
    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    try:
        # JobAdder timestamps commonly use `Z` for UTC.
        #
        # `datetime.fromisoformat(...)` understands `+00:00` directly, so we
        # normalise the suffix before parsing.
        parsed = datetime.fromisoformat(cleaned_value.replace("Z", "+00:00"))
    except ValueError:
        return None

    # Always return a timezone-aware UTC datetime.
    #
    # That avoids a very common class of bugs where naive and aware datetimes
    # get mixed later in comparisons or sorting.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _safe_int(value: Any) -> int | None:
    """
    Convert a source-system value into an integer when safe to do so.

    Parameters
    ----------
    value : Any
        Raw value from a JobAdder payload.

    Returns
    -------
    int | None
        Parsed integer value, or `None` when the conversion is not safe.

    Example
    -------
    The helper accepts values like:

    - `123`
    - `123.0`
    - `"123"`

    and returns `123`, while values like:

    - `""`
    - `"abc"`
    - `None`

    return `None`.
    """
    # Exclude booleans first.
    #
    # In Python, `bool` is a subclass of `int`, so without this guard:
    # - `True` would become `1`
    # - `False` would become `0`
    #
    # That would be technically valid Python but semantically wrong for source
    # identifiers such as attachment IDs.
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    # Accept floats pragmatically because some loose source payloads or test
    # fixtures may represent whole numbers as `123.0`.
    #
    # This is a convenience, not a claim that floats are ideal identifier
    # types.
    if isinstance(value, float):
        return int(value)

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    try:
        return int(cleaned_value)
    except ValueError:
        return None


__all__ = [
    "JobAdderIngestPreparationError",
    "build_jobadder_candidate_ingest_shell",
    "download_latest_jobadder_resume_for_candidate",
    "extract_latest_jobadder_resume_text_for_candidate",
]
