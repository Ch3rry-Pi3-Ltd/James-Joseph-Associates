"""
Schemas for integration-facing API routes.

This module contains response models for endpoints that sit at the boundary
between this backend and external systems such as JobAdder.

It gives the rest of the repository a stable way to talk about:

- integration authorisation-link responses
- integration callback responses
- OAuth setup status
- provider-specific metadata we choose to expose safely
- keeping integration response shapes out of route modules

Keeping these schemas separate makes the project easier to extend because:

- route modules stay focused on HTTP control flow
- tests can assert one clear response contract
- future integration routes can reuse the same local pattern
- provider-specific response shapes have an obvious home

In plain language:

- this module answers the question:

    "What should integration OAuth responses look like?"

- it does not call external APIs
- it does not exchange OAuth tokens
- it does not store secrets
- it only defines typed response shapes
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobAdderAuthorizationUrlResponse(BaseModel):
    """
    Response returned when the backend builds a JobAdder approval URL.

    Attributes
    ----------
    authorization_url : str
        Fully assembled JobAdder OAuth authorisation URL.

    oauth_configuration_ready : bool
        Whether the backend had the minimum settings needed to build the URL.

    state : str | None
        Optional opaque state value included in the URL.

    Notes
    -----
    - This response is intentionally small.
    - It exists to let the backend return one clean approval link for the client
      to open.
    - The URL itself still points at JobAdder, not at our backend.

    Example
    -------
    A response might look like:

        {
            "authorization_url": "https://id.jobadder.com/connect/authorize?...",
            "oauth_configuration_ready": true,
            "state": "connect-jobadder-dev"
        }
    """

    model_config = ConfigDict(extra="forbid")

    authorization_url: str = Field(
        min_length=1,
        description="Fully assembled JobAdder OAuth authorisation URL.",
    )

    oauth_configuration_ready: bool = Field(
        description=(
            "Whether the backend had the minimum settings needed to build the "
            "URL."
        ),
    )

    state: str | None = Field(
        default=None,
        description="Optional opaque state value included in the URL.",
    )


class JobAdderOAuthCallbackResponse(BaseModel):
    """
    Response returned by the JobAdder OAuth callback route.

    Attributes
    ----------
    status : Literal["received"]
        Fixed status confirming that the callback route was reached.

    message : str
        Short human-readable summary of what happened.

    authorization_code_received : bool
        Whether the callback included a JobAdder `code` query parameter.

    oauth_configuration_ready : bool
        Whether the backend already has the minimum JobAdder OAuth settings
        configured for the later token-exchange step.

    state : str | None
        Optional opaque state value returned by JobAdder.

        This is useful later for CSRF protection or correlating the callback to
        a connection attempt started by the backend.

    next_step : str
        Short explanation of what still needs to happen next.

    Notes
    -----
    - This response deliberately does not expose the raw authorisation code.
    - It also does not expose access tokens or refresh tokens.
    - At this stage, the route exists mainly to give the registered redirect URI
      a real backend target and to make callback testing explicit.

    Example
    -------
    A typical response looks like:

        {
            "status": "received",
            "message": "JobAdder authorization callback received.",
            "authorization_code_received": true,
            "oauth_configuration_ready": false,
            "state": "connect-jobadder-dev",
            "next_step": "Configure the JobAdder OAuth settings, then add the server-side token exchange and token storage."
        }
    """

    # Keep the response strict so the callback contract does not drift quietly.
    model_config = ConfigDict(extra="forbid")

    status: Literal["received"] = Field(
        description="Fixed status confirming the callback route was reached.",
    )

    message: str = Field(
        min_length=1,
        description="Safe human-readable summary of the callback result.",
    )

    authorization_code_received: bool = Field(
        description="Whether the callback included a JobAdder authorization code.",
    )

    oauth_configuration_ready: bool = Field(
        description=(
            "Whether the backend already has the minimum JobAdder OAuth "
            "settings configured for the next step."
        ),
    )

    state: str | None = Field(
        default=None,
        description="Optional opaque state value returned by JobAdder.",
    )

    next_step: str = Field(
        min_length=1,
        description="Short explanation of the next integration step.",
    )


__all__ = [
    "JobAdderAuthorizationUrlResponse",
    "JobAdderOAuthCallbackResponse",
]
