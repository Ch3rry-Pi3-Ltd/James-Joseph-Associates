"""
JobAdder OAuth helper functions for the intelligence backend.

This module contains small helper functions for building the JobAdder OAuth
authorisation URL.

It gives the rest of the repository a stable way to talk about:

- which JobAdder OAuth base URL we send users to
- which query parameters are required
- how the redirect URI is inserted safely
- how the scopes are assembled
- how the backend can validate that the minimum settings exist before trying to
  start the OAuth flow

Keeping this logic in its own module makes the project easier to grow because:

- route handlers do not need to hand-build long URLs
- OAuth-specific rules stay near each other
- tests can target one small helper module at a time
- later token-exchange and refresh-token logic can live nearby

In plain language:

- this module answers the question:

    "How does the backend build the JobAdder approval link?"

- it does not call JobAdder yet
- it does not exchange tokens
- it does not store tokens
- it only builds the URL that starts the approval flow
"""

from urllib.parse import urlencode

from backend.settings import get_settings

JOBADDER_AUTHORIZE_URL = "https://id.jobadder.com/connect/authorize"


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
    # inside values like the redirect URI and scope string.
    encoded_query = urlencode(query_params)

    return f"{JOBADDER_AUTHORIZE_URL}?{encoded_query}"


__all__ = [
    "JOBADDER_AUTHORIZE_URL",
    "build_jobadder_authorization_url",
    "has_jobadder_oauth_configuration",
]
