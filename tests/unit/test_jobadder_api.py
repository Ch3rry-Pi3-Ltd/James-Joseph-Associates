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
