"""
JobAdder OAuth helper functions for the intelligence backend.

This module contains small helper functions for the two early JobAdder OAuth
steps:

- building the JobAdder approval URL
- exchanging a one-time authorization code for tokens

It gives the rest of the repository a stable way to talk about:

- which JobAdder OAuth base URL we send users to
- which query parameters are required for the approval-link step
- which form fields are required for the token-exchange step
- how the backend can validate that the minimum settings exist before trying to
  start the OAuth flow
- how JobAdder token responses should be represented in Python

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to hand-build long URLs
- OAuth-specific rules stay near each other
- tests can target one small helper module at a time
- later token-exchange and refresh-token logic can live nearby

In plain language:

- this module answers the questions:

    "How does the backend build the JobAdder approval link?"
    "How does the backend swap a JobAdder code for tokens?"

- it does not define API routes
- it does not store tokens
- it does not create database records
- it only handles the OAuth helper logic itself
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from backend.settings import get_settings

JOBADDER_AUTHORIZE_URL = "https://id.jobadder.com/connect/authorize"
JOBADDER_TOKEN_URL = "https://id.jobadder.com/connect/token"


@dataclass(frozen=True)
class JobAdderTokenSet:
    """
    Normalised token response returned by JobAdder after a successful exchange.

    Attributes
    ----------
    access_token : str
        Short-lived bearer token used for authenticated JobAdder API calls.

    token_type : str
        OAuth token type returned by JobAdder.

        In practice, this is expected to be `Bearer`, but the backend should read
        the returned value rather than hard-code it.

    expires_in : int
        Token lifetime in seconds.

    refresh_token : str | None
        Longer-lived token used to request a new access token later.

        This is especially important because JobAdder access tokens expire and
        the integration should not require repeated manual reauthorisation.

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
    Raised when the backend cannot complete the JobAdder token exchange safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code: int | None
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

        It plain language:

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
    - The client secret is not needed until the later token-exchange step.

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
    Return whether the backend has enough configuration to exchange a code.

    Returns
    -------
    bool
        `True` when the backend has all values required for the server-side
        token exchange.

        `False` when one or more required settings are missing or empty.

    Notes
    -----
    - This check is stricter than `has_jobadder_oauth_configuration()`.
    - The token-exchange step needs:

        - `JOBADDER_CLIENT_ID`
        - `JOBADDER_CLIENT_SECRET`
        - `JOBADDER_REDIRECT_URI`

    In plain language:

    - building the login link needs fewer settings
    - swapping the code for tokens needs all three
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

        This is useful for later correlation and CSRF protection.

    scope : str
        Space-separated OAuth scopes to request.

        Defaults to:

            "read write offline_access"

        Notes:
        - `offline_access` matters because JobAdder only returns a refresh token
          when that scope is requested.
        - `read` and `write` are broad scopes. They can be narrowed later if the
          integration only needs a smaller set of permissions.

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

    Example
    -------
    Build an approval URL with a simple state:

        from backend.services.jobadder_oauth import build_jobadder_authorization_url

        url = build_jobadder_authorization_url(
            state="connect-jobadder-dev",
        )

        print(url)

    In plain language:

    - take the known settings
    - add the OAuth query parameters
    - return the final approval link
    """

    settings = get_settings()

    client_id = settings.jobadder_client_id.strip()
    redirect_uri = settings.jobadder_redirect_uri.strip()

    # Fail early if the minimum setup is not present.
    #   - The caller cannot build a correct approval URL without these values.
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

    # `state` is optional.
    #   - Only include it when the caller has supplied a real value.
    if state is not None and state.strip() != "":
        query_params["state"] = state

    # `urlencode(...)` safely builds the query string.
    #   - Takes care of URL-encoding characters such as:
    #
    #       - spaces
    #       - slashes
    #       - colons
    #
    #     inside values like the redirect URI and scope string.
    #
    #   - `quote_via=quote` matters here because JobAdder appears to expect 
    #     scopes to be encoded with `%20` between words rather than `+`.
    encoded_query = urlencode(query_params, quote_via=quote)

    return f"{JOBADDER_AUTHORIZE_URL}?{encoded_query}"


def build_jobadder_token_exchange_payload(*, code: str) -> dict[str, str]:
    """
    Build the form payload required for the JobAdder token endpoint.

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

    Notes
    -----
    - This function does not make the HTTP request.
    - It exists so the form-building rules can be tested separately from the
      HTTP exchange itself.
    - The payload uses the standard OAuth authorization-code grant fields.

    In plain language:

    - take the code and backend settings
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

def exchange_jobadder_authorization_code(
    *,
    code: str,
    timeout_seconds: float = 30.0,
) -> JobAdderTokenSet:
    """
    Exchange a one-time JobAdder authorization code for tokens.

    Parameters
    ----------
    code : str
        One-time authorization code returned by JobAdder.

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

    Notes
    -----
    - This is a server-side step.
    - The browser or client-side approver should never perform this exchange.
    - The returned tokens should be stored securely before this helper is
      wired directly into the public callback flow.

    Why this helper exists
    ----------------------
    The callback route receives a temporary `code`, but that code is not useful
    on its own. The backend must send it to JobAdder's token endpoint to obtain:

    - `access_token`
    - `refresh_token`
    - expiry information

    In plain language:

    - recieve the one-time code
    - send it to JobAdder from the backend
    - get tokens back
    - return them in a normal Python shape
    """

    payload = build_jobadder_token_exchange_payload(code=code)

    try:
        response = httpx.post(
            JOBADDER_TOKEN_URL,
            data=payload,
            headers={
                "Accept": "application/json",
            },
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        # Network-level failures are different from provider-side OAuth failures
        #   - If we never got a useable HTTP response, surface that clearly.
        #   - The caller can later translate this into a stable API error.
        raise JobAdderOAuthExchangeError(
            "Could not reach the JobAdder token endpoint.",
        ) from exc
    
    response_payload = _decode_jobadder_json_response(response)

    # JobAdder may reject the token request for reasons such as:
    #  
    #   - expired code
    #   - code already used
    #   - redirect URI mismatch
    #   - client credential mismatch
    #
    # When that happens, capture the provider details safely so later route code
    # can report something clerer than a generic 500.
    if response.status_code >= 400:
        raise JobAdderOAuthExchangeError(
            "JobAdder token exchange failed.",
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

    # A success response is not actually useful unless the key fields are present 
    #   - Fail fast if JobAdder returned something incomplete or unexpected.
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
    - This helper stays private because it is just internal parsing glue.

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

    In plain language:

    - if it is useful text, return it
    - otherwise return none
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
    "build_jobadder_token_exchange_payload",
    "exchange_jobadder_authorization_code",
    "has_jobadder_oauth_configuration",
    "has_jobadder_token_exchange_configuration",
]
