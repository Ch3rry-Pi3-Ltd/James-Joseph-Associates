"""
Unit tests for shared security helper functions.

These tests check the bearer-token utilities in the `backend.core.security`.

The important question is:

    "Can the backend consistency understand and check API credentials?"

That matters because future Make.com-facing endpoints should not be open to anyone on the internet.

These tests do not call real API routes.

They test the helper functions directly:

    normalise_authorization_head(...)
    parse_bearer_credentials(...)
    tokens_match(...)
    check_bearer_tokens(...)
    check_request_bearer_token(...)

The expected behaviour is:

- missing credentials are rejected
- blank credentials are rejected
- makformed credentials are rejected
- non-bearer auth schemes are rejected
- bearer tokens are parsed consistently
- invalid tokens are rejected
- valid tokens are accepted

In plain language:

- this file checks the small security helper tools
- it does not implement login
- it does not connect to Supabase
- it does not call Make.com
- it prepares the backend for protected routes later
"""

from fastapi import Request

from backend.core.security import (
    AUTHORIZATION_HEADER,
    BEARER_AUTH_SCHEME,
    BearerCredentials,
    SecurityFailureReason,
    check_bearer_token,
    check_request_bearer_token,
    normalise_authorization_header,
    parse_bearer_credentials,
    tokens_match,
)

def make_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """
    Build a minimal FastAPI object for security helper tests.

    The helper functions in `backend.core.security` expect a FastAPI `Request`
    object when checking request-level bearer tokens.

    These tests do not need a real server or real route. They only need a
    request object with headers attached.

    Parameters
    ----------
    headers : list[tuple[bytes, bytes]] | None
        Optional ASGI-style request headers.

        ASGI stores headers as byte pairs:

            (header_name, header_value)

        For example:

            (b"authorization", b"Bearer secret-token")

    Returns
    -------
    Request
        Minimal FastAPI request object containing the supplied headers.

    Notes
    -----
    - This does not start Uvicorn.
    - This does not call the real app.
    - This does not send a network request.
    - It only creates enough request structure for auth-header tests.

    In plain language:

    - build a fake request
    - attach fake auth headers
    - pass it into the security helper functions
    """

    # FastAPI's `Request` object is built from an ASGI scope
    #   - The scope is a dictionary describing the incoming request.
    #   - For these tests, we only need the request type, method, path, and
    #     headers.
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/protected-example",
            "headers": headers or [],
        }
    )

def test_normalise_authorization_header_returns_non_for_missing_value() -> None:
    """
    Verify that a missing `Authorization` header stays missing.

    FastAPI returns `None` when a header is not present on the request.

    Notes
    -----
    - Missing credentials should not become an empty string.
    - Returning `None` makes it clear that the client did not provide auth.
    - The parser later turns this into a precise missing-header reason.
    """

    assert normalise_authorization_header(None) is None

def test_normalise_authorization_header_returns_none_for_blank_value() -> None:
    """
    Verify that blank auth header values are treated as missing.

    A client can accidentally send the header name without useful content.

    For example:

        Authorization:

    Notes
    -----
    - Empty strings are not usable credentials.
    - Whitespace-only strings are not usable credentials.
    - Both should become `None`.
    """

    assert normalise_authorization_header("") is None
    assert normalise_authorization_header("   ") is None

def test_normalise_authorization_header_trims_useful_text() -> None:
    """
    Verify that useful auth header text is stripped of surrounding whitespace.

    Clients or workflow tools may accidentally add spaces around header values.

    For example:

        Authorization:  Bearer secret-token 

    Notes
    -----
    - The useful value is `Bearer secret-token`.
    - Leading and trailing spaces are not meaningful.
    - The helper should clean the value before parsing it.
    """

    assert (
        normalise_authorization_header(" Bearer secret-token ")
        == "Bearer secret-token"
    )

def test_parse_bearer_credentials_rejects_missing_header() -> None:
    """
    Verify that missing credentials return a missing-header reason.

    Notes
    -----
    - Protected routes will eventually use this reason to return `unauthorized`.
    - The helper returns a structured reason rather than raising an exception.
    """

    result = parse_bearer_credentials(None)

    assert result == SecurityFailureReason.MISSING_AUTHORIZATION_HEADER

def test_parse_bearer_credentials_rejects_malformed_header() -> None:
    """
    Verify that malformed credentials are rejected.

    The expected format is:

        Bearer <token>

    A single random string does not contain both parts.

    In plain language:

    - the header exists
    - but it does not look like an auth scheme plus token
    """

    result = parse_bearer_credentials("not-a-bearer-header")

    assert result == SecurityFailureReason.MALFORMED_AUTHORIZATION_HEADER

def test_parse_bearer_credentials_rejects_unsupported_auth_scheme() -> None:
    """
    Verify that non-bearer authentication schemes are rejected.

    For example:

        Basic abc123

    is not the same as:

        Bearer abc123

    Notes
    -----
    - Early Make.com integration should use bearer-token auth.
    - Other auth schemes can be considered later if needed.
    """

    result = parse_bearer_credentials("Basic abc123")

    assert result == SecurityFailureReason.UNSUPPORTED_AUTH_SCHEME

def test_parse_bearer_credentials_rejects_empty_bearer_token() -> None:
    """
    Verify that a bare `Bearer` header is rejected.

    This header tells us the caller used the expected scheme but did not include
    an actual token:

        Authorization: Bearer

    In plain language:

    - the auth type is present
    - the secret value is missing
    """

    result = parse_bearer_credentials("Bearer")

    assert result == SecurityFailureReason.EMPTY_BEARER_TOKEN

def test_parse_bearer_credentials_returns_credentials_for_valid_header() -> None:
    """
    Verify that a valid bearer header is parsed into credentials.

    Notes
    -----
    - The returned scheme is normalised to `Bearer`.
    - The returned token is the value after the scheme.
    - This does not prove the token is correct yet.
    """

    result = parse_bearer_credentials("Bearer make-secret-token")

    assert result == BearerCredentials(
        scheme="Bearer",
        token="make-secret-token",
    )

def test_parse_bearer_credentials_accepts_case_insensitive_scheme() -> None:
    """
    Verify that the bearer scheme is parsed case-insensitively.

    HTTP auth schemes are commonly treated case-insensitively.

    These should all mean the same scheme:

        Bearer
        bearer
        BEARER

    The helper should still return the canonical `Bearer` scheme internally.
    """

    result = parse_bearer_credentials("bearer make-secret-token")

    assert result == BearerCredentials(
        scheme="Bearer",
        token="make-secret-token",
    )

def test_parse_bearer_credentials_trims_token_edges() -> None:
    """
    Verify that accidental whitespace around the token is removed.

    Notes
    -----
    - Make.com or manual testing may accidentally add extra spaces.
    - Edge whitespace should not become part of the token value.
    """

    result = parse_bearer_credentials("Bearer   make-secret-token   ")

    assert result == BearerCredentials(
        scheme="Bearer",
        token="make-secret-token",
    )

def test_tokens_match_returns_true_for_matching_tokens() -> None:
    """
    Verify that matching tokens are accepted by the comparison helper.

    Notes
    -----
    - This test checks the small token comparison helper directly.
    - The helper uses constant-time comparison internally.
    """

    assert tokens_match(
        provided_token="make-secret-token",
        expected_token="make-secret-token",
    )

def test_tokens_match_returns_false_for_different_tokens() -> None:
    """
    Verify that different tokens are rejected.

    In plain language:

    - the caller sent a token
    - it was not the configured token
    - the request should not be authorised
    """

    assert not tokens_match(
        provided_token="wrong-token",
        expected_token="make-secret-token",
    )

def test_tokens_match_returns_false_for_empty_expected_token() -> None:
    """
    Verify that an empty configured token never authorises a request.

    Notes
    -----
    - An empty expected token means the backend is not safely configured.
    - This should fail closed rather than accidentally accepting requests.
    """

    assert not tokens_match(
        provided_token="anything",
        expected_token="",
    )

def test_check_bearer_token_returns_failure_for_invalid_token() -> None:
    """
    Verify that a parseable but incorrect token is rejected.

    Notes
    -----
    - The credentials can still be parsed.
    - The token comparison fails.
    - The result should include `INVALID_BEARER_TOKEN`.
    """

    result = check_bearer_token(
        authorization_header="Bearer wrong-token",
        expected_token="make-secret-token",
    )

    assert not result.is_authorised
    assert result.reason == SecurityFailureReason.INVALID_BEARER_TOKEN
    assert result.credentials == BearerCredentials(
        scheme="Bearer",
        token="wrong-token",
    )

def test_check_bearer_token_returns_success_for_valid_token() -> None:
    """
    Verify that the expected bearer token is authorised.

    In plain language:

    - the header is shaped correctly
    - the token matches the configured value
    - the request can be treated as authorised
    """

    result = check_bearer_token(
        authorization_header="Bearer make-secret-token",
        expected_token="make-secret-token",
    )

    assert result.is_authorised
    assert result.reason is None
    assert result.credentials == BearerCredentials(
        scheme="Bearer",
        token="make-secret-token",
    )

def test_check_request_bearer_token_reads_authorization_header() -> None:
    """
    Verify that request-level bearer checks read the `Authorization` header.

    This test checks the wrapper that accepts a FastAPI `Request`.

    Notes
    -----
    - Real protected endpoints will receive a `Request` object from FastAPI.
    - This helper reads the header and delegates to `check_bearer_token`.
    """

    request = make_request(
        headers=[
            (b"authorization", b"Bearer make-secret-token"),
        ]
    )

    result = check_request_bearer_token(
        request=request,
        expected_token="make-secret-token",
    )

    assert result.is_authorised
    assert result.reason is None

def test_check_request_bearer_token_reports_missing_header() -> None:
    """
    Verify that request-level checks report a missing auth header.

    In plain language:

    - the request has no `Authorization` header
    - the security helper rejects it with a clear reason
    """

    request = make_request()

    result = check_request_bearer_token(
        request=request,
        expected_token="make-secret-token",
    )

    assert not result.is_authorised
    assert result.reason == SecurityFailureReason.MISSING_AUTHORIZATION_HEADER

def test_security_constants_match_public_header_names() -> None:
    """
    Verify that security constants keep the expected public names.

    These constants are small, but they matter because future endpoints and tests
    should use the same names everywhere.

    Notes
    -----
    - `Authorization` is the standard HTTP auth header.
    - `Bearer` is the scheme Make.com should send for protected backend calls.
    """

    assert AUTHORIZATION_HEADER == "Authorization"
    assert BEARER_AUTH_SCHEME == "Bearer"