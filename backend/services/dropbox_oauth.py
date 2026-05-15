"""
Dropbox OAuth helper functions for the intelligence backend.

This module contains the first small Dropbox OAuth helpers for the backend.

It gives the rest of the repository a stable way to talk about:

- building the Dropbox approval URL
- exchanging a one-time authorization code for tokens
- refreshing a short-lived access token with a stored refresh token
- checking whether the minimum Dropbox OAuth settings exist
- deciding whether a stored Dropbox token should be treated as expired

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to hand-build OAuth URLs
- Dropbox-specific OAuth rules stay together
- tests can target one small helper surface at a time
- later Dropbox file-ingestion work can build on a stable auth layer

Important implementation note
-----------------------------
Dropbox can support the same broad "send Tom to an approval URL and receive a
callback" pattern as JobAdder. However, Dropbox still requires one registered
app in the Dropbox App Console first so the backend has:

- an app key
- an app secret
- one or more exact redirect URIs

That means end users do not each need their own developer app, but the project
does still need one Dropbox app registration before OAuth can work.

Example
-------
Typical usage in the rest of the backend looks like:

    authorization_url = build_dropbox_authorization_url(state="connect-dropbox")
    token_set = exchange_dropbox_authorization_code(code="abc123")
    should_refresh = is_dropbox_access_token_expired(
        obtained_at="2026-05-15T12:00:00Z",
        expires_in_seconds=14400,
    )

In plain language:

- this module answers the questions:

    "How does the backend build the Dropbox approval link?"
    "How does the backend swap a Dropbox code for tokens?"
    "How does the backend refresh an expired Dropbox access token?"

- it does not define API routes
- it does not store tokens
- it does not fetch Dropbox files directly
- it only handles the OAuth helper logic itself
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from backend.settings import get_settings

DROPBOX_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DEFAULT_DROPBOX_SCOPE = (
    "account_info.read files.metadata.read files.content.read sharing.read"
)


@dataclass(frozen=True)
class DropboxTokenSet:
    """
    Normalized token response returned by Dropbox after a successful exchange or
    refresh.

    Attributes
    ----------
    access_token : str
        Short-lived bearer token used for authenticated Dropbox API calls.

    token_type : str
        OAuth token type returned by Dropbox.

    expires_in : int
        Token lifetime in seconds.

    refresh_token : str | None
        Long-lived refresh token returned when `token_access_type=offline` was
        requested.

    scope : str | None
        Scope string returned by Dropbox, if present.

    account_id : str | None
        Dropbox account identifier returned by the token response when the app
        is user-linked.

    raw_payload : dict[str, Any]
        Full decoded provider payload.

    Notes
    -----
    - This object is internal backend data, not a public API response model.
    - The raw payload is kept so future Dropbox-specific fields can be used
      later without changing the exchange path first.

    Example
    -------
    A successful token exchange may be represented as:

        DropboxTokenSet(
            access_token="...",
            token_type="bearer",
            expires_in=14400,
            refresh_token="...",
            scope="account_info.read files.metadata.read",
            account_id="dbid:AAExample",
            raw_payload={...},
        )
    """

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    scope: str | None
    account_id: str | None
    raw_payload: dict[str, Any]


class DropboxOAuthExchangeError(RuntimeError):
    """
    Raised when the backend cannot complete the Dropbox token exchange or
    refresh safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code : int | None
        HTTP status code returned by Dropbox, if a provider response existed.

    provider_error : str | None
        Provider-level OAuth error code, if Dropbox returned one.

    provider_error_description : str | None
        Provider-level human-readable error description, if present.

    response_body : dict[str, Any] | None
        Safe decoded provider response body when available.

    Notes
    -----
    - This exception is meant for backend control flow.
    - Route handlers can catch it and convert it into the project's normal API
      error contract.
    - It should not carry secrets.

    Example
    -------
    Callers may inspect:

        error.status_code
        error.provider_error
        error.provider_error_description

    to distinguish between:

    - invalid app credentials
    - expired or invalid authorization codes
    - revoked refresh tokens
    - malformed provider responses
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


def has_dropbox_oauth_configuration() -> bool:
    """
    Return whether the minimum Dropbox OAuth settings are present.

    Returns
    -------
    bool
        `True` when the backend has the minimum values needed to start the
        Dropbox OAuth approval flow.

        `False` when one or more required settings are missing or empty.

    Notes
    -----
    - To build the approval URL, the backend only needs:
      - `DROPBOX_CLIENT_ID`
      - `DROPBOX_REDIRECT_URI`
    - The app secret is not needed until the token-exchange or refresh step.

    Example
    -------
    If:

    - `DROPBOX_CLIENT_ID` is set
    - `DROPBOX_REDIRECT_URI` is set

    then this helper returns `True` even if the client secret is still missing.
    """

    settings = get_settings()

    return (
        settings.dropbox_client_id.strip() != ""
        and settings.dropbox_redirect_uri.strip() != ""
    )


def has_dropbox_token_exchange_configuration() -> bool:
    """
    Return whether the backend has enough configuration to exchange or refresh
    Dropbox tokens.

    Returns
    -------
    bool
        `True` when the backend has all values required for the server-side
        token exchange and refresh steps.

        `False` when one or more required settings are missing or empty.

    Notes
    -----
    - This check is stricter than `has_dropbox_oauth_configuration()`.
    - The token-exchange and refresh steps need:

        - `DROPBOX_CLIENT_ID`
        - `DROPBOX_CLIENT_SECRET`
        - `DROPBOX_REDIRECT_URI`

    Example
    -------
    This helper returns `False` if any one of these is blank:

    - client ID
    - client secret
    - redirect URI
    """

    settings = get_settings()

    return all(
        [
            settings.dropbox_client_id.strip() != "",
            settings.dropbox_client_secret.strip() != "",
            settings.dropbox_redirect_uri.strip() != "",
        ]
    )


def build_dropbox_authorization_url(
    *,
    state: str | None = None,
    scope: str = DEFAULT_DROPBOX_SCOPE,
    token_access_type: str = "offline",
) -> str:
    """
    Build the Dropbox OAuth authorization URL.

    Parameters
    ----------
    state : str | None
        Optional opaque value that Dropbox should send back unchanged in the
        callback.

    scope : str
        Space-separated Dropbox scopes to request.

    token_access_type : str
        Dropbox token access type to request.

        Use `offline` so the callback yields a refresh token that the backend
        can store for later background reads.

    Returns
    -------
    str
        Fully assembled Dropbox authorization URL.

    Raises
    ------
    ValueError
        If the minimum Dropbox OAuth settings are missing.

    Notes
    -----
    - This function does not call Dropbox.
    - It only constructs the URL Tom will visit to authorize the app.
    - The redirect URI is URL-encoded automatically through `urlencode(...)`.

    Example
    -------
    Calling:

        build_dropbox_authorization_url(state="connect-dropbox-dev")

    returns a URL of the form:

        https://www.dropbox.com/oauth2/authorize?response_type=code&...
    """

    settings = get_settings()

    client_id = settings.dropbox_client_id.strip()
    redirect_uri = settings.dropbox_redirect_uri.strip()

    if client_id == "" or redirect_uri == "":
        raise ValueError(
            "Dropbox OAuth is not configured. "
            "Set DROPBOX_CLIENT_ID and DROPBOX_REDIRECT_URI."
        )

    # Build the standard code-flow query first, then add optional values only
    # when they are present. That keeps the final URL small and avoids empty
    # query parameters whose intent is unclear later during debugging.
    query_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "token_access_type": token_access_type,
    }

    if state is not None and state.strip() != "":
        query_params["state"] = state

    encoded_query = urlencode(query_params, quote_via=quote)

    return f"{DROPBOX_AUTHORIZE_URL}?{encoded_query}"


def build_dropbox_token_exchange_payload(*, code: str) -> dict[str, str]:
    """
    Build the form payload required for Dropbox code exchange.

    Parameters
    ----------
    code : str
        One-time authorization code returned by Dropbox after approval.

    Returns
    -------
    dict[str, str]
        Form fields expected by the Dropbox token endpoint.

    Raises
    ------
    ValueError
        If the backend is missing required configuration or the code is blank.

    Example
    -------
    Calling:

        build_dropbox_token_exchange_payload(code="abc123")

    returns a form payload that includes:

    - `grant_type=authorization_code`
    - the one-time `code`
    - the configured client credentials
    - the configured redirect URI
    """

    settings = get_settings()

    client_id = settings.dropbox_client_id.strip()
    client_secret = settings.dropbox_client_secret.strip()
    redirect_uri = settings.dropbox_redirect_uri.strip()
    cleaned_code = code.strip()

    if cleaned_code == "":
        raise ValueError("Dropbox authorization code cannot be empty.")

    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "Dropbox token exchange is not configured. "
            "Set DROPBOX_CLIENT_ID, DROPBOX_CLIENT_SECRET, and "
            "DROPBOX_REDIRECT_URI."
        )

    return {
        "grant_type": "authorization_code",
        "code": cleaned_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def build_dropbox_refresh_token_payload(*, refresh_token: str) -> dict[str, str]:
    """
    Build the form payload required for Dropbox refresh-token exchange.

    Parameters
    ----------
    refresh_token : str
        Stored Dropbox refresh token.

    Returns
    -------
    dict[str, str]
        Form fields expected by the Dropbox token endpoint.

    Raises
    ------
    ValueError
        If the backend is missing required configuration or the refresh token
        is blank.

    Example
    -------
    Calling:

        build_dropbox_refresh_token_payload(refresh_token="refresh-123")

    returns a payload that includes:

    - `grant_type=refresh_token`
    - `client_id`
    - `client_secret`
    - `refresh_token`
    """

    settings = get_settings()

    client_id = settings.dropbox_client_id.strip()
    client_secret = settings.dropbox_client_secret.strip()
    redirect_uri = settings.dropbox_redirect_uri.strip()
    cleaned_refresh_token = refresh_token.strip()

    if cleaned_refresh_token == "":
        raise ValueError("Dropbox refresh token cannot be empty.")

    # Keep the configuration requirement aligned with the rest of the OAuth
    # helper surface so callers only need to learn one rule: exchanges and
    # refreshes require the full registered app configuration.
    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "Dropbox token refresh is not configured. "
            "Set DROPBOX_CLIENT_ID, DROPBOX_CLIENT_SECRET, and "
            "DROPBOX_REDIRECT_URI."
        )

    return {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": cleaned_refresh_token,
    }


def exchange_dropbox_authorization_code(
    *,
    code: str,
    timeout_seconds: float = 30.0,
) -> DropboxTokenSet:
    """
    Exchange a one-time Dropbox authorization code for tokens.

    Parameters
    ----------
    code : str
        One-time authorization code returned by Dropbox.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    DropboxTokenSet
        Normalized token response returned by Dropbox.

    Raises
    ------
    ValueError
        If the code is blank or the backend is missing required settings.

    DropboxOAuthExchangeError
        If Dropbox rejects the request, returns an invalid response, or cannot
        be reached safely.

    Example
    -------
    A successful call:

        exchange_dropbox_authorization_code(code="abc123")

    returns a `DropboxTokenSet` that can then be persisted in Postgres.
    """

    payload = build_dropbox_token_exchange_payload(code=code)

    return _request_dropbox_token_set(
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider_failure_message="Dropbox token exchange failed.",
    )


def refresh_dropbox_access_token(
    *,
    refresh_token: str,
    timeout_seconds: float = 30.0,
) -> DropboxTokenSet:
    """
    Refresh an expired Dropbox access token using the stored refresh token.

    Parameters
    ----------
    refresh_token : str
        Stored Dropbox refresh token.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    Returns
    -------
    DropboxTokenSet
        Normalized token response returned by Dropbox.

    Raises
    ------
    ValueError
        If the refresh token is blank or the backend is missing required
        settings.

    DropboxOAuthExchangeError
        If Dropbox rejects the refresh request, returns an invalid response, or
        cannot be reached safely.

    Notes
    -----
    - Dropbox uses short-lived access tokens by default.
    - Requesting `token_access_type=offline` during authorization allows the
      backend to refresh those tokens later without sending Tom back through
      approval every time.

    Example
    -------
    Calling:

        refresh_dropbox_access_token(refresh_token="refresh-123")

    returns a new short-lived access token in the same normalized shape as the
    original exchange helper.
    """

    payload = build_dropbox_refresh_token_payload(refresh_token=refresh_token)

    return _request_dropbox_token_set(
        payload=payload,
        timeout_seconds=timeout_seconds,
        provider_failure_message="Dropbox token refresh failed.",
    )


def is_dropbox_access_token_expired(
    *,
    obtained_at: datetime | str | None,
    expires_in_seconds: int | None,
    safety_window_seconds: int = 60,
) -> bool:
    """
    Return whether a stored Dropbox access token should be treated as expired.

    Parameters
    ----------
    obtained_at : datetime | str | None
        Timestamp recording when the token set was obtained.

    expires_in_seconds : int | None
        Stored token lifetime in seconds.

    safety_window_seconds : int
        Number of seconds to subtract from the nominal expiry time.

    Returns
    -------
    bool
        `True` when the token should be treated as expired or unreliable.

        `False` when the token is still comfortably valid.

    Notes
    -----
    - If the backend cannot parse the stored timing data safely, this helper
      returns `True`.
    - Failing closed is preferable here because trying a known-bad access token
      only adds noise and a guaranteed provider retry path.

    Example
    -------
    If a token was obtained at `12:00:00Z`, lasts `14400` seconds, and the
    safety window is `60` seconds, then this helper will begin treating it as
    expired at `15:59:00Z`.
    """

    if safety_window_seconds < 0:
        raise ValueError(
            "Dropbox token expiry safety_window_seconds cannot be negative."
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


def _request_dropbox_token_set(
    *,
    payload: dict[str, str],
    timeout_seconds: float,
    provider_failure_message: str,
) -> DropboxTokenSet:
    """
    Send one token-endpoint request to Dropbox and normalize the token result.

    Parameters
    ----------
    payload : dict[str, str]
        Form fields to send to the Dropbox token endpoint.

    timeout_seconds : float
        HTTP timeout used for the provider request.

    provider_failure_message : str
        Message to use when Dropbox returns an HTTP error response.

    Returns
    -------
    DropboxTokenSet
        Normalized token response returned by Dropbox.

    Raises
    ------
    DropboxOAuthExchangeError
        If Dropbox rejects the request, returns an invalid response, or cannot
        be reached safely.

    Example
    -------
    Both of these public helpers:

        exchange_dropbox_authorization_code(...)
        refresh_dropbox_access_token(...)

    eventually delegate their provider request and response parsing here.
    """

    try:
        response = httpx.post(
            DROPBOX_TOKEN_URL,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise DropboxOAuthExchangeError(
            "Could not reach the Dropbox token endpoint.",
        ) from exc

    response_payload = _decode_dropbox_json_response(response)

    if response.status_code >= 400:
        raise DropboxOAuthExchangeError(
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
    account_id = _safe_string(response_payload.get("account_id"))
    raw_expires_in = response_payload.get("expires_in")

    if access_token is None:
        raise DropboxOAuthExchangeError(
            "Dropbox token response did not include an access token.",
            status_code=response.status_code,
            response_body=response_payload,
        )

    if token_type is None:
        raise DropboxOAuthExchangeError(
            "Dropbox token response did not include a token type.",
            status_code=response.status_code,
            response_body=response_payload,
        )

    try:
        expires_in = int(raw_expires_in)
    except (TypeError, ValueError) as exc:
        raise DropboxOAuthExchangeError(
            "Dropbox token response did not include a valid expires_in value.",
            status_code=response.status_code,
            response_body=response_payload,
        ) from exc

    return DropboxTokenSet(
        access_token=access_token,
        token_type=token_type,
        expires_in=expires_in,
        refresh_token=refresh_token,
        scope=scope,
        account_id=account_id,
        raw_payload=response_payload,
    )


def _decode_dropbox_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a Dropbox response body into a dictionary.

    Parameters
    ----------
    response : httpx.Response
        Raw HTTP response from Dropbox.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object, or a small fallback dictionary when the response
        body was not valid JSON.

    Example
    -------
    If Dropbox returns valid JSON, this helper returns that decoded object.
    Otherwise it returns a small fallback payload such as:

        {"raw_text": "..."}
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

    Example
    -------
    These values become:

        datetime(...)          -> timezone-aware UTC datetime
        "2026-05-15T12:00:00Z" -> timezone-aware UTC datetime
        ""                     -> None
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

    Example
    -------
    These values become:

        "  bearer  " -> "bearer"
        ""           -> None
        None         -> None
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    if cleaned_value == "":
        return None

    return cleaned_value


__all__ = [
    "DEFAULT_DROPBOX_SCOPE",
    "DROPBOX_AUTHORIZE_URL",
    "DROPBOX_TOKEN_URL",
    "DropboxOAuthExchangeError",
    "DropboxTokenSet",
    "build_dropbox_authorization_url",
    "build_dropbox_refresh_token_payload",
    "build_dropbox_token_exchange_payload",
    "exchange_dropbox_authorization_code",
    "has_dropbox_oauth_configuration",
    "has_dropbox_token_exchange_configuration",
    "is_dropbox_access_token_expired",
    "refresh_dropbox_access_token",
]
