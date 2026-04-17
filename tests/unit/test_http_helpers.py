"""
Unit tests for shared HTTP helper functions.

These tests check the small request-header utilities in `backend.core.http`.

The important question is:

    "Can the backend read useful HTTP metadata in one consistent way?"

That matters because future routes will need to read common request headers for:

- idempotency
- source-system tracking
- Make.com run tracking
- request IDs for logging and tracing

These tests do not call real API routes.

They test the helper functions directly:

    normalise_header_value(...)
    get_optional_header(...)
    get_request_metadata(...)

The expected behaviour is:

- missing headers become `None`
- blank headers become `None`
- whitespace is trimmed from useful headers
- recognised metadata headers are returned with Python-friendly keys
- unrecognised headers are ignored

In plain language:

- this file checks the small HTTP helper tools
- it does not test FastAPI routing
- it does not test Supabase
- it does not require real Make.com requests
- it does not require any real data
"""

from fastapi import Request

from backend.core.http import (
    IDEMPOTENCY_KEY_HEADER,
    MAKE_RUN_ID_HEADER,
    REQUEST_ID_HEADER,
    SOURCE_SYSTEM_HEADER,
    get_optional_header,
    get_request_metadata,
    normalise_header_value,
)


def make_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """
    Build a minimal FastAPI request object for HTTP helper tests.

    The helper functions in `backend.core.http` expect a FastAPI `Request`
    object because real endpoint code will receive a request from FastAPI.

    These tests do not need a real server or a real route. They only need a
    request object with headers attached.

    Parameters
    ----------
    headers : list[tuple[bytes, bytes]] | None
        Optional ASGI-style request headers.

        ASGI stores headers as byte pairs:

            (header_name, header_value)

        For example:

            (b"x-source-system", b"jobadder")

    Returns
    -------
    Request
        Minimal FastAPI request object containing the supplied headers.

    Notes
    -----
    - This does not start Uvicorn.
    - This does not call the real app.
    - This does not send a network request.
    - It only creates enough request structure for header-reading tests.

    Example
    -------
    A request with a source-system header can be created like this:

        request = make_request(
            headers=[
                (b"x-source-system", b"jobadder"),
            ]
        )

    In plain language:

    - build a fake request
    - attach fake headers
    - pass it into the HTTP helper functions
    """

    # FastAPI's `Request` object is built from an ASGI scope.
    #   - The scope is just a dictionary describing the incoming request.
    #   - For these tests, we only need the request type, method, path, and
    #     headers.
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/example",
            "headers": headers or [],
        }
    )


def test_normalise_header_value_returns_none_for_missing_value() -> None:
    """
    Verify that a missing header value stays missing.

    FastAPI returns `None` when a header is not present on the request.

    Notes
    -----
    - Missing optional metadata should not become an empty string.
    - Returning `None` makes it clear that the client did not provide the value.
    - This behaviour is used by `get_optional_header` and
      `get_request_metadata`.

    In plain language:

    - no header value came in
    - no useful header value should come out
    """

    assert normalise_header_value(None) is None


def test_normalise_header_value_returns_none_for_empty_string() -> None:
    """
    Verify that an empty header value is treated as missing.

    A client can send a header key with no useful value.

    For example:

        X-Source-System:

    Notes
    -----
    - Empty strings are not useful request metadata.
    - Treating them as missing keeps downstream code simpler.
    - Future endpoint validation can decide whether missing metadata should
      produce an error.

    In plain language:

    - an empty header is not real metadata
    - return `None`
    """

    assert normalise_header_value("") is None


def test_normalise_header_value_returns_none_for_whitespace_only_string() -> None:
    """
    Verify that whitespace-only header values are treated as missing.

    A client might accidentally send a value containing only spaces.

    For example:

        X-Source-System:

    Notes
    -----
    - Whitespace-only values should not be stored as metadata.
    - They should behave the same as missing values.
    - This prevents audit logs or database rows from receiving meaningless
      strings.

    In plain language:

    - spaces only are not useful text
    - return `None`
    """

    assert normalise_header_value("   ") is None


def test_normalise_header_value_trims_useful_text() -> None:
    """
    Verify that useful header text is stripped of surrounding whitespace.

    Clients or workflow tools may accidentally add spaces around header values.

    For example:

        X-Source-System:  jobadder 

    Notes
    -----
    - The useful value is `jobadder`.
    - Leading and trailing spaces are not meaningful.
    - The helper should clean the value before endpoint code uses it.

    In plain language:

    - keep the real text
    - remove the accidental spaces
    """

    assert normalise_header_value(" jobadder ") == "jobadder"


def test_get_optional_header_returns_none_when_header_is_missing() -> None:
    """
    Verify that missing optional headers return `None`.

    This test checks the full request-header lookup helper, not just the string
    normalisation helper.

    Notes
    -----
    - The request contains no headers.
    - The helper asks for `X-Source-System`.
    - Because the header is missing, the helper should return `None`.

    In plain language:

    - look for a header that is not there
    - get `None`
    """

    request = make_request()

    assert get_optional_header(request, SOURCE_SYSTEM_HEADER) is None


def test_get_optional_header_returns_clean_header_value() -> None:
    """
    Verify that optional headers are read and normalised.

    This test creates a fake request containing:

        X-Source-System:  jobadder 

    The helper should return:

        jobadder

    Notes
    -----
    - Header lookup should find the supplied value.
    - Whitespace should be trimmed.
    - Endpoint code should receive the cleaned value.

    In plain language:

    - read the header
    - clean the header
    - return the useful value
    """

    request = make_request(
        headers=[
            (b"x-source-system", b" jobadder "),
        ]
    )

    assert get_optional_header(request, SOURCE_SYSTEM_HEADER) == "jobadder"


def test_get_optional_header_is_case_insensitive() -> None:
    """
    Verify that HTTP header lookup is case-insensitive.

    HTTP header names are not case-sensitive.

    These should refer to the same header:

        X-Source-System
        x-source-system
        X-SOURCE-SYSTEM

    Notes
    -----
    - FastAPI/Starlette handles case-insensitive header lookup for us.
    - This test protects the expectation that callers can use the constant name
      without caring how the client cased the actual HTTP header.
    - That matters because different tools may format headers differently.

    In plain language:

    - HTTP header casing should not matter
    - the helper should still find the value
    """

    request = make_request(
        headers=[
            (b"x-source-system", b"jobadder"),
        ]
    )

    assert get_optional_header(request, "X-SOURCE-SYSTEM") == "jobadder"


def test_get_request_metadata_returns_recognised_headers() -> None:
    """
    Verify that common request metadata headers are collected.

    This test creates a fake request with all currently recognised metadata
    headers:

        Idempotency-Key
        X-Source-System
        X-Make-Run-Id
        X-Request-Id

    The helper should return those values using Python-friendly dictionary keys.

    Notes
    -----
    - External HTTP headers use names like `X-Source-System`.
    - Internal Python code should use names like `source_system`.
    - This helper performs that small translation in one place.

    Expected result
    ---------------
    The helper should return:

        {
            "idempotency_key": "jobadder-candidate-123",
            "source_system": "jobadder",
            "make_run_id": "make-run-456",
            "request_id": "request-789"
        }

    In plain language:

    - collect the headers we care about
    - rename them into Python-style keys
    - return one metadata dictionary
    """

    request = make_request(
        headers=[
            (b"idempotency-key", b"jobadder-candidate-123"),
            (b"x-source-system", b"jobadder"),
            (b"x-make-run-id", b"make-run-456"),
            (b"x-request-id", b"request-789"),
        ]
    )

    metadata = get_request_metadata(request)

    assert metadata == {
        "idempotency_key": "jobadder-candidate-123",
        "source_system": "jobadder",
        "make_run_id": "make-run-456",
        "request_id": "request-789",
    }


def test_get_request_metadata_omits_missing_headers() -> None:
    """
    Verify that missing metadata headers are not included in the result.

    A request may contain only some of the metadata headers.

    For example, Make.com might send a source-system name before we have agreed
    the final idempotency key format.

    Notes
    -----
    - Missing values should not appear as empty strings.
    - Missing values should not appear as `None` in the dictionary.
    - The returned metadata dictionary should contain only useful values.

    In plain language:

    - only include headers that were actually supplied
    - leave missing headers out
    """

    request = make_request(
        headers=[
            (b"x-source-system", b"jobadder"),
        ]
    )

    metadata = get_request_metadata(request)

    assert metadata == {
        "source_system": "jobadder",
    }


def test_get_request_metadata_omits_blank_headers() -> None:
    """
    Verify that blank metadata headers are ignored.

    A request might include recognised header names with empty or whitespace-only
    values.

    For example:

        X-Source-System:    
        X-Make-Run-Id:

    Notes
    -----
    - Blank values should not be treated as real metadata.
    - This keeps future logs and database records cleaner.
    - Endpoint-specific validation can later decide whether missing metadata is
      allowed for a particular route.

    In plain language:

    - recognised header names are not enough
    - the values also need useful text
    """

    request = make_request(
        headers=[
            (b"idempotency-key", b"   "),
            (b"x-source-system", b""),
            (b"x-make-run-id", b"make-run-456"),
            (b"x-request-id", b"   request-789   "),
        ]
    )

    metadata = get_request_metadata(request)

    assert metadata == {
        "make_run_id": "make-run-456",
        "request_id": "request-789",
    }


def test_get_request_metadata_ignores_unrecognised_headers() -> None:
    """
    Verify that unrelated headers are ignored.

    Real HTTP requests contain many headers that are not part of our metadata
    contract.

    For example:

        User-Agent
        Accept
        Content-Type

    Notes
    -----
    - This helper should only return metadata headers the backend explicitly
      recognises.
    - It should not copy every request header into logs or future persistence.
    - That keeps request metadata small and intentional.

    In plain language:

    - ignore headers we did not ask for
    - return only the metadata contract
    """

    request = make_request(
        headers=[
            (b"user-agent", b"test-client"),
            (b"accept", b"application/json"),
            (b"x-source-system", b"jobadder"),
        ]
    )

    metadata = get_request_metadata(request)

    assert metadata == {
        "source_system": "jobadder",
    }


def test_header_constants_match_public_header_names() -> None:
    """
    Verify that HTTP header constants keep the expected public names.

    These constants are small, but they matter because future endpoints and tests
    should use the same names everywhere.

    Notes
    -----
    - `Idempotency-Key` is the standard public header name for idempotent calls.
    - `X-Source-System` identifies the external system that sent the record.
    - `X-Make-Run-Id` links requests back to Make.com scenario runs.
    - `X-Request-Id` can support future tracing and logging.

    In plain language:

    - keep the header names stable
    - avoid typo-driven differences between routes
    """

    assert IDEMPOTENCY_KEY_HEADER == "Idempotency-Key"
    assert SOURCE_SYSTEM_HEADER == "X-Source-System"
    assert MAKE_RUN_ID_HEADER == "X-Make-Run-Id"
    assert REQUEST_ID_HEADER == "X-Request-Id"
