"""
Shared security helpers for the James Joseph Associates intelligence API.

This module contains small utilities for reading and validating API
authorisation metadata.

It gives the rest of the repository a stable way to talk about:

- `Authorization` headers
- bearer tokens
- missing credentials
- malformed credentials
- future Make.com API access
- future internal admin API access

Keeping security helpers in one place makes the project easier to extend because:

- endpoint modules do not need to repeat authentication parsing logic
- Make.com integration can use the same authentication shape everywhere
- future protected routes can share the same error behaviour
- tests can verify security behaviour without needing real business endpoints

In plain language:

- this module answers the question:

    "Did this request provide usable API credentials?"

- it does not define API routes
- it does not connect to Supabase
- it does not validate users in a database
- it does not implement a full login system
- it does not decide route-level permissions yet

Notes
-----
- This is a foundation module, not a complete authentication system.
- The first likely protected caller is Make.com.
- A simple bearer-token approach is enough for the early backend foundation.
- Later, this module can grow to support user sessions, JWTs, API keys, service
  accounts, or role-based permissions.
- Token comparison should use constant-time comparison so timing differences do
  not leak useful information.
"""

from dataclasses import dataclass
from enum import StrEnum
from secrets import compare_digest

from fastapi import Request

AUTHORIZATION_HEADER = "Authorization"
BEARER_AUTH_SCHEME = "Bearer"


class SecurityFailureReason(StrEnum):
    """
    Machine-readable reason why request credentials could not be accepted.

    Attributes
    ----------
    MISSING_AUTHORIZATION_HEADER : str
        No `Authorization` header was provided.

    MALFORMED_AUTHORIZATION_HEADER : str
        The `Authorization` header was present but did not match the expected
        bearer-token format.

    UNSUPPORTED_AUTH_SCHEME : str
        The `Authorization` header used a scheme other than `Bearer`.

    EMPTY_BEARER_TOKEN : str
        The header used the `Bearer` scheme but did not include a token.

    INVALID_BEARER_TOKEN : str
        The provided bearer token did not match the expected token.

    Notes
    -----
    - These values are internal helper reasons.
    - They are not necessarily the exact public API error codes returned to
      clients.
    - Public API error codes should still use the shared error schema, such as
      `unauthorized` or `forbidden`.

    In plain language:

    - this enum gives tests and future handlers a precise reason for auth failure
    """

    MISSING_AUTHORIZATION_HEADER = "missing_authorization_header"
    MALFORMED_AUTHORIZATION_HEADER = "malformed_authorization_header"
    UNSUPPORTED_AUTH_SCHEME = "unsupported_auth_scheme"
    EMPTY_BEARER_TOKEN = "empty_bearer_token"
    INVALID_BEARER_TOKEN = "invalid_bearer_token"


@dataclass(frozen=True, slots=True)
class BearerCredentials:
    """
    Parsed bearer-token credentials from an HTTP request.

    Attributes
    ----------
    scheme : str
        Authentication scheme from the `Authorization` header.

        For the first implementation, this should be:

            Bearer

    token : str
        Bearer token value from the `Authorization` header.

    Notes
    -----
    - This object only represents parsed credentials.
    - It does not prove the token is valid.
    - Validation happens separately by comparing the parsed token with an
      expected token.

    Example
    -------
    This header:

        Authorization: Bearer example-token

    becomes:

        BearerCredentials(
            scheme="Bearer",
            token="example-token",
        )

    In plain language:

    - split the header into the auth type and the secret value
    """

    scheme: str
    token: str


@dataclass(frozen=True, slots=True)
class SecurityCheckResult:
    """
    Result of checking bearer-token credentials.

    Attributes
    ----------
    is_authorised : bool
        Whether the request credentials were accepted.

    reason : SecurityFailureReason | None
        Reason the request was rejected.

        This is `None` when `is_authorised` is `True`.

    credentials : BearerCredentials | None
        Parsed bearer credentials when parsing succeeded.

        This may still be present even if the token itself was invalid.

    Notes
    -----
    - Returning a structured result is useful while the security foundation is
      still small.
    - Endpoint code can later convert failed results into standard API errors.
    - Tests can assert precise failure reasons without needing to parse exception
      messages.

    In plain language:

    - either auth passed
    - or auth failed with a clear reason
    """

    is_authorised: bool
    reason: SecurityFailureReason | None = None
    credentials: BearerCredentials | None = None


def normalise_authorization_header(value: str | None) -> str | None:
    """
    Convert a raw `Authorization` header into a clean optional string.

    Parameters
    ----------
    value : str | None
        Raw header value read from the incoming request.

        FastAPI returns `None` when the header is missing.

    Returns
    -------
    str | None
        Cleaned header value.

        The return value is:

        - a stripped string when the header contains useful text
        - `None` when the header is missing
        - `None` when the header contains only whitespace

    Notes
    -----
    - This follows the same pattern as the HTTP metadata helpers.
    - Empty credentials should be treated as missing credentials.
    - This helper does not parse the bearer scheme or token yet.

    Example
    -------
    These values become useful strings:

        " Bearer abc " -> "Bearer abc"
        "Bearer abc"   -> "Bearer abc"

    These values become `None`:

        None
        ""
        "   "

    In plain language:

    - remove accidental whitespace
    - treat empty values as missing
    """

    # Missing headers should remain missing.
    #   - FastAPI returns `None` when a header is not present.
    #   - Keeping that as `None` lets callers identify the missing-auth case.
    if value is None:
        return None

    # Trim accidental whitespace from the full header.
    #   - This handles values like `" Bearer abc "` without changing the token
    #     itself beyond edge whitespace.
    normalised_value = value.strip()

    # Empty strings should not count as credentials.
    #   - A header containing only spaces should behave like no header.
    if normalised_value == "":
        return None

    return normalised_value


def parse_bearer_credentials(
    authorization_header: str | None,
) -> BearerCredentials | SecurityFailureReason:
    """
    Parse bearer-token credentials from an `Authorization` header.

    Parameters
    ----------
    authorization_header : str | None
        Raw or normalised `Authorization` header value.

    Returns
    -------
    BearerCredentials | SecurityFailureReason
        Parsed credentials when the header is valid enough to parse.

        A failure reason is returned when the header is missing, malformed, uses
        an unsupported auth scheme, or contains an empty bearer token.

    Expected format
    ---------------
    The expected header format is:

        Authorization: Bearer <token>

    Example
    -------
    This input:

        "Bearer make-secret-token"

    returns:

        BearerCredentials(
            scheme="Bearer",
            token="make-secret-token",
        )

    This input:

        "Basic abc"

    returns:

        SecurityFailureReason.UNSUPPORTED_AUTH_SCHEME

    Notes
    -----
    - This function only parses credentials.
    - It does not decide whether the token is correct.
    - Token validation happens in `check_bearer_token`.

    In plain language:

    - read the auth header
    - check it looks like `Bearer something`
    - return the token or explain why it cannot be used
    """

    normalised_header = normalise_authorization_header(authorization_header)

    if normalised_header is None:
        return SecurityFailureReason.MISSING_AUTHORIZATION_HEADER

    # A bare `Bearer` value tells us the caller knew the expected scheme but did
    # not send a token.
    #   - Treating this separately gives future API errors a more precise reason.
    if normalised_header.lower() == BEARER_AUTH_SCHEME.lower():
        return SecurityFailureReason.EMPTY_BEARER_TOKEN

    # Split into two parts only:
    #
    #   Bearer <token>
    #
    # `maxsplit=1` matters because some token formats may contain additional
    # separators internally. We only care about the first space between the auth
    # scheme and the token value.
    parts = normalised_header.split(maxsplit=1)

    if len(parts) != 2:
        return SecurityFailureReason.MALFORMED_AUTHORIZATION_HEADER

    scheme, token = parts
    token = token.strip()

    if scheme.lower() != BEARER_AUTH_SCHEME.lower():
        return SecurityFailureReason.UNSUPPORTED_AUTH_SCHEME

    if token == "":
        return SecurityFailureReason.EMPTY_BEARER_TOKEN

    return BearerCredentials(
        scheme=BEARER_AUTH_SCHEME,
        token=token,
    )


def tokens_match(provided_token: str, expected_token: str) -> bool:
    """
    Compare two bearer tokens safely.

    Parameters
    ----------
    provided_token : str
        Token supplied by the request.

    expected_token : str
        Token expected by the backend.

    Returns
    -------
    bool
        `True` when the tokens match.

        `False` when they do not match.

    Notes
    -----
    - This uses `secrets.compare_digest`.
    - Constant-time comparison helps avoid timing leaks.
    - This helper assumes both inputs are already strings.
    - Empty expected tokens should not be treated as valid configuration.

    In plain language:

    - compare the submitted token with the configured token
    - do it in a safer way than plain `==`
    """

    # Empty configured tokens should never authorise requests.
    #   - If the expected token is empty, the app is not configured to accept
    #     bearer auth safely.
    if expected_token == "":
        return False

    return compare_digest(provided_token, expected_token)


def check_bearer_token(
    authorization_header: str | None,
    expected_token: str,
) -> SecurityCheckResult:
    """
    Check whether an `Authorization` header contains the expected bearer token.

    Parameters
    ----------
    authorization_header : str | None
        Raw `Authorization` header value.

    expected_token : str
        Token value the backend expects.

        In a real endpoint, this would usually come from settings or secret
        configuration.

    Returns
    -------
    SecurityCheckResult
        Structured result describing whether the request is authorised.

    Notes
    -----
    - This function does not read directly from a FastAPI request.
    - That makes it easy to unit test.
    - `check_request_bearer_token` wraps this function for request objects.
    - Failed checks return a reason instead of raising an exception.
    - Endpoint or exception-handler code can later convert the reason into a
      standard API error response.

    In plain language:

    - parse the auth header
    - compare the token
    - return pass/fail with a clear reason
    """

    credentials_or_reason = parse_bearer_credentials(authorization_header)

    # If parsing failed, return an unauthorised result with the exact reason.
    #   - Examples include missing header, wrong scheme, or malformed value.
    if isinstance(credentials_or_reason, SecurityFailureReason):
        return SecurityCheckResult(
            is_authorised=False,
            reason=credentials_or_reason,
        )

    credentials = credentials_or_reason

    # The header was parseable, so now check whether the supplied token matches
    # the backend's configured token.
    if not tokens_match(
        provided_token=credentials.token,
        expected_token=expected_token,
    ):
        return SecurityCheckResult(
            is_authorised=False,
            reason=SecurityFailureReason.INVALID_BEARER_TOKEN,
            credentials=credentials,
        )

    return SecurityCheckResult(
        is_authorised=True,
        credentials=credentials,
    )


def check_request_bearer_token(
    request: Request,
    expected_token: str,
) -> SecurityCheckResult:
    """
    Check bearer-token credentials on a FastAPI request object.

    Parameters
    ----------
    request : Request
        FastAPI request object.

    expected_token : str
        Token value the backend expects.

    Returns
    -------
    SecurityCheckResult
        Structured result describing whether the request is authorised.

    Notes
    -----
    - This helper reads the `Authorization` header from the request.
    - It delegates parsing and comparison to `check_bearer_token`.
    - Keeping request-reading separate from token-checking makes the core logic
      easier to test.

    Example
    -------
    A protected endpoint might eventually do:

        result = check_request_bearer_token(
            request=request,
            expected_token=settings.make_api_token,
        )

        if not result.is_authorised:
            ...

    In plain language:

    - read `Authorization` from the request
    - check whether it contains the expected bearer token
    """

    # Read the raw `Authorization` header from FastAPI.
    #   - Header lookup is case-insensitive.
    #   - Missing headers return `None`.
    authorization_header = request.headers.get(AUTHORIZATION_HEADER)

    return check_bearer_token(
        authorization_header=authorization_header,
        expected_token=expected_token,
    )


__all__ = [
    "AUTHORIZATION_HEADER",
    "BEARER_AUTH_SCHEME",
    "BearerCredentials",
    "SecurityCheckResult",
    "SecurityFailureReason",
    "check_bearer_token",
    "check_request_bearer_token",
    "normalise_authorization_header",
    "parse_bearer_credentials",
    "tokens_match",
]
