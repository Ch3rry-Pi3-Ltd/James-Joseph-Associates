"""
Schemas for integration-facing API routes.

This module contains response models for endpoints that sit at the boundary
between this backend and external systems such as JobAdder and Dropbox.

It gives the rest of the repository a stable way to talk about:

- integration authorisation-link responses
- integration callback responses
- successful integration connection-save responses
- authenticated JobAdder preview responses
- authenticated JobAdder candidate-detail responses
- authenticated JobAdder candidate-skills responses
- authenticated JobAdder candidate-notes responses
- Dropbox authorization-link responses
- Dropbox callback responses
- authenticated Dropbox account-preview responses
- authenticated Dropbox folder-preview responses
- Outlook authorization-link responses
- Outlook callback responses
- authenticated Outlook current-user responses
- authenticated Outlook folder/message/attachment preview responses
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

    "What should the integration routes return?"

- it does not call external APIs
- it does not exchange OAuth tokens
- it does not store secrets
- it does not fetch JobAdder data directly
- it only defines typed response shapes
"""

from datetime import date, datetime
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


class LinkedHelperPersonIngestRequest(BaseModel):
    """
    Request body for one protected Linked Helper person/contact ingest.
    """

    model_config = ConfigDict(extra="forbid")

    source_record_id: str | None = Field(
        default=None,
        description=(
            "Stable upstream row identifier. When omitted, the backend derives "
            "one from LinkedIn URL, email, or name/company."
        ),
    )
    source_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw Linked Helper webhook/CSV row preserved for provenance.",
    )
    import_run_id: str | None = Field(
        default=None,
        description="Optional import run identifier for operator bookkeeping.",
    )
    record_kind: Literal["candidate", "contact", "hiring_manager"] = Field(
        description="Canonical interpretation of the incoming Linked Helper row.",
    )
    full_name: str | None = Field(
        default=None,
        description="Full person name when the upstream row already provides it.",
    )
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    primary_email: str | None = Field(default=None)
    primary_phone: str | None = Field(default=None)
    linkedin_url: str | None = Field(default=None)
    location: str | None = Field(default=None)
    headline: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    company_name: str | None = Field(default=None)
    company_domain: str | None = Field(default=None)
    company_website_url: str | None = Field(default=None)
    company_linkedin_url: str | None = Field(default=None)
    role_title: str | None = Field(default=None)
    seniority: str | None = Field(default=None)
    postcode: str | None = Field(default=None)
    contact_type: str | None = Field(default=None)
    is_hiring_manager: bool = Field(default=False)
    is_current_company: bool = Field(default=True)
    role_start_date: date | None = Field(default=None)
    role_end_date: date | None = Field(default=None)
    candidate_status: str | None = Field(default=None)
    availability_status: str | None = Field(default=None)
    resume_updated_at: datetime | None = Field(default=None)
    last_contacted_at: datetime | None = Field(default=None)


class LinkedHelperPersonIngestResponse(BaseModel):
    """
    Response returned after one protected Linked Helper ingest.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = Field(
        description="Fixed status confirming the ingest completed."
    )
    message: str = Field(
        min_length=1,
        description="Short human-readable summary of the ingest result.",
    )
    persisted: dict[str, Any] = Field(
        default_factory=dict,
        description="Canonical IDs and provenance IDs written by the ingest.",
    )


class OutlookFolderIngestRunRequest(BaseModel):
    """
    Request body for one bounded protected Outlook folder-ingest run.

    Notes
    -----
    - This is intentionally a narrow operator/admin request.
    - The route is designed for small controlled production batches, not
      mailbox-scale backfills in a single HTTP call.
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        default="b4dd6a5f-8e27-4745-9369-e117121382ed",
        min_length=1,
        description="Microsoft user identifier used to load the stored Outlook OAuth connection.",
    )

    folder_segments: list[str] = Field(
        min_length=1,
        description="Human-readable Outlook folder path segments in order.",
    )

    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier such as a shared mailbox email address.",
    )

    message_limit: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of Outlook messages to scan in this bounded run.",
    )

    attachment_limit: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of supported attachments to ingest in this bounded run.",
    )

    dropbox_account_id: str = Field(
        default="dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0",
        min_length=1,
        description="Dropbox account ID used for CV export.",
    )

    dropbox_export_folder: str = Field(
        default="/+++ Outlook CV Export",
        min_length=1,
        description="Dropbox base folder that receives exported Outlook CV files.",
    )


class OutlookFolderIngestRunResponse(BaseModel):
    """
    Response returned after one bounded protected Outlook folder-ingest run.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = Field(
        description="Fixed status confirming that the bounded ingest run completed.",
    )

    message: str = Field(
        min_length=1,
        description="Short human-readable summary of the ingest run.",
    )

    resolved_folder: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved Outlook folder metadata used for the run.",
    )

    ingest_report: dict[str, Any] = Field(
        default_factory=dict,
        description="Operator-facing report covering ingested, skipped, and failed items.",
    )


class OutlookCvAttachmentExportRequest(BaseModel):
    """
    Request body for one bounded heuristic Outlook CV attachment export run.
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        default="b4dd6a5f-8e27-4745-9369-e117121382ed",
        min_length=1,
        description="Microsoft user identifier used to load the stored Outlook OAuth connection.",
    )

    folder_segments: list[str] = Field(
        default_factory=lambda: ["Inbox"],
        min_length=1,
        description="Human-readable Outlook folder path segments in order.",
    )

    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier such as a shared mailbox email address.",
    )

    message_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description=(
            "Per-page Outlook message batch size used while scanning the full "
            "bounded date window."
        ),
    )

    attachment_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of CV-like attachments to export in this bounded run.",
    )

    received_from: datetime | None = Field(
        default=None,
        description="Optional lower bound for Outlook receivedDateTime filtering.",
    )

    received_to: datetime | None = Field(
        default=None,
        description="Optional upper bound for Outlook receivedDateTime filtering.",
    )

    dropbox_account_id: str = Field(
        default="dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0",
        min_length=1,
        description="Dropbox account ID used for CV export.",
    )

    dropbox_export_folder: str = Field(
        default="/+++ Outlook CV Export",
        min_length=1,
        description="Dropbox base folder that receives exported Outlook CV files.",
    )

    dry_run: bool = Field(
        default=False,
        description="When true, classify attachments but do not upload any files to Dropbox.",
    )


class OutlookCvAttachmentExportResponse(BaseModel):
    """
    Response returned after one bounded heuristic Outlook CV attachment export run.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = Field(
        description="Fixed status confirming that the bounded export run completed.",
    )

    message: str = Field(
        min_length=1,
        description="Short human-readable summary of the export run.",
    )

    resolved_folder: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved Outlook folder metadata used for the run.",
    )

    export_report: dict[str, Any] = Field(
        default_factory=dict,
        description="Operator-facing report covering exported, non-resume, skipped, and failed items.",
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


class JobAdderJobAdsPreviewResponse(BaseModel):
    """
    Response returned when the backend performs the first authenticated
    JobAdder job-ad list read.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    item_count : int
        Number of job-ad items returned in this preview response.

    total_count : int | None
        Provider-reported total job-ad count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    jobads : list[dict[str, Any]]
        Small first-page preview of job-ad items returned by JobAdder.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "item_count": 2,
            "total_count": 25,
            "links": {...},
            "jobads": [...],
        }
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
        description="Number of job-ad items returned in this preview response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total job-ad count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    jobads: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Small first-page preview of job-ad items from JobAdder.",
    )


class JobAdderJobDetailResponse(BaseModel):
    """
    Response returned when the backend fetches one full JobAdder job record.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    job_id : int
        JobAdder job identifier requested by the route.

    job : dict[str, Any]
        Full job object returned by JobAdder.

    Notes
    -----
    - This keeps the nested job flexible because the current purpose is
      inspection and schema-mapping.
    - The main operational use is to compare the structured JobAdder
      opportunity record with Dropbox job-spec folders and PDFs that use the
      same `tw...` vacancy code.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "job_id": 936462,
            "job": {...},
        }
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

    job_id: int = Field(
        ge=1,
        description="JobAdder job identifier requested by the route.",
    )

    job: dict[str, Any] = Field(
        default_factory=dict,
        description="Full job object returned by JobAdder.",
    )


class JobAdderJobAdApplicationsPreviewResponse(BaseModel):
    """
    Response returned when the backend previews applications for one JobAdder
    job ad.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    ad_id : int
        JobAdder job-ad identifier whose applications were requested.

    active_only : bool
        Whether the preview came from the active-applications endpoint.

    item_count : int
        Number of application items returned in this preview response.

    total_count : int | None
        Provider-reported total application count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    applications : list[dict[str, Any]]
        Small first-page preview of application items returned by JobAdder.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "ad_id": 12345,
            "active_only": true,
            "item_count": 2,
            "total_count": 10,
            "links": {...},
            "applications": [...],
        }
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

    ad_id: int = Field(
        ge=1,
        description="JobAdder job-ad identifier whose applications were requested.",
    )

    active_only: bool = Field(
        description="Whether the preview came from the active-applications endpoint.",
    )

    item_count: int = Field(
        ge=0,
        description="Number of application items returned in this preview response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total application count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    applications: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Small first-page preview of application items from JobAdder.",
    )


class JobAdderApplicationsPreviewResponse(BaseModel):
    """
    Response returned when the backend previews the top-level JobAdder
    applications collection.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    active_only : bool
        Whether the preview requested only active applications.

    rejected_only : bool
        Whether the preview requested only rejected applications.

    item_count : int
        Number of application items returned in this preview response.

    total_count : int | None
        Provider-reported total application count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    applications : list[dict[str, Any]]
        Small first-page preview of application items returned by JobAdder.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "active_only": true,
            "rejected_only": false,
            "item_count": 5,
            "total_count": 608,
            "links": {...},
            "applications": [...],
        }

    Notes
    -----
    This response became the key advert-response discovery surface because the
    live account exposed meaningful vacancy/application context here even when
    the job-ad preview was empty.
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

    active_only: bool = Field(
        description="Whether the preview requested only active applications.",
    )

    rejected_only: bool = Field(
        description="Whether the preview requested only rejected applications.",
    )

    item_count: int = Field(
        ge=0,
        description="Number of application items returned in this preview response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total application count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    applications: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Small first-page preview of application items from JobAdder.",
    )


class JobAdderJobApplicationsPreviewResponse(BaseModel):
    """
    Response returned when the backend previews applications for one JobAdder
    job/opportunity.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    job_id : int
        JobAdder job identifier whose applications were requested.

    item_count : int
        Number of application items returned in this preview response.

    total_count : int | None
        Provider-reported total application count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    applications : list[dict[str, Any]]
        Small first-page preview of application items returned by JobAdder.

    Notes
    -----
    This response is useful when a reconciliation workflow already knows the
    canonical job and wants to inspect only the applications attached to that
    opportunity.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "job_id": 891841,
            "item_count": 10,
            "total_count": 28,
            "links": {...},
            "applications": [...],
        }
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

    job_id: int = Field(
        ge=1,
        description="JobAdder job identifier whose applications were requested.",
    )

    item_count: int = Field(
        ge=0,
        description="Number of application items returned in this preview response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total application count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    applications: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Small first-page preview of application items from JobAdder.",
    )


class JobAdderApplicationDetailResponse(BaseModel):
    """
    Response returned when the backend fetches one full JobAdder application.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    application_id : int
        JobAdder application identifier requested by the route.

    application : dict[str, Any]
        Full application object returned by JobAdder.

    Notes
    -----
    This response exists because application previews are useful for discovery
    but not sufficient for stable persistence.

    The persistence path needs a detail-level payload for one known application
    ID so the backend can link:

    - the application
    - the canonical candidate
    - the canonical job

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "application_id": 12204918,
            "application": {...}
        }
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

    application_id: int = Field(
        ge=1,
        description="JobAdder application identifier requested by the route.",
    )

    application: dict[str, Any] = Field(
        default_factory=dict,
        description="Full application object returned by JobAdder.",
    )


class JobAdderApplicationAttachmentsResponse(BaseModel):
    """
    Response returned when the backend fetches application attachments from
    JobAdder.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    application_id : int
        JobAdder application identifier whose attachments were requested.

    attachment_count : int
        Number of attachment items returned in this response.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    attachments : list[dict[str, Any]]
        Application attachments returned by JobAdder.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "application_id": 12204918,
            "attachment_count": 0,
            "links": {...},
            "attachments": [],
        }

    Notes
    -----
    This schema is intentionally light because the payload is mainly used to
    answer a structural question:

    - does this application actually carry CV attachments?
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

    application_id: int = Field(
        ge=1,
        description="JobAdder application identifier whose attachments were requested.",
    )

    attachment_count: int = Field(
        ge=0,
        description="Number of attachment items returned in this response.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Application attachments returned by JobAdder.",
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


class JobAdderCandidateAttachmentsResponse(BaseModel):
    """
    Response returned when the backend fetches candidate attachments from
    JobAdder.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    candidate_id : int
        JobAdder candidate identifier whose attachments were requested.

    attachment_count : int
        Number of attachment items returned in this response.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    attachments : list[dict[str, Any]]
        Candidate attachments returned by JobAdder.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "candidate_id": 17071060,
            "attachment_count": 1,
            "links": {...},
            "attachments": [...],
        }

    Notes
    -----
    For the tw398 sample, this surface turned out to be the structured CV
    attachment source, unlike the application-level attachment list.
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
        description="JobAdder candidate identifier whose attachments were requested.",
    )

    attachment_count: int = Field(
        ge=0,
        description="Number of attachment items returned in this response.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate attachments returned by JobAdder.",
    )


class JobAdderCandidateAttachmentDownloadProofResponse(BaseModel):
    """
    Response returned when the backend downloads one JobAdder candidate
    attachment transiently and reports proof metadata for comparison work.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    candidate_id : int
        JobAdder candidate identifier that owns the attachment.

    attachment_id : int
        JobAdder attachment identifier that was downloaded transiently.

    file_name : str | None
        File name inferred from the provider response headers when present.

    content_type : str | None
        MIME type reported by JobAdder for the downloaded file.

    content_length : int | None
        Byte length reported by JobAdder in the response headers when present.

    byte_count : int
        Actual number of bytes downloaded by the backend.

    sha256 : str
        SHA-256 hash of the downloaded file bytes.

    Notes
    -----
    - This response exists to compare one JobAdder attachment against another
      source such as Dropbox without exposing the raw file bytes through the
      API route itself.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "candidate_id": 17071060,
            "attachment_id": 21562882,
            "file_name": "sanjeev sadha.docx",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_length": 123456,
            "byte_count": 123456,
            "sha256": "...",
        }
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
        description="JobAdder candidate identifier that owns the attachment.",
    )

    attachment_id: int = Field(
        ge=1,
        description="JobAdder attachment identifier that was downloaded.",
    )

    file_name: str | None = Field(
        default=None,
        description="File name inferred from the provider response headers when present.",
    )

    content_type: str | None = Field(
        default=None,
        description="MIME type reported by JobAdder for the downloaded file.",
    )

    content_length: int | None = Field(
        default=None,
        ge=0,
        description="Byte length reported by JobAdder when present.",
    )

    byte_count: int = Field(
        ge=0,
        description="Actual number of bytes downloaded by the backend.",
    )

    sha256: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the downloaded file bytes.",
    )


class JobAdderCandidateNotesResponse(BaseModel):
    """
    Response returned when the backend fetches candidate notes from JobAdder.

    Attributes
    ----------
    jobadder_account : int
        JobAdder account identifier used to locate the stored OAuth connection.

    jobadder_instance : str | None
        Optional JobAdder instance value stored alongside the connection.

    api_url : str
        JobAdder API base URL used for the authenticated read.

    candidate_id : int
        JobAdder candidate identifier whose notes were requested.

    note_count : int
        Number of note items returned in this response.

    total_count : int | None
        Provider-reported total note count when JobAdder includes it.

    links : dict[str, Any]
        Provider pagination or navigation links when present.

    notes : list[dict[str, Any]]
        Candidate notes returned by JobAdder.

    Notes
    -----
    - Candidate notes are exposed by JobAdder through a dedicated notes
      endpoint rather than living inline inside the candidate detail object.
    - This response intentionally preserves the nested note dictionaries as-is
      for now because the immediate goal is inspection and mapping, not yet a
      frozen canonical note schema.

    Example
    -------
    A typical response looks like:

        {
            "jobadder_account": 2236,
            "jobadder_instance": "eu2",
            "api_url": "https://eu2api.jobadder.com/v2/",
            "candidate_id": 16496678,
            "note_count": 2,
            "total_count": 2,
            "links": {...},
            "notes": [...],
        }
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
        description="JobAdder candidate identifier whose notes were requested.",
    )

    note_count: int = Field(
        ge=0,
        description="Number of candidate note items returned in this response.",
    )

    total_count: int | None = Field(
        default=None,
        description="Provider-reported total note count when available.",
    )

    links: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider pagination or navigation links when present.",
    )

    notes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate notes returned by JobAdder.",
    )


class DropboxAuthorizationUrlResponse(BaseModel):
    """
    Response returned when the backend builds a Dropbox approval URL.

    Attributes
    ----------
    authorization_url : str
        Fully assembled Dropbox OAuth authorization URL.

    oauth_configuration_ready : bool
        Whether the backend had the minimum settings needed to build the URL.

    state : str | None
        Optional opaque state value included in the URL.

    Notes
    -----
    - This response is intentionally small.
    - It exists to let the backend return one clean approval link for Tom to
      open.
    - The URL itself still points at Dropbox, not at our backend.

    Example
    -------
    A response might look like:

        {
            "authorization_url": "https://www.dropbox.com/oauth2/authorize?...",
            "oauth_configuration_ready": true,
            "state": "connect-dropbox-dev"
        }
    """

    model_config = ConfigDict(extra="forbid")

    authorization_url: str = Field(
        min_length=1,
        description="Fully assembled Dropbox OAuth authorization URL.",
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


class DropboxOAuthConnectionSavedResponse(BaseModel):
    """
    Response returned when the Dropbox OAuth callback completes successfully.

    Attributes
    ----------
    status : Literal["connected"]
        Fixed status confirming the Dropbox connection was completed and saved.

    message : str
        Short human-readable summary of the successful connection result.

    oauth_connection_id : str
        Primary key of the saved Dropbox OAuth connection row.

    dropbox_account_id : str
        Dropbox account identifier returned by the provider and used as the
        natural key for persistence.

    requested_scope : str
        Space-separated Dropbox scope string the backend asked Dropbox to
        approve.

    granted_scope : str | None
        Space-separated Dropbox scope string returned by Dropbox in the token
        response.

    missing_requested_scopes : list[str]
        Requested Dropbox scopes that were not present in the returned provider
        scope string.

    state : str | None
        Optional opaque state value returned by Dropbox.

    next_step : str
        Short explanation of what should happen next after the connection was
        saved.

    Example
    -------
    A typical response looks like:

        {
            "status": "connected",
            "message": "Dropbox connection completed successfully.",
            "oauth_connection_id": "11111111-1111-1111-1111-111111111111",
            "dropbox_account_id": "dbid:AAExample",
            "requested_scope": "account_info.read files.metadata.read ...",
            "granted_scope": "account_info.read files.metadata.read ...",
            "missing_requested_scopes": [],
            "state": "connect-dropbox-dev",
            "next_step": "The Dropbox tokens were saved successfully. The next step is to make the first authenticated Dropbox API read."
        }
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["connected"] = Field(
        description="Fixed status confirming the Dropbox connection was saved."
    )
    message: str = Field(
        min_length=1,
        description="Safe human-readable summary of the successful connection result.",
    )
    oauth_connection_id: str = Field(
        min_length=1,
        description="Primary key of the saved Dropbox OAuth connection row.",
    )
    dropbox_account_id: str = Field(
        min_length=1,
        description="Dropbox account identifier associated with the saved connection.",
    )
    requested_scope: str = Field(
        min_length=1,
        description="Space-separated Dropbox scope string the backend requested.",
    )
    granted_scope: str | None = Field(
        default=None,
        description="Scope string returned by Dropbox in the token response, when present.",
    )
    missing_requested_scopes: list[str] = Field(
        default_factory=list,
        description="Requested Dropbox scopes that were not present in the returned provider scope string.",
    )
    state: str | None = Field(
        default=None,
        description="Optional opaque state value returned by Dropbox.",
    )
    next_step: str = Field(
        min_length=1,
        description="Short explanation of the next integration step.",
    )


class DropboxCurrentAccountResponse(BaseModel):
    """
    Response returned when the backend fetches the connected Dropbox account.

    Attributes
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to locate the stored OAuth connection.

    account : dict[str, Any]
        Current-account object returned by Dropbox.

    Example
    -------
    A response looks like:

        {
            "dropbox_account_id": "dbid:AAExample",
            "account": {...}
        }
    """

    model_config = ConfigDict(extra="forbid")

    dropbox_account_id: str = Field(
        min_length=1,
        description="Dropbox account identifier used for the authenticated read.",
    )
    account: dict[str, Any] = Field(
        default_factory=dict,
        description="Current-account object returned by Dropbox.",
    )


class DropboxFolderPreviewResponse(BaseModel):
    """
    Response returned when the backend fetches a first-page Dropbox folder
    preview.

    Attributes
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to locate the stored OAuth connection.

    path : str
        Dropbox folder path that was requested.

    entry_count : int
        Number of entries returned in this response.

    has_more : bool
        Whether Dropbox reported more entries beyond this first page.

    cursor : str | None
        Dropbox cursor returned for later continuation, when present.

    entries : list[dict[str, Any]]
        Folder entries returned by Dropbox.

    Notes
    -----
    - This is intentionally a first-page preview rather than a complete cursor
      traversal workflow.
    - That makes it suitable for early source-shape inspection work.

    Example
    -------
    A response looks like:

        {
            "dropbox_account_id": "dbid:AAExample",
            "path": "",
            "entry_count": 2,
            "has_more": false,
            "cursor": "...",
            "entries": [...]
        }
    """

    model_config = ConfigDict(extra="forbid")

    dropbox_account_id: str = Field(
        min_length=1,
        description="Dropbox account identifier used for the authenticated read.",
    )
    path: str = Field(
        description="Dropbox folder path that was requested.",
    )
    entry_count: int = Field(
        ge=0,
        description="Number of folder entries returned in this response.",
    )
    has_more: bool = Field(
        description="Whether Dropbox reported more entries beyond this first page.",
    )
    cursor: str | None = Field(
        default=None,
        description="Dropbox cursor returned for later continuation, when present.",
    )
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Folder entries returned by Dropbox.",
    )


class DropboxZipMembersPreviewResponse(BaseModel):
    """
    Response returned when the backend inspects the structure of a Dropbox ZIP.

    Attributes
    ----------
    dropbox_account_id : str
        Dropbox account identifier used for the authenticated read.

    file_path : str
        Full Dropbox path of the ZIP file that was inspected.

    file_name : str
        ZIP filename reported by Dropbox.

    byte_count : int
        Total byte size of the downloaded ZIP payload.

    entry_count : int
        Total number of ZIP members discovered in the archive.

    top_level_entries : list[str]
        Unique top-level folders or files at the archive root.

    preview_entries : list[dict[str, Any]]
        Bounded preview of ZIP members, including filenames and basic size
        metadata.

    Notes
    -----
    - This response is intentionally structural. It does not expose raw ZIP
      bytes.
    - It exists to answer questions such as "what kinds of files are in this
      export?" before building a batch importer.

    Example
    -------
    A response might look like:

        {
            "dropbox_account_id": "dbid:AAExample",
            "file_path": "/exports/Recruiterflow.zip",
            "file_name": "Recruiterflow.zip",
            "byte_count": 607918622,
            "entry_count": 42,
            "top_level_entries": ["candidates.csv", "attachments"],
            "preview_entries": [
                {"name": "candidates.csv", "is_dir": false, "file_size": 1234}
            ]
        }
    """

    model_config = ConfigDict(extra="forbid")

    dropbox_account_id: str = Field(
        min_length=1,
        description="Dropbox account identifier used for the authenticated read.",
    )
    file_path: str = Field(
        min_length=1,
        description="Full Dropbox path of the ZIP file that was inspected.",
    )
    file_name: str = Field(
        min_length=1,
        description="ZIP filename reported by Dropbox.",
    )
    byte_count: int = Field(
        ge=0,
        description="Total byte size of the downloaded ZIP payload.",
    )
    entry_count: int = Field(
        ge=0,
        description="Total number of ZIP members discovered in the archive.",
    )
    top_level_entries: list[str] = Field(
        default_factory=list,
        description="Unique top-level folders or files at the archive root.",
    )
    preview_entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Bounded preview of ZIP members and their basic metadata.",
    )


class DropboxZipJsonMemberPreviewResponse(BaseModel):
    """
    Response returned when the backend previews one JSON member inside a
    Dropbox ZIP.

    Attributes
    ----------
    dropbox_account_id : str
        Dropbox account identifier used for the authenticated read.

    file_path : str
        Full Dropbox path of the ZIP file that was inspected.

    member_name : str
        ZIP member path that was parsed as JSON.

    top_level_type : Literal["dict", "list"]
        JSON container type found at the member root.

    entry_count : int | None
        Number of top-level entries when the JSON root is a list.

    key_count : int | None
        Number of top-level keys when the JSON root is an object.

    keys_preview : list[str]
        Bounded preview of root keys when the JSON root is an object.

    sample_item_keys : list[str]
        Bounded preview of keys from the first object item when the JSON root
        is a list of objects.

    preview_payload : Any
        Bounded payload preview used for schema mapping.

    Notes
    -----
    - This response is intentionally bounded. It is meant for importer design,
      not full data extraction.
    - Large JSON members are trimmed to a small preview so the operator can
      inspect shape without moving whole payloads around the UI.

    Example
    -------
    A response might look like:

        {
            "dropbox_account_id": "dbid:AAExample",
            "file_path": "/exports/Recruiterflow.zip",
            "member_name": "candidate/1.100.json",
            "top_level_type": "list",
            "entry_count": 100,
            "key_count": null,
            "keys_preview": [],
            "sample_item_keys": ["id", "name", "email"],
            "preview_payload": [{"id": 1, "name": "Ada Lovelace"}]
        }
    """

    model_config = ConfigDict(extra="forbid")

    dropbox_account_id: str = Field(
        min_length=1,
        description="Dropbox account identifier used for the authenticated read.",
    )
    file_path: str = Field(
        min_length=1,
        description="Full Dropbox path of the ZIP file that was inspected.",
    )
    member_name: str = Field(
        min_length=1,
        description="ZIP member path that was parsed as JSON.",
    )
    top_level_type: Literal["dict", "list"] = Field(
        description="JSON container type found at the member root.",
    )
    entry_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of top-level entries when the JSON root is a list.",
    )
    key_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of top-level keys when the JSON root is an object.",
    )
    keys_preview: list[str] = Field(
        default_factory=list,
        description="Bounded preview of root keys when the JSON root is an object.",
    )
    sample_item_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded preview of keys from the first object item when the JSON "
            "root is a list of objects."
        ),
    )
    preview_payload: Any = Field(
        description="Bounded payload preview used for schema mapping.",
    )


class OutlookAuthorizationUrlResponse(BaseModel):
    """
    Response returned when the backend builds an Outlook approval URL.

    Attributes
    ----------
    authorization_url : str
        Fully assembled Microsoft OAuth authorization URL.

    oauth_configuration_ready : bool
        Whether the backend had the minimum settings needed to build the URL.

    state : str | None
        Optional opaque state value included in the URL.

    Notes
    -----
    - This response mirrors the JobAdder and Dropbox setup pattern so the
      frontend or operator has one consistent approval-link contract.
    - The URL itself points at Microsoft, not at our backend.

    Example
    -------
    A response might look like:

        {
            "authorization_url": "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?...",
            "oauth_configuration_ready": true,
            "state": "connect-outlook-dev"
        }
    """

    model_config = ConfigDict(extra="forbid")

    authorization_url: str = Field(
        min_length=1,
        description="Fully assembled Microsoft OAuth authorization URL.",
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


class OutlookOAuthConnectionSavedResponse(BaseModel):
    """
    Response returned when the Outlook OAuth callback completes successfully.

    Attributes
    ----------
    status : Literal["connected"]
        Fixed status confirming the Outlook connection was completed and saved.

    message : str
        Short human-readable summary of the successful connection result.

    oauth_connection_id : str
        Primary key of the saved Outlook OAuth connection row.

    microsoft_user_id : str
        Microsoft Graph user identifier associated with the saved connection.

    tenant_id : str | None
        Optional Microsoft Entra tenant identifier returned by the provider.

    user_principal_name : str | None
        Optional mailbox login or preferred username returned by Microsoft.

    state : str | None
        Optional opaque state value returned by Microsoft.

    next_step : str
        Short explanation of what should happen next after the connection was
        saved.

    Notes
    -----
    - This response deliberately confirms persistence without exposing the raw
      authorization code or token values.
    - Its job is to prove that the callback completed and that the backend now
      has enough information to start authenticated Graph reads.

    Example
    -------
    A typical response looks like:

        {
            "status": "connected",
            "message": "Outlook connection completed successfully.",
            "oauth_connection_id": "11111111-1111-1111-1111-111111111111",
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "tenant_id": "ffffffff-1111-2222-3333-444444444444",
            "user_principal_name": "tom@example.com",
            "state": "connect-outlook-dev",
            "next_step": "The Outlook tokens were saved successfully. The next step is to make the first authenticated Microsoft Graph read."
        }
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["connected"] = Field(
        description="Fixed status confirming the Outlook connection was saved."
    )
    message: str = Field(
        min_length=1,
        description="Safe human-readable summary of the successful connection result.",
    )
    oauth_connection_id: str = Field(
        min_length=1,
        description="Primary key of the saved Outlook OAuth connection row.",
    )
    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier associated with the saved connection.",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Optional Microsoft Entra tenant identifier.",
    )
    user_principal_name: str | None = Field(
        default=None,
        description="Optional Microsoft username or mailbox login returned by the provider.",
    )
    state: str | None = Field(
        default=None,
        description="Optional opaque state value returned by Microsoft.",
    )
    next_step: str = Field(
        min_length=1,
        description="Short explanation of the next integration step.",
    )


class OutlookCurrentUserResponse(BaseModel):
    """
    Response returned when the backend fetches the connected Outlook user.

    Attributes
    ----------
    microsoft_user_id : str
        Microsoft user identifier used for the authenticated read.

    user : dict[str, Any]
        Current-user object returned by Microsoft Graph.

    Notes
    -----
    - This is the smallest useful authenticated Graph proof after OAuth.
    - It tells us the stored connection works against `/me` before we move into
      folder, message, or attachment discovery.

    Example
    -------
    A response looks like:

        {
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "user": {...}
        }
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier used for the authenticated read.",
    )
    user: dict[str, Any] = Field(
        default_factory=dict,
        description="Current-user object returned by Microsoft Graph.",
    )


class OutlookMailFoldersResponse(BaseModel):
    """
    Response returned when the backend fetches a first-page Outlook mail-folder
    preview.

    Attributes
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to locate the stored connection.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    folder_count : int
        Number of mail folders returned in this response.

    folders : list[dict[str, Any]]
        First-page mail-folder objects returned by Microsoft Graph.

    Notes
    -----
    - This response is intentionally a preview, not a full traversal contract.
    - That keeps the first Outlook slice aligned with the early Dropbox folder
      preview approach.

    Example
    -------
    A response looks like:

        {
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "mailbox": "recruitment@example.com",
            "folder_count": 5,
            "folders": [...]
        }
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier used to locate the stored connection.",
    )
    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier used for the read.",
    )
    folder_count: int = Field(
        ge=0,
        description="Number of mail folders returned in this response.",
    )
    folders: list[dict[str, Any]] = Field(
        default_factory=list,
        description="First-page mail-folder objects returned by Microsoft Graph.",
    )


class OutlookMessagesResponse(BaseModel):
    """
    Response returned when the backend fetches a first-page Outlook message
    preview for one folder.

    Attributes
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to locate the stored connection.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    folder_id : str
        Mail folder identifier used for the message read.

    message_count : int
        Number of messages returned in this response.

    messages : list[dict[str, Any]]
        First-page message objects returned by Microsoft Graph.

    Notes
    -----
    - The first Outlook slice is about discovery, not mailbox synchronization.
    - Message items therefore stay flexible dictionaries so we can inspect the
      source shape before freezing a canonical import model.

    Example
    -------
    A response looks like:

        {
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "mailbox": null,
            "folder_id": "inbox",
            "message_count": 10,
            "messages": [...]
        }
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier used to locate the stored connection.",
    )
    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier used for the read.",
    )
    folder_id: str = Field(
        min_length=1,
        description="Mail folder identifier used for the message read.",
    )
    message_count: int = Field(
        ge=0,
        description="Number of messages returned in this response.",
    )
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="First-page message objects returned by Microsoft Graph.",
    )


class OutlookMessageAttachmentsResponse(BaseModel):
    """
    Response returned when the backend fetches a first-page Outlook attachment
    preview for one message.

    Attributes
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to locate the stored connection.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    message_id : str
        Message identifier whose attachments were requested.

    attachment_count : int
        Number of attachments returned in this response.

    attachments : list[dict[str, Any]]
        First-page attachment objects returned by Microsoft Graph.

    Notes
    -----
    - This preview response is the bridge between mailbox discovery and later
      CV-ingestion work.
    - It proves attachment visibility without yet defining the eventual file
      download or Dropbox-staging workflow.

    Example
    -------
    A response looks like:

        {
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "mailbox": "recruitment@example.com",
            "message_id": "AAMkAGI2...",
            "attachment_count": 3,
            "attachments": [...]
        }
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier used to locate the stored connection.",
    )
    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier used for the read.",
    )
    message_id: str = Field(
        min_length=1,
        description="Message identifier whose attachments were requested.",
    )
    attachment_count: int = Field(
        ge=0,
        description="Number of attachments returned in this response.",
    )
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="First-page attachment objects returned by Microsoft Graph.",
    )


class OutlookMessageAttachmentDownloadProofResponse(BaseModel):
    """
    Response returned when the backend downloads one Outlook file attachment
    transiently and returns only proof metadata.

    Attributes
    ----------
    microsoft_user_id : str
        Microsoft user identifier used to locate the stored connection.

    mailbox : str | None
        Optional delegated mailbox identifier used for the read.

    message_id : str
        Message identifier that owns the attachment.

    attachment_id : str
        Attachment identifier that was downloaded transiently.

    file_name : str | None
        Attachment file name returned by Microsoft Graph.

    content_type : str | None
        Attachment media type returned by Microsoft Graph.

    byte_count : int
        Actual byte length of the decoded attachment payload.

    sha256 : str
        SHA-256 digest of the decoded attachment bytes.

    Notes
    -----
    - This is intentionally a proof route, not a raw file-download route.
    - It exists so we can answer practical questions such as:

        "Can Outlook advert-response attachments feed the existing CV
        extraction pipeline?"

    - Returning hash/size metadata keeps the route useful for comparison work
      without turning it into a public binary-download endpoint.

    Example
    -------
    A response looks like:

        {
            "microsoft_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "mailbox": null,
            "message_id": "AAMkAGI2...",
            "attachment_id": "AAMkAGI2...AAABEgAQ...",
            "file_name": "Candidate CV.pdf",
            "content_type": "application/pdf",
            "byte_count": 326601,
            "sha256": "1006f53e15a0fc116312e38fba6249ec4add00e231d94dcafb8b69fd9a308715"
        }
    """

    model_config = ConfigDict(extra="forbid")

    microsoft_user_id: str = Field(
        min_length=1,
        description="Microsoft user identifier used to locate the stored connection.",
    )
    mailbox: str | None = Field(
        default=None,
        description="Optional delegated mailbox identifier used for the read.",
    )
    message_id: str = Field(
        min_length=1,
        description="Message identifier that owns the attachment.",
    )
    attachment_id: str = Field(
        min_length=1,
        description="Attachment identifier that was downloaded transiently.",
    )
    file_name: str | None = Field(
        default=None,
        description="Attachment file name returned by Microsoft Graph.",
    )
    content_type: str | None = Field(
        default=None,
        description="Attachment media type returned by Microsoft Graph.",
    )
    byte_count: int = Field(
        ge=0,
        description="Actual byte length of the decoded attachment payload.",
    )
    sha256: str = Field(
        min_length=1,
        description="SHA-256 digest of the decoded attachment bytes.",
    )


__all__ = [
    "LinkedHelperPersonIngestRequest",
    "LinkedHelperPersonIngestResponse",
    "JobAdderAuthorizationUrlResponse",
    "JobAdderApplicationDetailResponse",
    "JobAdderApplicationAttachmentsResponse",
    "JobAdderApplicationsPreviewResponse",
    "JobAdderJobApplicationsPreviewResponse",
    "JobAdderCandidateAttachmentDownloadProofResponse",
    "JobAdderCandidateAttachmentsResponse",
    "JobAdderCandidateDetailResponse",
    "JobAdderJobDetailResponse",
    "JobAdderJobAdApplicationsPreviewResponse",
    "JobAdderJobAdsPreviewResponse",
    "JobAdderCandidateNotesResponse",
    "JobAdderCandidateSkillsResponse",
    "JobAdderCandidatesPreviewResponse",
    "JobAdderOAuthConnectionSavedResponse",
    "DropboxAuthorizationUrlResponse",
    "DropboxCurrentAccountResponse",
    "DropboxFolderPreviewResponse",
    "DropboxOAuthConnectionSavedResponse",
    "OutlookAuthorizationUrlResponse",
    "OutlookCurrentUserResponse",
    "OutlookMessageAttachmentDownloadProofResponse",
    "OutlookMailFoldersResponse",
    "OutlookMessageAttachmentsResponse",
    "OutlookMessagesResponse",
    "OutlookOAuthConnectionSavedResponse",
]
