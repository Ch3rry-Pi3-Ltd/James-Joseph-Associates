"""
Unit tests for JobAdder ingest-preparation helpers.

This module tests the orchestration layer in
`backend.services.jobadder_ingest`.

Why these tests matter
----------------------
The lower-level JobAdder integration layers already prove smaller behaviours:

- OAuth URL building
- token exchange
- token refresh
- candidate reads
- attachments reads

This module tests the next layer up:

    "Can the backend combine those smaller pieces into one clean
    candidate-ingest preparation flow?"

That orchestration matters because it is where the backend starts making
business decisions such as:

- when to refresh a token before reads
- when to retry after a 401
- how to identify resume-like attachments
- how to select the latest likely CV
- how to shape the internal ingest shell

Scope of these tests
--------------------
These tests intentionally do not:

- call the real JobAdder API
- hit the real database
- download any real CV files
- run any LLM extraction

Instead, they isolate the local Python orchestration logic by replacing:

- stored-connection reads
- refresh helpers
- provider read callables

with small fake functions.

Example
-------
A typical orchestration call under test looks like:

    build_jobadder_candidate_ingest_shell(
        jobadder_account=2236,
        candidate_id=16496678,
    )

and should return a structure containing:

- the full candidate payload
- the attachments payload
- the selected latest resume attachment
- a smaller ingest shell for later stages

In plain language:

- this module answers the question:

    "Can we reliably prepare one candidate + CV source bundle
    before CV download and parsing begin?"

- it only tests local orchestration behaviour
- it does not test external systems directly
"""

import pytest

import backend.services.jobadder_ingest as jobadder_ingest
from backend.services.jobadder_api import JobAdderApiError
from backend.services.jobadder_ingest import (
    JobAdderIngestPreparationError,
    build_jobadder_candidate_ingest_shell,
    download_latest_jobadder_resume_for_candidate,
    extract_latest_jobadder_resume_text_for_candidate,
)
from backend.services.resume_text import ResumeTextExtractionError


def test_build_jobadder_candidate_ingest_shell_returns_candidate_and_latest_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the public orchestration helper returns the full candidate
    bundle and correctly selects the latest resume attachment.

    Notes
    -----
    - This test replaces the lower-level connection and provider-read helpers
      with small fake functions.
    - That keeps the test focused on the orchestration logic in
      `build_jobadder_candidate_ingest_shell(...)` itself.
    - The important behaviour here is not just "did it return something?" but:
        - did it preserve the candidate payload?
        - did it preserve the attachments list?
        - did it identify only the resume-like attachments?
        - did it pick the newest one?

    Example
    -------
    We simulate a candidate with multiple attachments, including:

    - an older resume PDF
    - a newer resume PDF
    - a non-resume document

    and confirm the helper picks the newer resume.

    In plain language:

    - pretend the candidate read succeeded
    - pretend the attachment read succeeded
    - confirm the final result contains the expected latest CV reference
    """

    fake_connection = {
        "access_token": "stored-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    fake_candidate_detail = {
        "candidate": {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "mobile": "07934 890 708",
            "status": "Active",
            "skillTags": ["machine learning", "applied econometrics"],
            "createdAt": "2025-07-10T16:01:10Z",
            "updatedAt": "2026-04-20T10:02:24Z",
        }
    }

    fake_candidate_attachments = {
        "items": [
            {
                "attachmentId": 20953945,
                "type": "Resume",
                "category": "Resume",
                "fileName": "Roger Campbell - CV 2024.pdf",
                "fileType": "application/pdf",
                "createdAt": "2025-12-01T09:00:00Z",
                "links": {
                    "self": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/20953945"
                },
            },
            {
                "attachmentId": 21091489,
                "type": "Resume",
                "category": "Resume",
                "fileName": "Roger Campbell - CV 2025.pdf",
                "fileType": "application/pdf",
                "createdAt": "2026-04-20T10:00:00Z",
                "links": {
                    "self": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
                },
            },
            {
                "attachmentId": 22000000,
                "type": "Document",
                "category": "Other",
                "fileName": "Interview Notes.pdf",
                "fileType": "application/pdf",
                "createdAt": "2026-04-21T10:00:00Z",
                "links": {
                    "self": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/22000000"
                },
            },
        ],
        "attachment_count": 3,
        "links": {"self": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments"},
    }
    fake_candidate_notes = {
        "notes": [
            {
                "noteId": "note-1",
                "type": "Email Reply",
                "text": "Hi Roger,Ã‚\r\n\r\nThanks again...",
                "createdAt": "2026-04-21T10:05:00Z",
                "updatedAt": "2026-04-21T10:05:00Z",
            }
        ],
        "note_count": 1,
        "total_count": 1,
        "links": {"self": "https://eu2api.jobadder.com/v2/candidates/16496678/notes"},
    }

    captured_stage_names: list[str] = []

    def fake_load_connection(*, jobadder_account: int) -> dict[str, object]:
        assert jobadder_account == 2236
        return fake_connection

    def fake_read_with_retry(
        *,
        jobadder_account: int,
        stored_connection: dict[str, object],
        stage_name: str,
        provider_failure_message: str,
        read_callable,
    ) -> tuple[dict[str, object], dict[str, object]]:
        captured_stage_names.append(stage_name)

        assert jobadder_account == 2236
        assert stored_connection == fake_connection

        if stage_name == "candidate_read":
            return fake_candidate_detail, fake_connection

        if stage_name == "attachments_read":
            return fake_candidate_attachments, fake_connection

        if stage_name == "notes_read":
            return fake_candidate_notes, fake_connection

        raise AssertionError(f"Unexpected stage_name: {stage_name}")

    monkeypatch.setattr(
        jobadder_ingest,
        "_load_jobadder_connection_for_ingest",
        fake_load_connection,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_perform_jobadder_read_with_refresh_retry",
        fake_read_with_retry,
    )

    result = build_jobadder_candidate_ingest_shell(
        jobadder_account=2236,
        candidate_id=16496678,
    )

    assert captured_stage_names == ["candidate_read", "attachments_read", "notes_read"]

    assert result["source_system"] == "jobadder"
    assert result["jobadder_account"] == 2236
    assert result["jobadder_instance"] == "eu2"
    assert result["api_url"] == "https://eu2api.jobadder.com/v2/"
    assert result["source_candidate_id"] == 16496678

    assert result["candidate"] == fake_candidate_detail["candidate"]

    assert result["attachments"]["attachment_count"] == 3
    assert result["attachments"]["resume_attachment_count"] == 2
    assert result["attachments"]["items"] == fake_candidate_attachments["items"]
    assert result["notes"]["note_count"] == 1
    assert result["notes"]["total_count"] == 1
    assert result["notes"]["items"] == fake_candidate_notes["notes"]
    assert result["notes"]["cleaned_items"] == [
        {
            "note_id": "note-1",
            "type": "Email Reply",
            "created_at": "2026-04-21T10:05:00Z",
            "updated_at": "2026-04-21T10:05:00Z",
            "text": "Hi Roger,Ã‚\r\n\r\nThanks again...",
            "cleaned_text": "Hi Roger,\n\nThanks again...",
        }
    ]

    assert result["latest_resume"]["attachmentId"] == 21091489
    assert result["latest_resume"]["fileName"] == "Roger Campbell - CV 2025.pdf"

    assert result["ingest_shell"]["source_system"] == "jobadder"
    assert result["ingest_shell"]["source_candidate_id"] == 16496678
    assert result["ingest_shell"]["source_updated_at"] == "2026-04-20T10:02:24Z"

    assert result["ingest_shell"]["core_identity"] == {
        "first_name": "Roger",
        "last_name": "Campbell",
        "email": "the_rfc@hotmail.co.uk",
        "mobile": "07934 890 708",
    }

    assert result["ingest_shell"]["jobadder_metadata"]["status"] == "Active"
    assert result["ingest_shell"]["jobadder_metadata"]["skill_tags"] == [
        "machine learning",
        "applied econometrics",
    ]
    assert result["ingest_shell"]["candidate_notes"] == [
        {
            "note_id": "note-1",
            "type": "Email Reply",
            "created_at": "2026-04-21T10:05:00Z",
            "updated_at": "2026-04-21T10:05:00Z",
            "text": "Hi Roger,Ã‚\r\n\r\nThanks again...",
            "cleaned_text": "Hi Roger,\n\nThanks again...",
        }
    ]

    assert result["ingest_shell"]["resume_source"] == {
        "provider": "jobadder_attachment",
        "external_id": 21091489,
        "file_name": "Roger Campbell - CV 2025.pdf",
        "mime_type": "application/pdf",
        "category": "Resume",
        "type": "Resume",
        "created_at": "2026-04-20T10:00:00Z",
        "self_link": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
    }


def test_build_jobadder_candidate_ingest_shell_returns_none_when_no_resume_like_attachment_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the public orchestration helper treats "no resume found" as a
    normal outcome rather than an error.

    Notes
    -----
    - This is a realistic case.
    - A candidate may exist in JobAdder without a CV attachment.
    - The ingest-preparation step should still return useful candidate data and
      attachment metadata rather than crashing.

    Example
    -------
    We simulate a candidate whose attachments are things like:

    - notes
    - miscellaneous documents
    - non-resume files

    and confirm the result contains:
    - `latest_resume = None`
    - `resume_source = None`

    In plain language:

    - pretend attachments exist
    - but none of them look like a CV
    - confirm the helper still returns a valid ingest bundle
    """

    fake_connection = {
        "access_token": "stored-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    fake_candidate_detail = {
        "candidate": {
            "candidateId": 13816907,
            "firstName": "Pavel",
            "lastName": "Voronkin",
            "email": "promethean.vp@gmail.com",
            "mobile": "+44 7503 619821",
            "updatedAt": "2025-09-05T07:36:44Z",
        }
    }

    fake_candidate_attachments = {
        "items": [
            {
                "attachmentId": 1001,
                "type": "Document",
                "category": "Other",
                "fileName": "Interview Notes.txt",
                "fileType": "text/plain",
                "createdAt": "2026-01-01T10:00:00Z",
                "links": {"self": "https://example.com/attachments/1001"},
            }
        ],
        "attachment_count": 1,
        "links": {},
    }
    fake_candidate_notes = {
        "notes": [],
        "note_count": 0,
        "total_count": 0,
        "links": {},
    }

    def fake_load_connection(*, jobadder_account: int) -> dict[str, object]:
        assert jobadder_account == 2236
        return fake_connection

    def fake_read_with_retry(
        *,
        jobadder_account: int,
        stored_connection: dict[str, object],
        stage_name: str,
        provider_failure_message: str,
        read_callable,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if stage_name == "candidate_read":
            return fake_candidate_detail, fake_connection

        if stage_name == "attachments_read":
            return fake_candidate_attachments, fake_connection

        if stage_name == "notes_read":
            return fake_candidate_notes, fake_connection

        raise AssertionError(f"Unexpected stage_name: {stage_name}")

    monkeypatch.setattr(
        jobadder_ingest,
        "_load_jobadder_connection_for_ingest",
        fake_load_connection,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_perform_jobadder_read_with_refresh_retry",
        fake_read_with_retry,
    )

    result = build_jobadder_candidate_ingest_shell(
        jobadder_account=2236,
        candidate_id=13816907,
    )

    assert result["latest_resume"] is None
    assert result["attachments"]["resume_attachment_count"] == 0
    assert result["notes"]["note_count"] == 0
    assert result["notes"]["cleaned_items"] == []
    assert result["ingest_shell"]["candidate_notes"] == []
    assert result["ingest_shell"]["resume_source"] is None


def test_load_jobadder_connection_for_ingest_refreshes_proactively_when_token_is_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the connection loader refreshes the stored JobAdder connection
    before any provider read when the stored token is already expired.

    Notes
    -----
    - This tests the proactive refresh path directly, rather than the whole
      public orchestration helper.
    - That keeps the test focused on one policy decision:
        - should this helper return the stored row as-is?
        - or should it refresh first?

    Example
    -------
    We simulate:
    - a stored connection row
    - an expiry check that says "expired"
    - a refresh helper that returns a refreshed connection

    and confirm the refreshed row is what the helper returns.

    In plain language:

    - pretend the stored token is expired
    - confirm the helper refreshes before any read starts
    """

    stored_connection = {
        "access_token": "old-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "obtained_at": "2026-04-28T10:00:00Z",
        "expires_in_seconds": 3600,
    }

    refreshed_connection = {
        "access_token": "new-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "obtained_at": "2026-04-29T10:00:00Z",
        "expires_in_seconds": 3600,
    }

    captured_refresh: dict[str, object] = {}

    def fake_get_connection(jobadder_account: int) -> dict[str, object]:
        assert jobadder_account == 2236
        return stored_connection

    def fake_is_expired(*, obtained_at, expires_in_seconds) -> bool:
        assert obtained_at == "2026-04-28T10:00:00Z"
        assert expires_in_seconds == 3600
        return True

    def fake_refresh_connection(*, jobadder_account: int, refresh_token_value: object):
        captured_refresh["jobadder_account"] = jobadder_account
        captured_refresh["refresh_token_value"] = refresh_token_value
        return refreshed_connection

    monkeypatch.setattr(
        jobadder_ingest,
        "get_jobadder_oauth_connection",
        fake_get_connection,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "is_jobadder_access_token_expired",
        fake_is_expired,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_refresh_jobadder_connection_or_raise",
        fake_refresh_connection,
    )

    result = jobadder_ingest._load_jobadder_connection_for_ingest(
        jobadder_account=2236,
    )

    assert result == refreshed_connection
    assert captured_refresh == {
        "jobadder_account": 2236,
        "refresh_token_value": "stored-refresh-token",
    }


def test_load_jobadder_connection_for_ingest_raises_when_connection_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the connection loader raises a clear local error when no stored
    JobAdder OAuth connection exists for the requested account.

    Example
    -------
    If the database returns `None` for account `2236`, this helper should raise
    `JobAdderIngestPreparationError` with:
    - `stage = "connection_load"`
    - details containing the account ID

    In plain language:

    - pretend no stored connection exists
    - confirm the helper raises a clear local error
    """

    monkeypatch.setattr(
        jobadder_ingest,
        "get_jobadder_oauth_connection",
        lambda jobadder_account: None,
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        jobadder_ingest._load_jobadder_connection_for_ingest(jobadder_account=2236)

    error = exc_info.value

    assert str(error) == "Stored JobAdder connection was not found."
    assert error.stage == "connection_load"
    assert error.details == [{"jobadder_account": 2236}]


def test_load_jobadder_connection_for_ingest_raises_when_access_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the connection loader rejects a malformed stored connection row
    before any provider read begins.

    Notes
    -----
    - This is a local persistence validation test.
    - It is not about provider behaviour.
    - The helper should fail before it gets anywhere near JobAdder if the stored
      row is incomplete.

    Example
    -------
    We simulate a stored row with:
    - blank `access_token`
    - valid `api_url`

    and confirm the helper raises `connection_load`.

    In plain language:

    - pretend the database row is incomplete
    - confirm the helper fails locally and clearly
    """

    monkeypatch.setattr(
        jobadder_ingest,
        "get_jobadder_oauth_connection",
        lambda jobadder_account: {
            "access_token": "   ",
            "refresh_token": "stored-refresh-token",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "obtained_at": "2026-04-28T10:00:00Z",
            "expires_in_seconds": 3600,
        },
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        jobadder_ingest._load_jobadder_connection_for_ingest(jobadder_account=2236)

    error = exc_info.value

    assert str(error) == "The stored JobAdder connection is missing an access token."
    assert error.stage == "connection_load"
    assert error.details == [{"jobadder_account": 2236}]


def test_perform_jobadder_read_with_refresh_retry_refreshes_once_after_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the shared read helper performs one refresh-and-retry cycle when
    the first provider read fails with `401`.

    Notes
    -----
    - This is the most important recovery path in the orchestration layer.
    - The whole point is:
        - first read fails with expired/stale token
        - refresh succeeds
        - retry succeeds
    - The helper should then return:
        - the successful read result
        - the refreshed connection row

    Example
    -------
    We simulate:
    - first read -> `401`
    - refresh helper -> refreshed connection
    - second read -> success

    In plain language:

    - pretend the first token is rejected
    - pretend refresh succeeds
    - confirm the helper retries exactly once and returns success
    """

    stored_connection = {
        "access_token": "old-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    refreshed_connection = {
        "access_token": "new-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    captured_attempts: list[tuple[str, str]] = []

    def fake_refresh_connection(*, jobadder_account: int, refresh_token_value: object):
        assert jobadder_account == 2236
        assert refresh_token_value == "stored-refresh-token"
        return refreshed_connection

    def fake_read_callable(*, api_url: str, access_token: str) -> dict[str, object]:
        captured_attempts.append((api_url, access_token))

        if access_token == "old-access-token":
            raise JobAdderApiError(
                "JobAdder candidate detail read failed.",
                status_code=401,
                endpoint_url=f"{api_url.rstrip('/')}/candidates/16496678",
            )

        return {"candidate": {"candidateId": 16496678}}

    monkeypatch.setattr(
        jobadder_ingest,
        "_refresh_jobadder_connection_or_raise",
        fake_refresh_connection,
    )

    result, winning_connection = jobadder_ingest._perform_jobadder_read_with_refresh_retry(
        jobadder_account=2236,
        stored_connection=stored_connection,
        stage_name="candidate_read",
        provider_failure_message="JobAdder candidate detail read failed.",
        read_callable=fake_read_callable,
    )

    assert result == {"candidate": {"candidateId": 16496678}}
    assert winning_connection == refreshed_connection
    assert captured_attempts == [
        ("https://eu2api.jobadder.com/v2/", "old-access-token"),
        ("https://eu2api.jobadder.com/v2/", "new-access-token"),
    ]


def test_perform_jobadder_read_with_refresh_retry_raises_for_non_401_provider_failure() -> None:
    """
    Verify that the shared read helper does not try to refresh on non-401
    provider failures.

    Notes
    -----
    - A `404`, `429`, or `500` is not the same thing as "token probably
      expired".
    - This helper should only attempt automatic recovery for the one case where
      a refresh is likely to help: `401`.

    Example
    -------
    We simulate a `404` candidate read failure and confirm the helper raises
    `JobAdderIngestPreparationError` directly without trying to refresh.

    In plain language:

    - pretend the provider returned a non-401 error
    - confirm the helper surfaces that as a final failure
    """

    stored_connection = {
        "access_token": "stored-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    def fake_read_callable(*, api_url: str, access_token: str) -> dict[str, object]:
        raise JobAdderApiError(
            "JobAdder candidate detail read failed.",
            status_code=404,
            endpoint_url="https://eu2api.jobadder.com/v2/candidates/99999999",
            response_body={"message": "Not found"},
        )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        jobadder_ingest._perform_jobadder_read_with_refresh_retry(
            jobadder_account=2236,
            stored_connection=stored_connection,
            stage_name="candidate_read",
            provider_failure_message="JobAdder candidate detail read failed.",
            read_callable=fake_read_callable,
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate detail read failed."
    assert error.stage == "candidate_read"
    assert error.status_code == 404
    assert error.details == [
        {"jobadder_account": 2236},
        {"provider_status_code": 404},
        {"endpoint_url": "https://eu2api.jobadder.com/v2/candidates/99999999"},
    ]


def test_perform_jobadder_read_with_refresh_retry_retries_once_for_transport_failure() -> None:
    """
    Verify that the shared read helper retries once when the provider helper
    reports a transport-level connectivity failure.

    Notes
    -----
    - This retry is intentionally different from the 401 refresh path.
    - No token refresh should happen here.
    - The helper should simply retry the same read once because no usable HTTP
      response was received on the first attempt.

    Example
    -------
    We simulate:

    - the first read raising `JobAdderApiError("Could not reach the JobAdder API.")`
    - the second read succeeding

    In plain language:

    - pretend the network blipped once
    - confirm the helper retries once and then returns success
    """

    stored_connection = {
        "access_token": "stored-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }
    captured_attempts: list[tuple[str, str]] = []

    def fake_read_callable(*, api_url: str, access_token: str) -> dict[str, object]:
        captured_attempts.append((api_url, access_token))
        if len(captured_attempts) == 1:
            raise JobAdderApiError(
                "Could not reach the JobAdder API.",
                endpoint_url=f"{api_url.rstrip('/')}/candidates/16496678",
            )
        return {"candidate": {"candidateId": 16496678}}

    result, winning_connection = jobadder_ingest._perform_jobadder_read_with_refresh_retry(
        jobadder_account=2236,
        stored_connection=stored_connection,
        stage_name="candidate_read",
        provider_failure_message="JobAdder candidate detail read failed.",
        read_callable=fake_read_callable,
    )

    assert result == {"candidate": {"candidateId": 16496678}}
    assert winning_connection == stored_connection
    assert captured_attempts == [
        ("https://eu2api.jobadder.com/v2/", "stored-access-token"),
        ("https://eu2api.jobadder.com/v2/", "stored-access-token"),
    ]


def test_select_latest_resume_attachment_uses_created_at_then_attachment_id() -> None:
    """
    Verify that resume selection prefers the newest timestamp and uses
    attachment ID as a fallback tie-breaker.

    Notes
    -----
    - This test directly exercises the selection rule.
    - That keeps the ranking behaviour explicit and easy to change later if the
      client's data teaches us a better rule.

    Example
    -------
    We simulate two resume attachments with the same timestamp but different
    attachment IDs. The helper should return the one with the higher numeric ID.

    In plain language:

    - pretend two resumes were uploaded at the same time
    - confirm the helper still chooses deterministically
    """

    attachments = [
        {
            "attachmentId": 100,
            "type": "Resume",
            "category": "Resume",
            "fileName": "resume-a.pdf",
            "fileType": "application/pdf",
            "createdAt": "2026-04-20T10:00:00Z",
        },
        {
            "attachmentId": 200,
            "type": "Resume",
            "category": "Resume",
            "fileName": "resume-b.pdf",
            "fileType": "application/pdf",
            "createdAt": "2026-04-20T10:00:00Z",
        },
    ]

    selected = jobadder_ingest._select_latest_resume_attachment(attachments)

    assert selected is not None
    assert selected["attachmentId"] == 200


def test_download_latest_jobadder_resume_for_candidate_returns_resume_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the resume-download orchestration helper returns one combined
    bundle containing:

    - the previously prepared ingest data
    - the selected resume metadata
    - the downloaded attachment bytes

    Notes
    -----
    - This test focuses on the boundary between:
        - metadata-only ingest preparation
        - and
        - transient binary CV retrieval
    - The key idea is that the helper should not recompute business meaning.
      It should:
        - trust the ingest-shell output
        - validate the chosen attachment ID
        - reload a read-ready connection
        - download the selected file

    Example
    -------
    We simulate:

    - an ingest bundle that already selected a likely resume
    - a fresh read-ready connection for the binary step
    - a successful binary download result

    and confirm the final return value contains both the source metadata and
    the transient file payload.

    In plain language:

    - pretend the candidate and attachment selection already succeeded
    - pretend the binary download succeeded
    - confirm the helper returns one clean combined resume bundle
    """

    fake_ingest_bundle = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "source_candidate_id": 16496678,
        "candidate": {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
        },
        "notes": {
            "items": [],
            "cleaned_items": [],
            "note_count": 0,
            "total_count": 0,
            "links": {},
        },
        "latest_resume": {
            "attachmentId": 21091489,
            "type": "Resume",
            "category": "Resume",
            "fileName": "Roger Campbell - CV 2025.pdf",
            "fileType": "application/pdf",
            "createdAt": "2026-04-20T10:00:00Z",
            "links": {
                "self": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
            },
        },
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "resume_source": {
                "provider": "jobadder_attachment",
                "external_id": 21091489,
                "file_name": "Roger Campbell - CV 2025.pdf",
                "mime_type": "application/pdf",
                "category": "Resume",
                "type": "Resume",
                "created_at": "2026-04-20T10:00:00Z",
                "self_link": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
            },
        },
    }

    refreshed_connection = {
        "access_token": "fresh-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    downloaded_resume = {
        "content_bytes": b"%PDF-1.7 test pdf bytes",
        "content_type": "application/pdf",
        "content_length": 24,
        "file_name": "Roger Campbell - CV 2025.pdf",
        "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
    }

    captured_read_call: dict[str, object] = {}

    def fake_build_ingest_shell(*, jobadder_account: int, candidate_id: int) -> dict[str, object]:
        assert jobadder_account == 2236
        assert candidate_id == 16496678
        return fake_ingest_bundle

    def fake_load_connection(*, jobadder_account: int) -> dict[str, object]:
        assert jobadder_account == 2236
        return refreshed_connection

    def fake_read_with_retry(
        *,
        jobadder_account: int,
        stored_connection: dict[str, object],
        stage_name: str,
        provider_failure_message: str,
        read_callable,
    ) -> tuple[dict[str, object], dict[str, object]]:
        assert jobadder_account == 2236
        assert stored_connection == refreshed_connection
        assert stage_name == "resume_download"
        assert provider_failure_message == "JobAdder candidate resume download failed."

        # Execute the supplied callable so the test proves the helper passes the
        # selected attachment ID and the refreshed connection values through to
        # the lower binary-download layer correctly.
        read_result = read_callable(
            api_url=stored_connection["api_url"],
            access_token=stored_connection["access_token"],
        )
        return read_result, refreshed_connection

    def fake_download_attachment(
        *,
        api_url: str,
        access_token: str,
        candidate_id: int,
        attachment_id: int,
        timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        captured_read_call["api_url"] = api_url
        captured_read_call["access_token"] = access_token
        captured_read_call["candidate_id"] = candidate_id
        captured_read_call["attachment_id"] = attachment_id
        captured_read_call["timeout_seconds"] = timeout_seconds
        return downloaded_resume

    monkeypatch.setattr(
        jobadder_ingest,
        "build_jobadder_candidate_ingest_shell",
        fake_build_ingest_shell,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_load_jobadder_connection_for_ingest",
        fake_load_connection,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_perform_jobadder_read_with_refresh_retry",
        fake_read_with_retry,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "download_jobadder_candidate_attachment",
        fake_download_attachment,
    )

    result = download_latest_jobadder_resume_for_candidate(
        jobadder_account=2236,
        candidate_id=16496678,
    )

    assert result["source_system"] == "jobadder"
    assert result["jobadder_account"] == 2236
    assert result["jobadder_instance"] == "eu2"
    assert result["api_url"] == "https://eu2api.jobadder.com/v2/"
    assert result["source_candidate_id"] == 16496678
    assert result["candidate"] == fake_ingest_bundle["candidate"]
    assert result["notes"] == fake_ingest_bundle["notes"]
    assert result["latest_resume"] == fake_ingest_bundle["latest_resume"]
    assert result["resume_source"] == fake_ingest_bundle["ingest_shell"]["resume_source"]
    assert result["downloaded_resume"] == downloaded_resume
    assert result["ingest_shell"] == fake_ingest_bundle["ingest_shell"]

    assert captured_read_call == {
        "api_url": "https://eu2api.jobadder.com/v2/",
        "access_token": "fresh-access-token",
        "candidate_id": 16496678,
        "attachment_id": 21091489,
        "timeout_seconds": 30.0,
    }


def test_download_latest_jobadder_resume_for_candidate_raises_when_no_resume_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the resume-download helper fails clearly when the ingest shell
    did not identify any likely resume attachment.

    Notes
    -----
    - This is a different policy from the earlier ingest-shell helper.
    - There, "no resume found" is a valid partial result.
    - Here, the caller explicitly asked to download a resume, so the helper
      should fail rather than pretending the request succeeded.

    Example
    -------
    We simulate an ingest bundle where:

    - candidate data exists
    - attachments may have been inspected
    - but `latest_resume` is `None`

    and confirm the helper raises `JobAdderIngestPreparationError` with the
    `resume_selection` stage.

    In plain language:

    - pretend no likely CV was found upstream
    - confirm the download helper stops immediately and clearly
    """

    monkeypatch.setattr(
        jobadder_ingest,
        "build_jobadder_candidate_ingest_shell",
        lambda *, jobadder_account, candidate_id: {
            "candidate": {"candidateId": candidate_id},
            "notes": {
                "items": [],
                "cleaned_items": [],
                "note_count": 0,
                "total_count": 0,
                "links": {},
            },
            "latest_resume": None,
            "ingest_shell": {"candidate_notes": [], "resume_source": None},
        },
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        download_latest_jobadder_resume_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    error = exc_info.value

    assert str(error) == "No likely JobAdder resume attachment was found for this candidate."
    assert error.stage == "resume_selection"
    assert error.details == [
        {"jobadder_account": 2236},
        {"candidate_id": 16496678},
    ]


def test_download_latest_jobadder_resume_for_candidate_raises_when_attachment_id_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the resume-download helper re-validates the selected
    attachment ID before attempting the binary download.

    Notes
    -----
    - The ingest shell works with raw provider payloads.
    - That means a "selected" resume could still carry a malformed
      `attachmentId` field in bad source data or in a buggy future refactor.
    - This test makes sure the helper fails locally and clearly before trying
      to build a download URL from unusable data.

    Example
    -------
    We simulate a selected resume object where:

    - `latest_resume` exists
    - but `attachmentId` is blank

    and confirm the helper raises `resume_selection`.

    In plain language:

    - pretend a resume was selected
    - but its attachment ID is unusable
    - confirm the helper rejects it before any download starts
    """

    monkeypatch.setattr(
        jobadder_ingest,
        "build_jobadder_candidate_ingest_shell",
        lambda *, jobadder_account, candidate_id: {
            "candidate": {"candidateId": candidate_id},
            "notes": {
                "items": [],
                "cleaned_items": [],
                "note_count": 0,
                "total_count": 0,
                "links": {},
            },
            "latest_resume": {
                "attachmentId": "   ",
                "fileName": "Broken Resume.pdf",
            },
            "ingest_shell": {
                "candidate_notes": [],
                "resume_source": {
                    "provider": "jobadder_attachment",
                    "external_id": None,
                }
            },
        },
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        download_latest_jobadder_resume_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    error = exc_info.value

    assert (
        str(error)
        == "The selected JobAdder resume attachment is missing a usable attachment ID."
    )
    assert error.stage == "resume_selection"
    assert error.details == [
        {"jobadder_account": 2236},
        {"candidate_id": 16496678},
    ]


def test_download_latest_jobadder_resume_for_candidate_raises_when_binary_download_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that provider-side attachment-download failures are converted into
    the ingest layer's orchestration error type with useful structured
    context.

    Notes
    -----
    - The binary download itself belongs to the lower API service layer.
    - This orchestration helper should still surface a clean ingest-level error
      when that lower layer ultimately fails.
    - The important contract here is:
        - preserve the high-level failure message
        - preserve the stage label
        - preserve the status code and endpoint context where available

    Example
    -------
    We simulate:

    - an ingest bundle with a valid selected resume
    - a fresh connection for the download step
    - a lower-layer read helper that raises `JobAdderIngestPreparationError`
      after the binary download fails

    and confirm the public helper surfaces that same structured orchestration
    failure.

    In plain language:

    - pretend attachment download failed downstream
    - confirm the public helper does not hide that failure
    """

    fake_ingest_bundle = {
        "candidate": {"candidateId": 16496678},
        "notes": {
            "items": [],
            "cleaned_items": [],
            "note_count": 0,
            "total_count": 0,
            "links": {},
        },
        "latest_resume": {
            "attachmentId": 21091489,
            "fileName": "Roger Campbell - CV 2025.pdf",
        },
        "ingest_shell": {
            "candidate_notes": [],
            "resume_source": {
                "provider": "jobadder_attachment",
                "external_id": 21091489,
            }
        },
    }

    refreshed_connection = {
        "access_token": "fresh-access-token",
        "refresh_token": "stored-refresh-token",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "jobadder_instance": "eu2",
    }

    expected_error = JobAdderIngestPreparationError(
        "JobAdder candidate resume download failed.",
        stage="resume_download",
        status_code=404,
        details=[
            {"jobadder_account": 2236},
            {"provider_status_code": 404},
            {
                "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
            },
        ],
    )

    monkeypatch.setattr(
        jobadder_ingest,
        "build_jobadder_candidate_ingest_shell",
        lambda *, jobadder_account, candidate_id: fake_ingest_bundle,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "_load_jobadder_connection_for_ingest",
        lambda *, jobadder_account: refreshed_connection,
    )

    def fake_read_with_retry(
        *,
        jobadder_account: int,
        stored_connection: dict[str, object],
        stage_name: str,
        provider_failure_message: str,
        read_callable,
    ) -> tuple[dict[str, object], dict[str, object]]:
        # This simulates the state after the lower shared retry helper has
        # already concluded that the binary download definitively failed.
        #
        # In other words, the public helper is not expected to second-guess the
        # structured orchestration error at this point. It should just surface
        # it.
        raise expected_error

    monkeypatch.setattr(
        jobadder_ingest,
        "_perform_jobadder_read_with_refresh_retry",
        fake_read_with_retry,
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        download_latest_jobadder_resume_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate resume download failed."
    assert error.stage == "resume_download"
    assert error.status_code == 404
    assert error.details == [
        {"jobadder_account": 2236},
        {"provider_status_code": 404},
        {
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
        },
    ]


def test_extract_latest_jobadder_resume_text_for_candidate_returns_text_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the new text-extraction orchestration helper returns one
    combined bundle containing:

    - the earlier resume-download context
    - the downloaded resume metadata
    - the extracted plain text payload

    Notes
    -----
    - This is the first full "candidate -> resume bytes -> resume text" test
      at the JobAdder orchestration layer.
    - The helper should not reimplement download logic itself.
    - It should:
        - reuse the resume-download bundle
        - pass the downloaded bytes and content type to the document-text helper
        - keep the overall return shape aligned with the earlier ingest helpers

    Example
    -------
    We simulate:

    - a successful resume-download bundle
    - a successful document text extraction result

    and confirm the helper returns both pieces in one combined structure.

    In plain language:

    - pretend the CV download already worked
    - pretend the document text extraction worked
    - confirm the helper returns one clean end-to-end text bundle
    """

    fake_resume_bundle = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "source_candidate_id": 16496678,
        "candidate": {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
        },
        "notes": {
            "items": [],
            "cleaned_items": [],
            "note_count": 0,
            "total_count": 0,
            "links": {},
        },
        "latest_resume": {
            "attachmentId": 21091489,
            "fileName": "Roger Campbell - CV 2025.pdf",
        },
        "resume_source": {
            "provider": "jobadder_attachment",
            "external_id": 21091489,
            "file_name": "Roger Campbell - CV 2025.pdf",
            "mime_type": "application/pdf",
        },
        "downloaded_resume": {
            "content_bytes": b"%PDF-1.7 fake pdf bytes",
            "content_type": "application/pdf",
            "content_length": 23,
            "file_name": "Roger Campbell - CV 2025.pdf",
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
        },
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
        },
    }

    fake_extracted_text = {
        "text": "Roger CampbellÃ‚\nSenior Data Scientist\nPython",
        "page_count": 2,
        "extractor": "pypdf",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "character_count": 46,
    }

    captured_extract_call: dict[str, object] = {}

    def fake_download_bundle(*, jobadder_account: int, candidate_id: int) -> dict[str, object]:
        assert jobadder_account == 2236
        assert candidate_id == 16496678
        return fake_resume_bundle

    def fake_extract_text(
        *,
        content_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
    ) -> dict[str, object]:
        captured_extract_call["content_bytes"] = content_bytes
        captured_extract_call["file_name"] = file_name
        captured_extract_call["content_type"] = content_type
        return fake_extracted_text

    monkeypatch.setattr(
        jobadder_ingest,
        "download_latest_jobadder_resume_for_candidate",
        fake_download_bundle,
    )
    monkeypatch.setattr(
        jobadder_ingest,
        "extract_text_from_resume_bytes",
        fake_extract_text,
    )

    result = extract_latest_jobadder_resume_text_for_candidate(
        jobadder_account=2236,
        candidate_id=16496678,
    )

    assert result["source_system"] == "jobadder"
    assert result["jobadder_account"] == 2236
    assert result["jobadder_instance"] == "eu2"
    assert result["api_url"] == "https://eu2api.jobadder.com/v2/"
    assert result["source_candidate_id"] == 16496678
    assert result["candidate"] == fake_resume_bundle["candidate"]
    assert result["notes"] == fake_resume_bundle["notes"]
    assert result["latest_resume"] == fake_resume_bundle["latest_resume"]
    assert result["resume_source"] == fake_resume_bundle["resume_source"]
    assert result["downloaded_resume"] == fake_resume_bundle["downloaded_resume"]
    assert result["extracted_resume_text"] == {
        "text": "Roger CampbellÃ‚\nSenior Data Scientist\nPython",
        "cleaned_text": "Roger Campbell\nSenior Data Scientist\nPython",
        "page_count": 2,
        "extractor": "pypdf",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "character_count": 46,
    }
    assert result["ingest_shell"] == fake_resume_bundle["ingest_shell"]

    assert captured_extract_call == {
        "content_bytes": b"%PDF-1.7 fake pdf bytes",
        "file_name": "Roger Campbell - CV 2025.pdf",
        "content_type": "application/pdf",
    }


def test_extract_latest_jobadder_resume_text_for_candidate_supports_docx_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the orchestration helper passes DOCX metadata through to the
    generic resume-text dispatcher.

    Notes
    -----
    - This test exists because the live batch failures showed `.docx` resumes
      were previously being handed to the PDF parser.
    - The ingest layer should not guess from ZIP-like bytes alone.
    - It should pass the upstream content type and file name through so the
      document module can make the format decision in one place.
    """

    fake_resume_bundle = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "source_candidate_id": 13816910,
        "candidate": {"candidateId": 13816910},
        "notes": {
            "items": [],
            "cleaned_items": [],
            "note_count": 0,
            "total_count": 0,
            "links": {},
        },
        "latest_resume": {
            "attachmentId": 21091490,
            "fileName": "Isaiah Perumalla.docx",
        },
        "resume_source": {
            "provider": "jobadder_attachment",
            "external_id": 21091490,
            "file_name": "Isaiah Perumalla.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        "downloaded_resume": {
            "content_bytes": b"PK\x03\x04 fake docx bytes",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_length": 20,
            "file_name": "Isaiah Perumalla.docx",
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/13816910/attachments/21091490",
        },
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": 13816910,
        },
    }

    captured_extract_call: dict[str, object] = {}

    monkeypatch.setattr(
        jobadder_ingest,
        "download_latest_jobadder_resume_for_candidate",
        lambda *, jobadder_account, candidate_id: fake_resume_bundle,
    )

    def fake_extract_text(
        *,
        content_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
    ) -> dict[str, object]:
        captured_extract_call["content_bytes"] = content_bytes
        captured_extract_call["file_name"] = file_name
        captured_extract_call["content_type"] = content_type
        return {
            "text": "Isaiah Perumalla\n\nSenior Data Engineer",
            "page_count": None,
            "extractor": "docx_xml",
            "file_name": "Isaiah Perumalla.docx",
            "character_count": 38,
        }

    monkeypatch.setattr(
        jobadder_ingest,
        "extract_text_from_resume_bytes",
        fake_extract_text,
    )

    result = extract_latest_jobadder_resume_text_for_candidate(
        jobadder_account=2236,
        candidate_id=13816910,
    )

    assert result["extracted_resume_text"]["extractor"] == "docx_xml"
    assert result["extracted_resume_text"]["cleaned_text"] == (
        "Isaiah Perumalla\n\nSenior Data Engineer"
    )
    assert captured_extract_call == {
        "content_bytes": b"PK\x03\x04 fake docx bytes",
        "file_name": "Isaiah Perumalla.docx",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


def test_extract_latest_jobadder_resume_text_for_candidate_raises_when_text_extraction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that document text-extraction failures are converted into the ingest
    layer's orchestration error type with useful structured context.

    Notes
    -----
    - The lower document helper uses `ResumeTextExtractionError`.
    - This higher JobAdder orchestration layer should translate that into
      `JobAdderIngestPreparationError` so callers only need one main error
      family for the whole candidate-resume-text flow.
    - The translated error should still preserve the important parsing-stage
      context.

    Example
    -------
    We simulate:

    - a successful resume-download bundle
    - a failing document text extraction step

    and confirm the public helper raises a structured ingest-level error with:

    - `stage = "resume_text_extraction"`
    - the original parser-stage label preserved in details

    In plain language:

    - pretend the CV download worked
    - pretend the document parser failed later
    - confirm the helper surfaces that clearly at the ingest layer
    """

    fake_resume_bundle = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "jobadder_instance": "eu2",
        "api_url": "https://eu2api.jobadder.com/v2/",
        "source_candidate_id": 16496678,
        "candidate": {"candidateId": 16496678},
        "notes": {
            "items": [],
            "cleaned_items": [],
            "note_count": 0,
            "total_count": 0,
            "links": {},
        },
        "latest_resume": {"attachmentId": 21091489},
        "resume_source": {"provider": "jobadder_attachment"},
        "downloaded_resume": {
            "content_bytes": b"bad pdf bytes",
            "content_type": "application/pdf",
            "content_length": 13,
            "file_name": "Broken Resume.pdf",
            "endpoint_url": "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489",
        },
        "ingest_shell": {
            "source_system": "jobadder",
            "source_candidate_id": 16496678,
            "candidate_notes": [],
        },
    }

    monkeypatch.setattr(
        jobadder_ingest,
        "download_latest_jobadder_resume_for_candidate",
        lambda *, jobadder_account, candidate_id: fake_resume_bundle,
    )

    def fake_extract_text(
        *,
        content_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
    ) -> dict[str, object]:
        raise ResumeTextExtractionError(
            "The resume PDF could not be parsed.",
            stage="pdf_parse",
            details=[{"file_name": "Broken Resume.pdf"}],
        )

    monkeypatch.setattr(
        jobadder_ingest,
        "extract_text_from_resume_bytes",
        fake_extract_text,
    )

    with pytest.raises(JobAdderIngestPreparationError) as exc_info:
        extract_latest_jobadder_resume_text_for_candidate(
            jobadder_account=2236,
            candidate_id=16496678,
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate resume text extraction failed."
    assert error.stage == "resume_text_extraction"
    assert error.details == [
        {"jobadder_account": 2236},
        {"candidate_id": 16496678},
        {"resume_text_stage": "pdf_parse"},
        {"file_name": "Broken Resume.pdf"},
    ]
