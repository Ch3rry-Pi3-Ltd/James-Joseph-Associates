"""
Microsoft / Outlook OAuth helper functions for the intelligence backend.

This module contains the first small OAuth helpers for Microsoft Graph-backed
Outlook access.

It gives the rest of the repository a stable way to talk about:

- building the Microsoft approval URL
- exchanging a one-time authorization code for tokens
- refreshing an expired access token with a stored refresh token
- checking whether the minimum Outlook OAuth settings exist
- deciding whether a stored Outlook token should be treated as expired

Important implementation note
-----------------------------
The mailbox flow we want here is the modern Microsoft 365 / Exchange Online
path, not local PST parsing.

That means:

- one Microsoft Entra application must be registered first
- the backend stores delegated OAuth tokens after the callback
- later Outlook mailbox reads happen through Microsoft Graph

Example
-------
Typical usage in the rest of the backend looks like:

    authorization_url = build_outlook_authorization_url(
        state="connect-outlook",
    )
    token_set = exchange_outlook_authorization_code(code="abc123")
    should_refresh = is_outlook_access_token_expired(
        obtained_at="2026-05-16T10:00:00Z",
        expires_in_seconds=3600,
    )

In plain language:

- this module answers the questions:

    "How does the backend build the Outlook approval link?"
    "How does the backend swap a Microsoft code for tokens?"
    "How does the backend refresh an expired Graph access token?"

- it does not define API routes
- it does not store tokens
- it does not fetch mail folders or attachments
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.settings import get_settings

DEFAULT_OUTLOOK_SCOPE = (
    "offline_access User.Read Mail.Read Mail.Read.Shared"
)


@dataclass(frozen=True)
class OutlookTokenSet:
    """
    Normalized token response returned by Microsoft after a successful exchange
    or refresh.

    Attributes
    ----------
    access_token : str
        Short-lived bearer token used for Microsoft Graph API calls.

    token_type : str
        OAuth token type returned by Microsoft.

    expires_in : int
        Token lifetime in seconds.

    refresh_token : str | None
        Long-lived refresh token returned when `offline_access` was requested.

    scope : str | None
        Space-separated scope string returned by Microsoft, if present.

    microsoft_user_id : str | None
        Graph user identifier from the ID token or provider payload when
        available.

    tenant_id : str | None
        Microsoft Entra tenant identifier associated with the token set.

    user_principal_name : str | None
        Preferred username claim, typically the signed-in mailbox login.

    raw_payload : dict[str, Any]
        Full decoded provider payload.

    Example
    -------
    A successful token exchange may be represented as:

        OutlookTokenSet(
            access_token="...",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="...",
            scope="offline_access User.Read Mail.Read Mail.Read.Shared",
            microsoft_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            tenant_id="ffffffff-1111-2222-3333-444444444444",
            user_principal_name="tom@example.com",
            raw_payload={...},
        )
    """

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    scope: str | None
    microsoft_user_id: str | None
    tenant_id: str | None
    user_principal_name: str | None
    raw_payload: dict[str, Any]


class OutlookOAuthExchangeError(RuntimeError):
    """
    Raised when the backend cannot complete the Microsoft token exchange or
    refresh safely.

    Example
    -------
    Route handlers can inspect:

        error.status_code
        error.provider_error
        error.provider_error_description

    to distinguish between invalid app credentials, expired authorization
    codes, revoked refresh tokens, or malformed provider responses.
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
        """Return the human-readable error message."""

        return self.message


def _tenant_segment() -> str:
    """
    Return the configured Microsoft tenant segment to use in OAuth URLs.

    Example
    -------
    With:

        MICROSOFT_TENANT_ID="organizations"

    this helper returns:

        "organizations"
    """

    settings = get_settings()
    tenant_segment = settings.microsoft_tenant_id.strip()
    return tenant_segment or "organizations"


def _authorize_url() -> str:
    """Return the Microsoft OAuth authorize endpoint for the configured tenant."""

    return (
        f"https://login.microsoftonline.com/{_tenant_segment()}"
        "/oauth2/v2.0/authorize"
    )


def _token_url() -> str:
    """Return the Microsoft OAuth token endpoint for the configured tenant."""

    return (
        f"https://login.microsoftonline.com/{_tenant_segment()}"
        "/oauth2/v2.0/token"
    )


def has_outlook_oauth_configuration() -> bool:
    """
    Return whether the minimum Outlook OAuth settings are present.

    Example
    -------
    If:

    - `MICROSOFT_CLIENT_ID` is set
    - `MICROSOFT_REDIRECT_URI` is set

    then this helper returns `True` even before the client secret is
    configured.
    """

    settings = get_settings()

    return (
        settings.microsoft_client_id.strip() != ""
        and settings.microsoft_redirect_uri.strip() != ""
    )


def has_outlook_token_exchange_configuration() -> bool:
    """
    Return whether the backend has enough configuration to exchange or refresh
    Microsoft tokens.

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
            settings.microsoft_client_id.strip() != "",
            settings.microsoft_client_secret.strip() != "",
            settings.microsoft_redirect_uri.strip() != "",
        ]
    )


def build_outlook_authorization_url(
    *,
    state: str | None = None,
    scope: str = DEFAULT_OUTLOOK_SCOPE,
) -> str:
    """
    Build the Microsoft OAuth authorization URL used for Outlook access.

    Parameters
    ----------
    state : str | None
        Optional opaque value that Microsoft should return unchanged in the
        callback.

    scope : str
        Space-separated Microsoft Graph delegated scopes to request.

    Returns
    -------
    str
        Fully assembled Microsoft OAuth authorization URL.

    Example
    -------
    A call such as:

        build_outlook_authorization_url(state="connect-outlook-dev")

    returns a URL starting with:

        https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?...
    """

    settings = get_settings()
    client_id = settings.microsoft_client_id.strip()
    redirect_uri = settings.microsoft_redirect_uri.strip()

    if client_id == "" or redirect_uri == "":
        raise ValueError(
            "Outlook OAuth is not configured. "
            "Set MICROSOFT_CLIENT_ID and MICROSOFT_REDIRECT_URI."
        )

    query_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scope,
    }

    if state is not None and state.strip() != "":
        query_params["state"] = state

    return f"{_authorize_url()}?{urlencode(query_params)}"


def build_outlook_token_exchange_payload(*, code: str) -> dict[str, str]:
    """
    Build the form payload required for Microsoft authorization-code exchange.

    Example
    -------
    The resulting payload contains:

    - `grant_type=authorization_code`
    - the one-time code
    - the configured client credentials
    - the configured redirect URI
    """

    settings = get_settings()
    client_id = settings.microsoft_client_id.strip()
    client_secret = settings.microsoft_client_secret.strip()
    redirect_uri = settings.microsoft_redirect_uri.strip()

    if not isinstance(code, str) or code.strip() == "":
        raise ValueError("Outlook authorization code cannot be empty.")

    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "Outlook token exchange is not configured. "
            "Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and "
            "MICROSOFT_REDIRECT_URI."
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }


def build_outlook_refresh_token_payload(*, refresh_token: str) -> dict[str, str]:
    """
    Build the form payload required for Microsoft refresh-token exchange.

    Example
    -------
    A successful refresh request needs:

    - `grant_type=refresh_token`
    - the stored refresh token
    - the configured client credentials
    """

    settings = get_settings()
    client_id = settings.microsoft_client_id.strip()
    client_secret = settings.microsoft_client_secret.strip()
    redirect_uri = settings.microsoft_redirect_uri.strip()

    if not isinstance(refresh_token, str) or refresh_token.strip() == "":
        raise ValueError("Outlook refresh token cannot be empty.")

    if client_id == "" or client_secret == "" or redirect_uri == "":
        raise ValueError(
            "Outlook token refresh is not configured. "
            "Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and "
            "MICROSOFT_REDIRECT_URI."
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "redirect_uri": redirect_uri,
    }


def exchange_outlook_authorization_code(*, code: str) -> OutlookTokenSet:
    """
    Exchange a one-time Microsoft authorization code for tokens.

    Example
    -------
    A call such as:

        exchange_outlook_authorization_code(code="abc123")

    returns an `OutlookTokenSet` that can then be persisted in Postgres.
    """

    payload = build_outlook_token_exchange_payload(code=code)

    return _request_outlook_token_set(
        payload=payload,
        provider_failure_message="Outlook token exchange failed.",
    )


def refresh_outlook_access_token(*, refresh_token: str) -> OutlookTokenSet:
    """
    Refresh an expired Microsoft access token using the stored refresh token.

    Example
    -------
    A call such as:

        refresh_outlook_access_token(refresh_token="refresh-123")

    returns a replacement `OutlookTokenSet`.
    """

    payload = build_outlook_refresh_token_payload(refresh_token=refresh_token)

    return _request_outlook_token_set(
        payload=payload,
        provider_failure_message="Outlook token refresh failed.",
    )


def is_outlook_access_token_expired(
    *,
    obtained_at: str | datetime,
    expires_in_seconds: int,
    safety_window_seconds: int = 60,
) -> bool:
    """
    Return whether a stored Outlook access token should be treated as expired.

    Example
    -------
    If a token was obtained one hour ago and lasts only 3600 seconds, this
    helper returns `True`.
    """

    if safety_window_seconds < 0:
        raise ValueError(
            "Outlook token expiry safety_window_seconds cannot be negative."
        )

    if isinstance(obtained_at, str):
        normalized_obtained_at = datetime.fromisoformat(
            obtained_at.replace("Z", "+00:00")
        )
    else:
        normalized_obtained_at = obtained_at

    if normalized_obtained_at.tzinfo is None:
        normalized_obtained_at = normalized_obtained_at.replace(
            tzinfo=timezone.utc
        )

    expires_at = normalized_obtained_at + timedelta(seconds=expires_in_seconds)
    safety_window = timedelta(seconds=safety_window_seconds)

    return datetime.now(timezone.utc) >= (expires_at - safety_window)


def _request_outlook_token_set(
    *,
    payload: dict[str, str],
    provider_failure_message: str,
) -> OutlookTokenSet:
    """
    Send one token-endpoint request to Microsoft and normalize the token result.

    Example
    -------
    This internal helper is used by both:

    - `exchange_outlook_authorization_code(...)`
    - `refresh_outlook_access_token(...)`
    """

    settings = get_settings()

    try:
        response = httpx.post(
            _token_url(),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=settings.llm_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise OutlookOAuthExchangeError(
            "Could not reach the Microsoft token endpoint.",
        ) from exc

    response_payload = _decode_outlook_json_response(response)

    if response.status_code >= 400:
        raise OutlookOAuthExchangeError(
            provider_failure_message,
            status_code=response.status_code,
            provider_error=_read_optional_string(response_payload, "error"),
            provider_error_description=_read_optional_string(
                response_payload,
                "error_description",
            ),
            response_body=response_payload,
        )

    access_token = _read_required_string(response_payload, "access_token")
    token_type = _read_required_string(response_payload, "token_type")
    expires_in_raw = response_payload.get("expires_in")

    try:
        expires_in = int(expires_in_raw)
    except (TypeError, ValueError) as exc:
        raise OutlookOAuthExchangeError(
            "Microsoft token response did not include a valid expires_in value.",
            response_body=response_payload,
        ) from exc

    id_token_claims = _decode_jwt_claims(
        _read_optional_string(response_payload, "id_token")
    )

    return OutlookTokenSet(
        access_token=access_token,
        token_type=token_type,
        expires_in=expires_in,
        refresh_token=_read_optional_string(response_payload, "refresh_token"),
        scope=_read_optional_string(response_payload, "scope"),
        microsoft_user_id=_read_optional_string(id_token_claims, "oid"),
        tenant_id=_read_optional_string(id_token_claims, "tid"),
        user_principal_name=(
            _read_optional_string(id_token_claims, "preferred_username")
            or _read_optional_string(id_token_claims, "upn")
        ),
        raw_payload=response_payload,
    )


def _decode_outlook_json_response(response: httpx.Response) -> dict[str, Any]:
    """
    Decode a Microsoft response body into a dictionary.

    Example
    -------
    If Microsoft returns valid JSON, this helper returns that decoded object.
    """

    try:
        decoded = response.json()
    except ValueError:
        return {}

    if isinstance(decoded, dict):
        return decoded

    return {}


def _read_required_string(payload: dict[str, Any], key: str) -> str:
    """
    Read one required string from a decoded provider payload.

    Example
    -------
    If `access_token` is missing or blank, this helper raises a provider-shape
    error instead of returning a partial token set.
    """

    value = payload.get(key)

    if not isinstance(value, str) or value.strip() == "":
        raise OutlookOAuthExchangeError(
            f"Microsoft token response did not include a usable {key}.",
            response_body=payload,
        )

    return value


def _read_optional_string(payload: dict[str, Any], key: str) -> str | None:
    """
    Read one optional string from a decoded provider payload.

    Example
    -------
    If a provider payload contains:

        {"scope": "Mail.Read User.Read"}

    then `_read_optional_string(payload, "scope")` returns that string.
    """

    value = payload.get(key)

    if not isinstance(value, str):
        return None

    stripped_value = value.strip()
    return stripped_value or None


def _decode_jwt_claims(jwt_value: str | None) -> dict[str, Any]:
    """
    Decode the middle payload segment of a JWT without verifying the signature.

    Notes
    -----
    - This helper is intentionally lightweight.
    - It is used only to extract convenient non-secret identity hints from the
      ID token returned alongside the delegated token set.
    - The backend still treats the access and refresh tokens as the real
      credentials; these decoded claims are only metadata.

    Example
    -------
    If Microsoft returns an `id_token`, this helper can extract claims such as:

    - `oid`
    - `tid`
    - `preferred_username`
    """

    if not isinstance(jwt_value, str) or jwt_value.strip() == "":
        return {}

    segments = jwt_value.split(".")

    if len(segments) < 2:
        return {}

    payload_segment = segments[1]
    padding = "=" * (-len(payload_segment) % 4)

    try:
        import base64
        import json

        decoded_payload = base64.urlsafe_b64decode(payload_segment + padding)
        parsed_payload = json.loads(decoded_payload.decode("utf-8"))
    except Exception:
        return {}

    if isinstance(parsed_payload, dict):
        return parsed_payload

    return {}


__all__ = [
    "DEFAULT_OUTLOOK_SCOPE",
    "OutlookOAuthExchangeError",
    "OutlookTokenSet",
    "build_outlook_authorization_url",
    "build_outlook_refresh_token_payload",
    "build_outlook_token_exchange_payload",
    "exchange_outlook_authorization_code",
    "has_outlook_oauth_configuration",
    "has_outlook_token_exchange_configuration",
    "is_outlook_access_token_expired",
    "refresh_outlook_access_token",
]
