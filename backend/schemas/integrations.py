"""
Schemas for integration-facing API routes.

This module contains response models for endpoints that sit at the boundary
between this backend and external systems such as JobAdder.

It gives the rest of the repository a stable way to talk about:

- integration authorisation-link responses
- integration callback responses
- successful integration connection-save responses
- first authenticated JobAdder API preview responses
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
- it does not fetch JobAdder data directly
- it only defines typed response shapes
"""

from typing import Any, Literal

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


class JobAdderOAuthConnectionSavedResponse(BaseModel):
    """
    Response returned when the JobAdder OAuth callback completes successfully.

    Attributes
    ----------
    status : Literal["connected"]
        Fixed status confirming that the JobAdder connection was completed and
        persisted.

    message : str
        Short human-readable summary of the successful connection result.

    oauth_connection_id : str
        Primary key of the saved OAuth connection row.

    jobadder_account : int
        JobAdder account identifier returned by the provider and used as the
        natural key for persistence.

    jobadder_instance : str | None
        Optional JobAdder instance value returned by the provider.

    state : str | None
        Optional opaque state value returned by JobAdder.

        This is useful later for CSRF protection or correlating the callback to
        a connection attempt started by the backend.

    next_step : str
        Short explanation of what should happen next after the connection was
        saved.

    Notes
    -----
    - This response deliberately does not expose the raw authorisation code.
    - It also does not expose access tokens or refresh tokens.
    - It confirms that the backend completed the two important server-side
      actions:

        - exchange the code for tokens
        - save the returned token set in Postgres

    Example
    -------
    A typical response looks like:

        {
            "status": "connected",
            "message": "JobAdder connection completed successfully.",
            "oauth_connection_id": "11111111-1111-1111-1111-111111111111",
            "jobadder_account": 123456,
            "jobadder_instance": "jobadder-prod-au",
            "state": "connect-jobadder-dev",
            "next_step": "The JobAdder tokens were saved successfully. The next step is to make the first authenticated JobAdder API read."
        }
    """

    # Keep the response strict so the callback contract does not drift quietly.
    model_config = ConfigDict(extra="forbid")

    status: Literal["connected"] = Field(
        description=(
            "Fixed status confirming the JobAdder connection was completed and "
            "saved."
        ),
    )

    message: str = Field(
        min_length=1,
        description="Safe human-readable summary of the successful connection result.",
    )

    oauth_connection_id: str = Field(
        min_length=1,
        description="Primary key of the saved JobAdder OAuth connection row.",
    )

    jobadder_account: int = Field(
        description="JobAdder account identifier associated with the saved connection.",
    )

    jobadder_instance: str | None = Field(
        default=None,
        description="Optional JobAdder instance value returned by the provider.",
    )

    state: str | None = Field(
        default=None,
        description="Optional opaque state value returned by JobAdder.",
    )

    next_step: str = Field(
        min_length=1,
        description="Short explanation of the next integration step.",
    )


class JobAdderCandidatesPreviewResponse(BaseModel):
    """
    Response returned when the backend performs the first authenticated
    JobAdder candidate-list read.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    item_count : int
        Number of candidate items returned in this preview response.

    total_count : int | None
        Provider-reported total item count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    candidates : list[dict[str, Any]]
        Small first-page preview of candidate items returned by JobAdder.

    Notes
    -----
    - This is intentionally a thin wrapper around the first provider response.
    - At this stage we are proving authenticated API access, not yet defining
      the final canonical candidate-ingestion model.
    - The nested candidate items therefore remain flexible dictionaries.

    In plain language:

    - tell us which stored connection was used
    - tell us how many candidate items came back
    - return the first small candidate preview from JobAdder
    """

    model_config = ConfigDict(extra="forbid")

    jobadder_account: int = Field(
        description="JobAdder account identifier used for the authenticated read.",
    )

    jobadder_instance: str | None = Field(
        default=None,
        description="Optional JobAdder instance value stored with the connection.",
    )

    api_url: str = Field(
        min_length=1,
        description="JobAdder API base URL used for the authenticated read.",
    )

    item_count: int = Field(
        ge=0,
        description="Number of candidate items returned in this preview response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total candidate count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Small first-page preview of candidate items from JobAdder.",
    )


class JobAdderCandidateDetailResponse(BaseModel):
    """
    Response returned when the backend fetches one full JobAdder candidate.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    candidate_id : int
        JobAdder candidate identifier requested by the route.

    candidate : dict[str, Any]
        Full candidate object returned by JobAdder.

    Notes
    -----
    - This response intentionally keeps the nested candidate flexible rather
      than freezing the source shape prematurely.
    - The immediate purpose is inspection and schema-mapping, not final
      ingestion or long-term contract design.

    In plain language:

    - tell us which stored JobAdder connection was used
    - tell us which candidate was requested
    - return the full candidate object that JobAdder sent back
    """

    model_config = ConfigDict(extra="forbid")

    jobadder_account: int = Field(
        description="JobAdder account identifier used for the authenticated read.",
    )

    jobadder_instance: str | None = Field(
        default=None,
        description="Optional JobAdder instance value stored with the connection.",
    )

    api_url: str = Field(
        min_length=1,
        description="JobAdder API base URL used for the authenticated read.",
    )

    candidate_id: int = Field(
        ge=1,
        description="JobAdder candidate identifier requested by the route.",
    )

    candidate: dict[str, Any] = Field(
        default_factory=dict,
        description="Full candidate object returned by JobAdder.",
    )


class JobAdderCandidateSkillsResponse(BaseModel):
    """
    Response returned when the backend fetches the structured skills tree for
    one JobAdder candidate.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    candidate_id : int
        JobAdder candidate identifier whose skills were requested.

    category_count : int
        Number of top-level skill categories returned by JobAdder.

    links : dict[str, Any]
        Provider navigation links when present.

    categories : list[dict[str, Any]]
        Structured skills category tree returned by JobAdder.

    Notes
    -----
    - The OpenAPI spec documents candidate skills as a nested
      category -> subcategory -> skill hierarchy.
    - This response preserves that hierarchy so the backend can inspect how the
      source system models skills before choosing a canonical representation.
    """

    model_config = ConfigDict(extra="forbid")

    jobadder_account: int = Field(
        description="JobAdder account identifier used for the authenticated read.",
    )

    jobadder_instance: str | None = Field(
        default=None,
        description="Optional JobAdder instance value stored with the connection.",
    )

    api_url: str = Field(
        min_length=1,
        description="JobAdder API base URL used for the authenticated read.",
    )

    candidate_id: int = Field(
        ge=1,
        description="JobAdder candidate identifier whose skills were requested.",
    )

    category_count: int = Field(
        ge=0,
        description="Number of top-level skill categories returned by JobAdder.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider navigation links when present.",
    )

    categories: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured skills category tree returned by JobAdder.",
    )


__all__ = [
    "JobAdderAuthorizationUrlResponse",
    "JobAdderCandidateDetailResponse",
    "JobAdderCandidateSkillsResponse",
    "JobAdderCandidatesPreviewResponse",
    "JobAdderOAuthConnectionSavedResponse",
]
