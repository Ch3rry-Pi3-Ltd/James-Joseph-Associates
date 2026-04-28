"""
JobAdder candidate-ingest prepatation helpers.

This module sites one level above the raw JobAdder API read helpers.

Why this module exists
----------------------
We already have lower-level pieces that can:

- load the stored JobAdder OAuth connection from Postgrest
- refresh an expired JobAdder access token
- fetch one candidate from JobAdder
- fetch other JobAdder resources through small read-only service helpers

The next problem is different:

    "Can the backend taken several JobAdder reads and turn them into one
    internal ingest-ready payload shell?"

That is what this module is for.

Scope of this first version
---------------------------
This module intentionally does not do everything.

It does not:

- run an LLM
- parse PDF text
- write canonical candidate records
- write document records
- talk to Dropbox
- talk to Azure Blob storage

It only prepares the raw source-side materials that later ingestion stages
will need.

Specifically, given a JobAdder account ID and a candidate ID, this module:

1. loads the stored JobAdder OAuth connection
2. makes sure the access token is usuable
3. refreshes the token if needed
4. fetches the full candidate record
5. fetches the candidate's attachment list
6. identifies the latest likely-resume attachment
7. returns one normalised internal dictionary

Why start here
--------------
This is the right first orchestration layer because it separates two concerns:

- raw provider transport details
- ingest preparation decisions

The lower-level `backend.services.jobadder_api` module should stay focus on
single endpoint reads.

This module should stay focused on combining those reads into something the rest
of the backend can use.

In plain language:

- this module answers the question:

    "Can we get one candidate and their latest likely CV reference out of
    JobAdder in one clean step?"

- it does not yet download the CV binary
- it does not yet parse the CV
- it does not yet create or update canonical records
"""

from datetime import datetime, timezone
from backend.db.jobadder_oauth import (
    get_jobadder_oauth_connection,
    save_jobadder_oauth_connection,
)
from backend.services.jobadder_api import (
    JobAdderApiError,
    fetch_jobadder_candidate_attachments,
    fetch_job_adder_candidate_detail,
)
from backend.services.jobadder_oauth import (
    JobAdderOAuthExchangeError,
    is_jobadder_access_token_expired,
    refresh_jobadder_access_token,
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

    status_code : int | None
        Upstream HTTP status code when the failure came from JobAdder.

    details : list[dict[str, Any]]
        Small safe structured details that can help route handlers, logs, or
        tests explain what happened without leaking secrets.

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
    Build one internal JobAdder candidate-ingest prepatation payload.

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
        - the latest likely-resume attachment reference, if found
        - a smaller ingest-ready shell for downstream stages

    Raises
    ------
    ValueError
        If the JobAdder account ID or candidate ID is invalid.

    JobAdderIngestPreparationError
        If the stored JobAdder connection cannot be loaded, refreshed, or used
        to read the required JobAdder resource safely.

    Notes
    -----
    - This helper is the first orchestration layer for JobAdder ingestion work.
    - It intentionally stops before downloading the resume file itself.
    - That boundary matters because file retrieval, PDF parsing, and LLM-based
      extraction will likely evolve separately from the provider record reads.

    In plain language:

    - get the candidate
    - get their attachments
    - pick the most likely latest CV
    - return one clean bundle for the next ingestion step
    """
    
    if jobadder_account < 1:
        raise ValueError("JobAdder jobadder_account must be at least 1.")
    
    if candidate_id < 1:
        raise ValueError("JobAdder candidate_id must be at least 1.")
    
    stored_connection = _load_jobadder_connection_for_ingest(
        jobadder_account=jobadder_account,
    )

    # Use the same successful connection for both reads
    #   - If the first read forces a refresh, we want the second read to reused
    #     the refreshed token and API URL instead of repeating stale values.
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

    attachment_items = candidate_attachments.get("items", [])
    resume_attachments = [
        attachment
        for attachment in attachment_items
        if _looks_like_resume_attachment(attachment)
    ]
    latest_resume = _select_latest_resume_attachment(resume_attachments)

    candidate_payload = candidate_detail["candidate"]
    api_url = successful_connection["api_url"]
    jobadder_instance = successful_connection.get("jobadder_instance")

    # The top-level return includes two layers on purpose:
    #
    #   1. rich source payloads:
    #       - full candidate object
    #       - full attachment list
    #
    #   2. smaller ingest shell:
    #       - the minimum structured metadata that downstream ingestion steps can
    #         rely on without re-reading the entire source payload shape
    #
    # That split keeps the early experimentation easy while still encouraging a
    # stable internal contract to emerge.
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
        "latest_resume": latest_resume,
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": candidate_id,
            "source_updated_at": candidate_payload.get("updatedAt"),
            "core_identity": {
                "first_name": candidate_payload.get("firstName"),
                "last_name": candidate_payload.get("lastName"),
                "email": candidate_payload.get("email"),
                "mobile": candidate_payload.get("mobile"),
            },
            "jobadder_metadata": {
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
            "resume_source": _build_resume_source_reference(latest_resume),
        },
    }

def _load_jobadder_connection_for_ingest(*, jobadder_account: int) -> dict[str, Any]:
    """
    Load one stored JobAdder OAuth connection and make sure it is read-ready.

    Parameters
    ----------
    jobadder_account : int
        Jobadder account identifier used to locate the stored OAuth connection.

    Returns
    -------
    dict[str, Any]
        Stored JobAdder connection row that contains at least a usable
        `access_token` and `api_url`.

    Raises
    ------
    JobAdderIngestPrepatationError
        If the stored connection does not exist, is missing required fields, or
        requires a refresh that cannot be completed.

    Notes
    -----
    - this helper mirrors the same backend bahaviour already used by the
      integration routes:
        - load the stored connection
        - validate the local fields
        - refresh proactively if the token is expired
    - Keeping that policy here prevents an ingest path from quietly drifting
      away from the route behaviour you already proved live.
    """

    stored_connection = get_jobadder_oauth_connection(jobadder_account)

    if stored_connection is None:
        raise JobAdderIngestPreparationError(
            "Stored JobAdder connection was not found.",
            stage="connection_load",
            details=[
                {
                    "jobadder_account": jobadder_account
                }
            ],
        )
    
    raw_access_token = stored_connection.get("access_token")
    raw_api_url = stored_connection.get("api_url")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(raw_access_token, str) or raw_access_token.string() == "":
        raise JobAdderIngestPreparationError(
            "The stored JobAdder connection is missing an access token.",
            stage="connection_load",
            details=[
                {
                    "jobadder_account": jobadder_account
                }
            ],
        )
    
    if not isinstance(raw_api_url, str) or raw_api_url.strip() == "":
        raise JobAdderIngestPreparationError(
            "The stored JobAdder connection is missing an API URL.",
            stage="connect_load",
            details=[
                {
                    "jobadder_account": jobadder_account
                }
            ],
        )
    
    # Refresh proactively when the stored timing fields indicate the token is at
    # or beyond its safe lifetime.
    #   - This avoids avoidable 401s and keeps ingestion work deterministic:
    #     
    #     - start with a token that is expected to be valid, rather than immediately
    #       gambling on a near-expiry access token.
    if is_jobadder_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        return _refresh_jobadder_connection_or_raise(
            jobadder_account=jobadder_account,
            refresh_token_value=raw_refresh_token,
        )

    return stored_connection
