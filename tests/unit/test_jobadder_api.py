"""
Unit tests for JobAdder API read helpers.

This module tests the small authenticated JobAdder API read helpers in
`backend.services.jobadder_api`.

It gives the rest of the repository a stable way to check:

- the backend builds the correct JobAdder API headers
- the first candidate-list read uses the expected endpoint
- successful provider responses are normalised correctly
- provider-side failures become structured local errors
- malformed success payloads fail clearly
- transport-level failures are surfaced cleanly

Why these tests matter
----------------------
The backend has already proved that it can:

- complete the OAuth approval flow
- exchange the one-time authorisation code for tokens
- persist the returned token set in Postgres

The next proof point is different:

    "Can the backend use the stored token to read real data from JobAdder?"

These tests exercise the first service helper for that task without touching
the real JobAdder API.

In plain language:

- this module answers the question:

    "Can the backend make a small authenticated JobAdder read safely?"

- it does not call the real JobAdder API
- it does not touch the database
- it only tests local service-helper behaviour
"""

import httpx
import pytest

from backend.services.jobadder_api import (
    JobAdderApiError,
    build_jobadder_api_headers,
    download_jobadder_candidate_attachment,
    fetch_jobadder_candidate_detail,
    fetch_jobadder_candidates_page,
    fetch_jobadder_candidate_notes,
    fetch_jobadder_candidate_skills,
    fetch_jobadder_candidates_preview,
)


def test_build_jobadder_api_headers_returns_expected_bearer_headers() -> None:
    """
    Verify that the header helper produces the standard bearer-token shape.

    In plain language:

    - take a fake stored access token
    - build the headers
    - confirm the result matches what JobAdder expects
    """

    headers = build_jobadder_api_headers(access_token="test-access-token")

    assert headers == {
        "Authorization": "Bearer test-access-token",
        "Accept": "application/json",
    }


def test_build_jobadder_api_headers_raises_when_token_is_blank() -> None:
    """
    Verify that the header helper rejects a blank access token.

    In plain language:

    - pass a useless token value
    - confirm the helper fails early rather than building a bad header
    """

    with pytest.raises(ValueError) as exc_info:
        build_jobadder_api_headers(access_token="   ")

    assert str(exc_info.value) == "JobAdder access token cannot be empty."


def test_fetch_jobadder_candidates_preview_returns_trimmed_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a successful JobAdder candidate-list response is normalised
    correctly and trimmed to the requested preview size.

    Notes
    -----
    - This test does not call the real JobAdder API.
    - It replaces `httpx.get(...)` with a small fake function.
    - That lets the test inspect the outgoing request and control the returned
      provider payload precisely.

    In plain language:

    - pretend JobAdder returned a first page of candidates
    - confirm the helper called the expected endpoint with bearer auth
    - confirm the helper returned a small, predictable preview shape
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "items": [
                    {"candidateId": 1, "firstName": "Alice"},
                    {"candidateId": 2, "firstName": "Ben"},
                    {"candidateId": 3, "firstName": "Cara"},
                ],
                "totalCount": 3,
                "links": {
                    "first": "https://api.jobadder.com/v2/candidates?page=1",
                },
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    preview = fetch_jobadder_candidates_preview(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        item_limit=2,
    )

    assert preview["item_count"] == 2
    assert preview["total_count"] == 3
    assert preview["links"] == {
        "first": "https://api.jobadder.com/v2/candidates?page=1",
    }
    assert preview["items"] == [
        {"candidateId": 1, "firstName": "Alice"},
        {"candidateId": 2, "firstName": "Ben"},
    ]
    assert preview["endpoint_url"] == "https://api.jobadder.com/v2/candidates"

    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates"
    assert captured_request["headers"] == {
        "Authorization": "Bearer jobadder-access-token",
        "Accept": "application/json",
    }
    assert captured_request["timeout"] == 30.0


def test_fetch_jobadder_candidates_preview_does_not_duplicate_v2_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the helper does not append a second `/v2` when the stored
    JobAdder API URL already includes the version segment.

    Notes
    -----
    - This protects against the exact production failure where the backend
      built:

          https://eu2api.jobadder.com/v2/v2/candidates

    - The helper should instead normalise that to:

          https://eu2api.jobadder.com/v2/candidates

    In plain language:

    - pretend the stored API URL already ends in `/v2`
    - confirm the helper still builds one valid candidate-list endpoint
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "items": [],
                "totalCount": 0,
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    preview = fetch_jobadder_candidates_preview(
        api_url="https://eu2api.jobadder.com/v2",
        access_token="jobadder-access-token",
    )

    assert preview["endpoint_url"] == "https://eu2api.jobadder.com/v2/candidates"
    assert preview["item_count"] == 0
    assert captured_request["url"] == "https://eu2api.jobadder.com/v2/candidates"


def test_fetch_jobadder_candidates_page_requests_first_page_with_explicit_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the paginated candidate helper requests the first page using
    explicit page and page-size parameters.

    In plain language:

    - ask for page 1 with a concrete page size
    - confirm the helper keeps the base endpoint clean
    - confirm the pagination params are sent separately
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout, params=None):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout
        captured_request["params"] = params

        return httpx.Response(
            200,
            json={
                "items": [
                    {"candidateId": 1, "firstName": "Alice"},
                    {"candidateId": 2, "firstName": "Ben"},
                ],
                "totalCount": 2,
                "links": {
                    "next": "https://api.jobadder.com/v2/candidates?page=2",
                },
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    page_result = fetch_jobadder_candidates_page(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        page=1,
        page_size=100,
    )

    assert page_result["item_count"] == 2
    assert page_result["page"] == 1
    assert page_result["page_size"] == 100
    assert page_result["links"] == {
        "next": "https://api.jobadder.com/v2/candidates?page=2",
    }

    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates"
    assert captured_request["params"] == {
        "page": 1,
        "pagesize": 100,
    }


def test_fetch_jobadder_candidates_page_uses_provider_next_link_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the paginated candidate helper trusts a provider-supplied next
    link rather than reconstructing it.

    In plain language:

    - pretend JobAdder already gave us the next-page URL
    - confirm the helper calls that URL directly
    - confirm it does not send duplicate pagination params
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout, params=None):
        captured_request["url"] = url
        captured_request["params"] = params

        return httpx.Response(
            200,
            json={
                "items": [
                    {"candidateId": 3, "firstName": "Cara"},
                ],
                "totalCount": 3,
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    page_result = fetch_jobadder_candidates_page(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        page=2,
        page_size=100,
        page_url="https://api.jobadder.com/v2/candidates?page=2",
    )

    assert page_result["item_count"] == 1
    assert page_result["page"] == 2
    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates?page=2"
    assert captured_request["params"] is None


def test_fetch_jobadder_candidates_page_raises_when_items_list_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the paginated candidate helper rejects a malformed success
    payload without an `items` list.

    In plain language:

    - pretend JobAdder returned a 200 response
    - omit the `items` list
    - confirm the helper fails clearly
    """

    def fake_get(url, headers, timeout, params=None):
        return httpx.Response(
            200,
            json={
                "totalCount": 3,
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        fetch_jobadder_candidates_page(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
            page=1,
            page_size=100,
        )

    error = exc_info.value
    assert str(error) == (
        "JobAdder candidate read response did not include an items list."
    )


def test_fetch_jobadder_candidates_preview_raises_for_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a provider-side HTTP failure becomes a structured local error.

    Notes
    -----
    - This covers cases such as provider throttling, expired tokens, or other
      upstream request failures where JobAdder did return an HTTP response.
    - The helper should preserve the useful debugging metadata rather than
      collapsing everything into a generic exception.

    In plain language:

    - pretend JobAdder rejected the request
    - confirm the helper raises one clear backend exception
    - confirm the important provider metadata is kept on that exception
    """

    def fake_get(url, headers, timeout):
        return httpx.Response(
            429,
            headers={"Retry-After": "40"},
            json={"message": "Too many requests"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        fetch_jobadder_candidates_preview(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate read failed."
    assert error.status_code == 429
    assert error.retry_after == "40"
    assert error.endpoint_url == "https://api.jobadder.com/v2/candidates"
    assert error.response_body == {"message": "Too many requests"}


def test_fetch_jobadder_candidates_preview_raises_when_items_list_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a malformed success payload is rejected clearly.

    Notes
    -----
    - A 200 response is not enough on its own.
    - The helper still needs the list payload shape it was built to consume.
    - If JobAdder returned a shape we do not understand, we should fail fast
      rather than pretend the read succeeded.

    In plain language:

    - pretend JobAdder returned HTTP 200
    - but left out the `items` list
    - confirm the helper rejects that response clearly
    """

    def fake_get(url, headers, timeout):
        return httpx.Response(
            200,
            json={
                "totalCount": 1,
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        fetch_jobadder_candidates_preview(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
        )

    error = exc_info.value

    assert (
        str(error)
        == "JobAdder candidate read response did not include an items list."
    )
    assert error.status_code == 200
    assert error.endpoint_url == "https://api.jobadder.com/v2/candidates"


def test_fetch_jobadder_candidates_preview_raises_for_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that transport-level failures are surfaced clearly.

    Notes
    -----
    - This covers cases where the backend could not reach JobAdder at all.
    - That is different from provider-side HTTP failures because no usable
      upstream response body exists in this case.

    In plain language:

    - pretend the backend could not reach JobAdder
    - confirm the helper raises a clear connectivity error
    """

    def fake_get(url, headers, timeout):
        raise httpx.ConnectError("Network failure")

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        fetch_jobadder_candidates_preview(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
        )

    error = exc_info.value

    assert str(error) == "Could not reach the JobAdder API."
    assert error.endpoint_url == "https://api.jobadder.com/v2/candidates"


def test_fetch_jobadder_candidate_detail_returns_candidate_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the candidate-detail helper returns one full candidate object.

    In plain language:

    - pretend JobAdder returned one candidate payload
    - confirm the helper called the expected detail endpoint
    - confirm the helper returned that candidate in a small predictable wrapper
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "candidateId": 123,
                "firstName": "Alice",
                "lastName": "Nguyen",
                "email": "alice@example.com",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    detail = fetch_jobadder_candidate_detail(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=123,
    )

    assert detail["candidate"] == {
        "candidateId": 123,
        "firstName": "Alice",
        "lastName": "Nguyen",
        "email": "alice@example.com",
    }
    assert detail["endpoint_url"] == "https://api.jobadder.com/v2/candidates/123"
    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates/123"


def test_fetch_jobadder_candidate_skills_returns_category_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the candidate-skills helper returns the structured category tree
    documented by the JobAdder API.

    In plain language:

    - pretend JobAdder returned one category with one subcategory and one skill
    - confirm the helper called the expected skills endpoint
    - confirm the helper returned the structured category list cleanly
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "categoryId": 1,
                        "name": "Engineering",
                        "subCategories": [
                            {
                                "subCategoryId": 2,
                                "name": "Backend",
                                "skills": [
                                    {"skillId": 3, "name": "Python"},
                                ],
                            }
                        ],
                    }
                ],
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    skills = fetch_jobadder_candidate_skills(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=123,
    )

    assert skills["category_count"] == 1
    assert skills["categories"] == [
        {
            "categoryId": 1,
            "name": "Engineering",
            "subCategories": [
                {
                    "subCategoryId": 2,
                    "name": "Backend",
                    "skills": [
                        {"skillId": 3, "name": "Python"},
                    ],
                }
            ],
        }
    ]
    assert skills["endpoint_url"] == "https://api.jobadder.com/v2/candidates/123/skills"
    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates/123/skills"


def test_fetch_jobadder_candidate_notes_returns_notes_list_with_text_field_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the candidate-notes helper calls the dedicated JobAdder notes
    endpoint and explicitly requests full note text.

    Notes
    -----
    - This test matters because candidate detail does not carry the actual note
      bodies directly.
    - JobAdder's notes endpoint supports `Fields=text`, and that parameter is
      easy to forget.
    - If we omit it, the backend may only receive truncated note previews
      (`textPartial`) instead of the real note text we eventually want to map.

    Example
    -------
    We simulate a successful candidate-notes response and confirm that the
    outbound provider request includes:

    - `Fields=text`
    - `Limit=<requested item limit>`

    In plain language:

    - pretend JobAdder returned one candidate note
    - confirm the helper called the notes endpoint
    - confirm the helper asked for the full text field, not just a preview
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, params, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["params"] = params
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "noteId": "11111111-1111-1111-1111-111111111111",
                        "type": "General",
                        "textPartial": "Candidate called back",
                        "text": "Candidate called back and is available next Tuesday.",
                        "createdAt": "2026-04-30T10:00:00Z",
                    }
                ],
                "totalCount": 1,
                "links": {
                    "self": "https://api.jobadder.com/v2/candidates/123/notes"
                },
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    notes = fetch_jobadder_candidate_notes(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=123,
        item_limit=10,
    )

    assert notes["note_count"] == 1
    assert notes["total_count"] == 1
    assert notes["links"] == {
        "self": "https://api.jobadder.com/v2/candidates/123/notes"
    }
    assert notes["notes"] == [
        {
            "noteId": "11111111-1111-1111-1111-111111111111",
            "type": "General",
            "textPartial": "Candidate called back",
            "text": "Candidate called back and is available next Tuesday.",
            "createdAt": "2026-04-30T10:00:00Z",
        }
    ]
    assert notes["endpoint_url"] == "https://api.jobadder.com/v2/candidates/123/notes"

    assert captured_request["url"] == "https://api.jobadder.com/v2/candidates/123/notes"
    assert captured_request["headers"] == {
        "Authorization": "Bearer jobadder-access-token",
        "Accept": "application/json",
    }
    assert captured_request["params"] == {
        "Fields": ["text"],
        "Limit": 10,
    }
    assert captured_request["timeout"] == 30.0


def test_fetch_jobadder_candidate_notes_raises_when_items_list_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a malformed candidate-notes success payload is rejected
    clearly.

    Notes
    -----
    - A 200 response is not enough by itself.
    - The helper still needs the documented `items` list to reason about the
      returned notes.

    In plain language:

    - pretend JobAdder returned HTTP 200
    - but did not include a notes list
    - confirm the helper fails clearly
    """

    def fake_get(url, headers, params, timeout):
        return httpx.Response(
            200,
            json={
                "totalCount": 1,
                "links": {},
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        fetch_jobadder_candidate_notes(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
            candidate_id=123,
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate notes response did not include an items list."
    assert error.endpoint_url == "https://api.jobadder.com/v2/candidates/123/notes"


def test_download_jobadder_candidate_attachment_returns_binary_content_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the binary attachment-download helper returns the downloaded
    bytes and the useful response metadata in one small predictable wrapper.

    Notes
    -----
    - This is the first JobAdder helper in the module that exercises a
      successful non-JSON response path.
    - That matters because attachment download is a different transport shape
      from the earlier candidate and skills reads:
        - the success path returns bytes
        - the error path may still return JSON
    - This test therefore checks both:
        - the outbound request shape
        - the returned binary-content wrapper

    Example
    -------
    We simulate a successful PDF response with:

    - `Content-Type: application/pdf`
    - `Content-Length: 123`
    - `Content-Disposition: attachment; filename="Roger Campbell - CV 2025.pdf"`

    and confirm the helper extracts the filename and preserves the bytes.

    In plain language:

    - pretend JobAdder returned a PDF attachment
    - confirm the helper called the correct endpoint
    - confirm the helper returned the bytes and key metadata cleanly
    """

    captured_request: dict[str, object] = {}

    def fake_get(url, headers, timeout):
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["timeout"] = timeout

        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": "123",
                "Content-Disposition": (
                    'attachment; filename="Roger Campbell - CV 2025.pdf"'
                ),
            },
            content=b"%PDF-1.7 fake-pdf-content",
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    attachment = download_jobadder_candidate_attachment(
        api_url="https://eu2api.jobadder.com/v2/",
        access_token="jobadder-access-token",
        candidate_id=16496678,
        attachment_id=21091489,
    )

    assert attachment["content_bytes"] == b"%PDF-1.7 fake-pdf-content"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["content_length"] == 123
    assert attachment["file_name"] == "Roger Campbell - CV 2025.pdf"
    assert (
        attachment["endpoint_url"]
        == "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
    )

    assert (
        captured_request["url"]
        == "https://eu2api.jobadder.com/v2/candidates/16496678/attachments/21091489"
    )
    assert captured_request["headers"] == {
        "Authorization": "Bearer jobadder-access-token",
        "Accept": "application/json",
    }
    assert captured_request["timeout"] == 30.0


def test_download_jobadder_candidate_attachment_returns_none_file_name_when_content_disposition_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that the helper still succeeds when JobAdder does not provide a
    `Content-Disposition` header with a filename.

    Notes
    -----
    - Real file-download APIs do not always provide a clean filename header.
    - The helper should still return the binary content and other response
      metadata even if the file name is unavailable.

    Example
    -------
    We simulate a successful PDF response with:

    - `Content-Type`
    - `Content-Length`
    - but no `Content-Disposition`

    and confirm the helper returns `file_name = None`.

    In plain language:

    - pretend JobAdder returned the file but not the filename header
    - confirm the download still succeeds
    """

    def fake_get(url, headers, timeout):
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": "456",
            },
            content=b"%PDF-1.7 another-fake-pdf",
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    attachment = download_jobadder_candidate_attachment(
        api_url="https://api.jobadder.com",
        access_token="jobadder-access-token",
        candidate_id=16496678,
        attachment_id=21091489,
    )

    assert attachment["content_bytes"] == b"%PDF-1.7 another-fake-pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["content_length"] == 456
    assert attachment["file_name"] is None
    assert (
        attachment["endpoint_url"]
        == "https://api.jobadder.com/v2/candidates/16496678/attachments/21091489"
    )


def test_download_jobadder_candidate_attachment_raises_for_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that a provider-side binary-download failure becomes the same local
    structured exception type used by the JSON read helpers.

    Notes
    -----
    - This is important because higher layers should not need one error
      contract for JSON reads and another for binary downloads.
    - Even though the success path is binary, the failure path often still
      contains JSON provider details.

    Example
    -------
    We simulate a `404` attachment-download failure and confirm the helper
    raises `JobAdderApiError` with the expected endpoint and status code.

    In plain language:

    - pretend JobAdder rejected the attachment download
    - confirm the helper raises one clear backend exception
    """

    def fake_get(url, headers, timeout):
        return httpx.Response(
            404,
            json={"message": "Attachment not found"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        download_jobadder_candidate_attachment(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
            candidate_id=16496678,
            attachment_id=99999999,
        )

    error = exc_info.value

    assert str(error) == "JobAdder candidate attachment download failed."
    assert error.status_code == 404
    assert (
        error.endpoint_url
        == "https://api.jobadder.com/v2/candidates/16496678/attachments/99999999"
    )
    assert error.response_body == {"message": "Attachment not found"}


def test_download_jobadder_candidate_attachment_raises_for_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that transport-level failures during attachment download are surfaced
    clearly.

    Notes
    -----
    - This covers the case where the backend could not reach JobAdder at all.
    - As with the JSON helpers, the caller should receive one clear local
      exception rather than a raw `httpx` error.

    Example
    -------
    We simulate a connection failure and confirm the helper raises
    `JobAdderApiError` with the expected endpoint.

    In plain language:

    - pretend the backend could not reach JobAdder
    - confirm the helper raises a connectivity error
    """

    def fake_get(url, headers, timeout):
        raise httpx.ConnectError("Network failure")

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(JobAdderApiError) as exc_info:
        download_jobadder_candidate_attachment(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
            candidate_id=16496678,
            attachment_id=21091489,
        )

    error = exc_info.value

    assert str(error) == "Could not reach the JobAdder API."
    assert (
        error.endpoint_url
        == "https://api.jobadder.com/v2/candidates/16496678/attachments/21091489"
    )


def test_download_jobadder_candidate_attachment_raises_when_attachment_id_is_invalid() -> None:
    """
    Verify that the helper rejects an invalid attachment ID before doing any
    provider work.

    Notes
    -----
    - This is a local caller-input validation test.
    - The helper should fail immediately rather than constructing a bad
      provider URL and leaving the error to some later HTTP layer.

    Example
    -------
    Passing `attachment_id=0` should raise `ValueError`.

    In plain language:

    - pass an invalid attachment ID
    - confirm the helper fails early
    """

    with pytest.raises(ValueError) as exc_info:
        download_jobadder_candidate_attachment(
            api_url="https://api.jobadder.com",
            access_token="jobadder-access-token",
            candidate_id=16496678,
            attachment_id=0,
        )

    assert str(exc_info.value) == "JobAdder attachment_id must be at least 1."
