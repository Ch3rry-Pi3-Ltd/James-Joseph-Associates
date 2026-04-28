"""
JobAdder OAuth helper functions for the intelligence backend.

This module contains small helper functions for the three early JobAdder OAuth
steps:

- building the JobAdder approval URL
- exchanging a one-time authorisation code for tokens
- refreshing an expired access token using the stored refresh token

It gives the rest of the repository a stable way to talk about:

- which JobAdder OAuth base URL we send users to
- which form fields are required for the token-exchange step
- which form fields are required for the refresh-token step
- how the backend can validate that the minimum settings exist before trying to
  start or continue the OAuth flow
- how JobAdder token responses should be represented in Python
- how the backend can decide whether a stored access token is expired

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to hand-build long URLs or token payloads
- OAuth-specific rules stay near each other
- tests can target one small helper module at a time
- later refresh scheduling or background maintenance can build on these helpers

In plain language:

- this module answers the questions:

    "How does the backend build the JobAdder approval link?"
    "How does the backend swap a JobAdder code for tokens?"
    "How does the backend refresh an expired access token?"

- it does not define API routes
- it does not store tokens
- it does not create database records
- it only handles the OAuth helper logic itself
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from backend.settings import get_settings

JOBADDER_AUTHORIZE_URL = "https://id.jobadder.com/connect/authorize"
JOBADDER_TOKEN_URL = "https://id.jobadder.com/connect/token"


@dataclass(frozen=True)
class JobAdderTokenSet:
    """
    Normalised token response returned by JobAdder after a successful exchange
    or refresh.

    Attributes
    ----------
    access_token : str
        Short-lived bearer token used for authenticated JobAdder API calls.

    token_type : str
        OAuth token type returned by JobAdder.

        In practice, this is expected to be `Bearer`, but the backend should
        read the returned value rather than hard-code it.

    expires_in : int
        Token lifetime in seconds.

    refresh_token : str | None
        Longer-lived token used to request a new access token later.

    scope : str | None
        Scope string returned by the provider, if present.

    raw_payload : dict[str, Any]
        Full decoded provider payload.

        Keeping the raw payload available is useful for later debugging and for
        future fields JobAdder may add that we do not yet model explicitly.

    Notes
    -----
    - This object is internal backend data, not a public API response model.
    - It is intentionally small but keeps the raw payload so we do not lose
      provider information too early.
    """

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    scope: str | None
    raw_payload: dict[str, Any]


class JobAdderOAuthExchangeError(RuntimeError):
    """
    Raised when the backend cannot complete the JobAdder token exchange or
    refresh safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code : int | None
        HTTP status code returned by JobAdder, if a provider response existed.

    provider_error : str | None
        Provider-level OAuth error code, if JobAdder returned one.

    provider_error_description : str | None
        Provider-level human-readable error description, if present.

    response_body : dict[str, Any] | None
        Safe decoded provider response body when available.

    Notes
    -----
    - This exception is meant for backend control flow.
    - Route handlers can catch it later and convert it into the project's normal
      API error shape.
    - It should not carry secrets.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_error: str | None = None,
        provider_error_description: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider_error = provider_error
        self.provider_error_description = provider_error_description
        self.response_body = response_body

    def __str__(self) -> str:
        """
        Return the human-readable error message.

        In plain language:

        - when this exception is printed
        - show the main message
        """

        return self.message


def has_jobadder_oauth_configuration() -> bool:
    """
    Return whether the minimum JobAdder OAuth settings are present.

    Returns
    -------
    bool
        `True` when the backend has the minimum values needed to start the OAuth
        approval flow.

        `False` when one or more required settings are missing or empty.

    Notes
    -----
    - This check is intentionally narrow.
    - To build the authorisation URL, we only need:
      - `JOBADDER_CLIENT_ID`
      - `JOBADDER_REDIRECT_URI`
    - The client secret is not needed until the token-exchange or refresh step.

    In plain language:

    - check whether we have enough config
    - return true or false
    """

    settings = get_settings()

    return (
        settings.jobadder_client_id.strip() != ""
        and settings.jobadder_redirect_uri.strip() != ""
    )


def has_jobadder_token_exchange_configuration() -> bool:
    """
    Return whether the backend has enough configuration to exchange or refresh
    tokens.

    Returns
    -------
    bool
        `True` when the backend has all values required for the server-side
        token exchange and refresh steps.

        `False` when one or more required settings are missing or empty.

    Notes
    -----
    - This check is stricter than `has_jobadder_oauth_configuration()`.
    - The token-exchange and refresh steps need:

        - `JOBADDER_CLIENT_ID`
        - `JOBADDER_CLIENT_SECRET`
        - `JOBADDER_REDIRECT_URI`

    In plain language:

    - building the login link needs fewer settings
    - swapping the code for tokens or refreshing them needs all three
    """

    settings = get_settings()

    return all(
        [
            settings.jobadder_client_id.strip() != "",
            settings.jobadder_client_secret.strip() != "",
            settings.jobadder_redirect_uri.strip() != "",
        ]
    )


def build_jobadder_authorization_url(
    *,
    state: str | None = None,
    scope: str = "read write offline_access",
) -> str:
    """
    Build the JobAdder OAuth authorisation URL.

    Parameters
    ----------
    state : str | None
        Optional opaque value that JobAdder should send back unchanged in the
        callback.

    scope : str
        Space-separated OAuth scopes to request.

    Returns
    -------
    str
        Fully assembled JobAdder authorisation URL.

    Raises
    ------
    ValueError
        If the minimum JobAdder OAuth settings are missing.

    Notes
    -----
    - This function does not call JobAdder.
    - It only constructs the URL the client-side approver will visit.
    - The redirect URI is URL-encoded automatically through `urlencode(...)`.

    In plain language:

    - take the known settings
    - add the OAuth query parameters
    - return the final approval link
    """

    settings = get_settings()

    client_id = settings.jobadder_client_id.strip()
    redirect_uri = settings.jobadder_redirect_uri.strip()

    if client_id == "" or redirect_uri == "":
        raise ValueError(
            "JobAdder OAuth is not configured. "
            "Set JOBADDER_CLIENT_ID and JOBADDER_REDIRECT_URI."
        )

    query_params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
    }

    if state is not None and state.strip() != "":
        query_params["state"] = state

    encoded_query = urlencode(query_params, quote_via=quote)

    return f"{JOBADDER_AUTHORIZE_URL}?{encoded_query}"


def build_jobadder_token_exchange_payload(*, code: str) -> dict[str, str]:
    """
    Build the form payload required for the JobAdder token endpoint when
    exchanging an authorisation code.

    Parameters
    ----------
    code : str
        One-time authorisation code returned by JobAdder after approval.

    Returns
    -------
    dict[str, str]
        Form fields expected by the JobAdder token endpoint.

    Raises
    ------
    ValueError
        If the backend is missing required configuration or the code is blank.

    In plain language:

    - take the one-time code and backend settings
    - build the form data JobAdder expects
    """

    settings = get_settings()

    client_id = settings.jobadder_client_id.strip()
    client_secret = settings.jobadder_client_secret.strip()
    redirect_uri = settings.jobadder_redirect_uri.strip()
    cleaned_code = code.strip()

    if cleaned_code == "":
        raise ValueError("JobAdder authorization code cannot be empty.")

    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "JobAdder token exchange is not configured. "
            "Set JOBADDER_CLIENT_ID, JOBADDER_CLIENT_SECRET, and "
            "JOBADDER_REDIRECT_URI."
        )

    return {
        "grant_type": "authorization_code",
        "code": cleaned_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def build_jobadder_refresh_token_payload(*, refresh_token: str) -> dict[str, str]:
    """
    Build the form payload required for the JobAdder token endpoint when
    refreshing an expired access token.

    Parameters
    ----------
    refresh_token : str
        Stored JobAdder refresh token.

    Returns
    -------
    dict[str, str]
        Form fields expected by the JobAdder token endpoint.

    Raises
    ------
    ValueError
        If the backend is missing required configuration or the refresh token is
        blank.

    Notes
    -----
    - JobAdder's OAuth docs show refresh requests using:
        - `grant_type=refresh_token`
        - `client_id`
        - `client_secret`
        - `refresh_token`
    - The redirect URI is not needed for the refresh grant.

    In plain language:

    - take the stored refresh token and backend settings
    - build the form data JobAdder expects for token refresh
    """

    settings = get_settings()

    client_id = settings.jobadder_client_id.strip()
    client_secret = settings.jobadder_client_secret.strip()
    redirect_uri = settings.jobadder_redirect_uri.strip()
    cleaned_refresh_token = refresh_token.strip()

    if cleaned_refresh_token == "":
        raise ValueError("JobAdder refresh token cannot be empty.")

    # Keep the configuration requirement aligned with the rest of the OAuth
    # helper surface.
    #   - Even though the refresh request itself does not need the redirect URI,
    #     this backend treats the full OAuth configuration as one coherent unit.
    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "JobAdder token refresh is not configured. "
            "Set JOBADDER_CLIENT_ID, JOBADDER_CLIENT_SECRET, and "
            "JOBADDER_REDIRECT_URI."
        )

    return {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": cleaned_refresh_token,
    }


def exchange_jobadder_authorization_code(
    *,
    code: str,
    timeout_seconds: float = 30.0,
) -> JobAdderTokenSet:
    """
    Exchange a one-time JobAdder authorisation code for tokens.

    Parameters
    ----------
    code : str
        One-time authorisation code returned by JobAdder.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    JobAdderTokenSet
        Normalised token response returned by JobAdder.

    Raises
    ------
    ValueError
        If the code is blank or the backend is missing required settings.

    JobAdderOAuthExchangeError
        If JobAdder rejects the request, returns an invalid response, or cannot
        be reached safely.

    In plain language:

    - receive the one-time code
    - send it to JobAdder from the backend
    - get tokens back
    - return them in a normal Python shape
    """

    payload = build_jobadder_token_exchange_payload(code=code)

    return _request_jobadder_token_set(
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder token exchange failed.",
    )


def refresh_jobadder_access_token(
    *,
    refresh_token: str,
    timeout_seconds: float = 30.0,
) -> JobAdderTokenSet:
    """
    Refresh an expired JobAdder access token using the stored refresh token.

    Parameters
    ----------
    refresh_token : str
        Stored JobAdder refresh token.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    JobAdderTokenSet
        Normalised token response returned by JobAdder.

    Raises
    ------
    ValueError
        If the refresh token is blank or the backend is missing required
        settings.

    JobAdderOAuthExchangeError
        If JobAdder rejects the refresh request, returns an invalid response, or
        cannot be reached safely.

    Why this helper exists
    ----------------------
    JobAdder access tokens expire after 60 minutes. The refresh token exists so
    the backend can obtain a new access token without forcing the client to
    repeat the full approval flow every hour.

    In plain language:

    - take the stored refresh token
    - ask JobAdder for a new access token
    - return the new token set in the same shape as the original exchange
    """

    # Build the refresh-grant payload separately from the HTTP request.
    #   - That keeps the grant-type-specific field rules testable on their own.
    #   - It also keeps the public helper readable: one step to build the
    #     payload, one step to send it.
    payload = build_jobadder_refresh_token_payload(refresh_token=refresh_token)

    return _request_jobadder_token_set(
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider_failure_message="JobAdder token refresh failed.",
    )


def is_jobadder_access_token_expired(
    *,
    obtained_at: datetime | str | None,
    expires_in_seconds: int | None,
    safety_window_seconds: int = 60,
) -> bool:
    """
    Return whether a stored JobAdder access token should be treated as expired.

    Parameters
    ----------
    obtained_at : datetime | str | None
        Timestamp recording when the token set was obtained.

        This may be a database `datetime`, an ISO string, or `None`.

    expires_in_seconds : int | None
        Stored token lifetime in seconds.

    safety_window_seconds : int
        Number of seconds to subtract from the nominal expiry time.

        This gives the backend a small buffer so it refreshes slightly before
        the exact expiry point rather than racing it.

    Returns
    -------
    bool
        `True` when the token should be treated as expired or unreliable.

        `False` when the token is still comfortably valid.

    Notes
    -----
    - If the backend cannot parse the stored timing data safely, this helper
      returns `True`.
    - Failing closed is the correct behaviour here because attempting an API
      read with a likely-expired token only adds noise and latency.

    In plain language:

    - work out when the token should expire
    - subtract a small safety margin
    - decide whether the backend should refresh before making an API call
    """

    if safety_window_seconds < 0:
        raise ValueError(
            "JobAdder token expiry safety_window_seconds cannot be negative."
        )

    obtained_at_dt = _normalise_datetime(obtained_at)

    if obtained_at_dt is None or expires_in_seconds is None:
        return True

    try:
        cleaned_expires_in_seconds = int(expires_in_seconds)
    except (TypeError, ValueError):
        return True

    expiry_time = obtained_at_dt + timedelta(seconds=cleaned_expires_in_seconds)
    refresh_cutoff = expiry_time - timedelta(seconds=safety_window_seconds)

    return datetime.now(timezone.utc) >= refresh_cutoff


def _request_jobadder_token_set(
    *,
    payload: dict[str, str],
    timeout_seconds: float,
    provider_failure_message: str,
) -> JobAdderTokenSet:
    """
    Send one token-endpoint request to JobAdder and normalise the token result.

    Parameters
    ----------
    payload : dict[str, str]
        Form fields to send to the JobAdder token endpoint.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when JobAdder returns an HTTP error response.

    Returns
    -------
    JobAdderTokenSet
        Normalised token response returned by JobAdder.

    Raises
    ------
    JobAdderOAuthExchangeError
        If JobAdder rejects the request, returns an invalid response, or cannot
        be reached safely.

    Notes
    -----
    - This private helper is shared by both:
        - the authorisation-code exchange path
        - the refresh-token path
    - Keeping the HTTP request and response-normalisation rules in one place
      prevents the two public helpers from drifting apart.
    """

    try:
        response = httpx.post(
            JOBADDER_TOKEN_URL,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise JobAdderOAuthExchangeError(
            "Could not reach the JobAdder token endpoint.",
        ) from exc

    response_payload = _decode_jobadder_json_response(response)

    if response.status_code >= 400:
        raise JobAdderOAuthExchangeError(
            provider_failure_message,
            status_code=response.status_code,
            provider_error=_safe_string(response_payload.get("error")),
            provider_error_description=_safe_string(
                response_payload.get("error_description")
            ),
            response_body=response_payload,
        )

    access_token = _safe_string(response_payload.get("access_token"))
    token_type = _safe_string(response_payload.get("token_type"))
    refresh_token = _safe_string(response_payload.get("refresh_token"))
    scope = _safe_string(response_payload.get("scope"))
    raw_expires_in = response_payload.get("expires_in")

    if access_token is None:
        raise JobAdderOAuthExchangeError(
            "JobAdder token response did not include an access token.",
            status_code=response.status_code,
            response_body=response_payload,
        )

    if token_type is None:
        raise JobAdderOAuthExchangeError(
            "JobAdder token response did not include a token type.",
            status_code=response.status_code,
            response_body=response_payload,
        )

    try:
        expires_in = int(raw_expires_in)
    except (TypeError, ValueError) as exc:
        raise JobAdderOAuthExchangeError(
            "JobAdder token response did not include a valid expires_in value.",
            status_code=response.status_code,
            response_body=response_payload,
        ) from exc

    return JobAdderTokenSet(
        access_token=access_token,
        token_type=token_type,
        expires_in=expires_in,
        refresh_token=refresh_token,
        scope=scope,
        raw_payload=response_payload,
    )


def _decode_jobadder_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a JobAdder response body into a dictionary.

    Parameters
    ----------
    response : httpx.Response
        Raw HTTP response from JobAdder.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object, or a small fallback dictionary when the response
        body was not valid JSON.

    Notes
    -----
    - The token endpoint is expected to return JSON.
    - If it does not, we still want safe debugging context rather than an
      unrelated JSON parsing exception.

    In plain language:

    - try to read JSON
    - if that fails, return a small fallback dictionary
    """

    try:
        decoded = response.json()
    except ValueError:
        return {
            "raw_text": response.text,
        }

    if isinstance(decoded, dict):
        return decoded

    return {
        "decoded_json": decoded,
    }


def _normalise_datetime(value: Any) -> datetime | None:
    """
    Convert a stored date/time value into a timezone-aware UTC datetime.

    Parameters
    ----------
    value : Any
        Raw value read from storage.

    Returns
    -------
    datetime | None
        Timezone-aware UTC datetime when parsing succeeds, otherwise `None`.

    Notes
    -----
    - Database reads will usually return real `datetime` objects.
    - Some tests or future callers may pass ISO strings instead.
    - If a datetime is naive, this helper treats it as UTC.

    In plain language:

    - accept a few realistic storage shapes
    - turn them into one consistent UTC datetime form
    - return none when the value cannot be trusted
    """

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    try:
        parsed_value = datetime.fromisoformat(cleaned_value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value.astimezone(timezone.utc)


def _safe_string(value: Any) -> str | None:
    """
    Convert a provider field into a stripped optional string.

    Parameters
    ----------
    value : Any
        Raw value read from the provider payload.

    Returns
    -------
    str | None
        Cleaned string value, or `None` when the provider field is missing or
        blank.

    Notes
    -----
    - OAuth providers sometimes return null, blank strings, or unexpected types.
    - This helper keeps the string-cleaning rule consistent inside this module.
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    return cleaned_value


__all__ = [
    "JOBADDER_AUTHORIZE_URL",
    "JOBADDER_TOKEN_URL",
    "JobAdderOAuthExchangeError",
    "JobAdderTokenSet",
    "build_jobadder_authorization_url",
    "build_jobadder_refresh_token_payload",
    "build_jobadder_token_exchange_payload",
    "exchange_jobadder_authorization_code",
    "has_jobadder_oauth_configuration",
    "has_jobadder_token_exchange_configuration",
    "is_jobadder_access_token_expired",
    "refresh_jobadder_access_token",
]
