"""
Candidate API response schemas.

This module contains small Pydantic models used by candidate-related API
endpoints.

It gives the rest of the repository a stable way to talk about:

- the API response shape for one candidate profile view
- returning candidate data and linked skills together
- generating FastAPI/OpenAPI documentation for candidate endpoints
- keeping route modules focused on request handling rather than schema classes

Keeping these schemas in their own module makes the project easier to extend
because:

- candidate route modules can stay focused on endpoint behaviour
- tests can assert one shared response contract
- future candidate endpoints can reuse the same schema file
- response model growth has a clear home

In plain language:

- this module answers the question:

    "What should a candidate profile API response look like?"

- it does not define database tables
- it does not run SQL queries
- it does not contain route handlers
- it does not decide how candidate data is fetched
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.llm_safety import MAX_LLM_INPUT_CHARACTERS

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_BASE64_CHARACTERS = ((MAX_UPLOAD_BYTES + 2) // 3) * 4


class CandidateProfileResponse(BaseModel):
    """
    Combined candidate profile response returned by the API.

    Attributes
    ----------
    candidate : dict[str, Any]
        Canonical candidate profile data returned by the service layer.

    skills : list[dict[str, Any]]
        Skills linked to the candidate, including evidence and confidence where
        available.

    Notes
    -----
    - The underlying candidate and skill dictionaries currently come from the
      prototype Supabase/Postgres service layer.
    - This response model is intentionally a thin wrapper around those service
      results for the current prototype stage.
    - Later, if the API contract needs stricter field-level typing, this model
      is the right place to introduce that.
    - For now, keeping the nested payloads as dictionaries lets the API move
      quickly while the canonical schema is still being proven out.
    - Once the candidate profile shape stabilises, the nested dictionaries can
      be replaced with more explicit Pydantic models.

    Example
    -------
    A successful response should look like:

        {
            "candidate": {
                "candidate_id": "33333333-3333-3333-3333-333333333331",
                "full_name": "Sarah Jones"
            },
            "skills": [
                {
                    "skill_name": "Python",
                    "confidence": 0.98
                }
            ]
        }

    In plain language:

    - `candidate` holds the main candidate profile details
    - `skills` holds the linked skill rows for that candidate
    - together they form the first usable candidate profile view exposed by the API
    """

    # Reject unexpected top-level fields so the route response stays explicit
    #   - Without this, accidental extra keys could appear in responses and
    #     still pass validation.
    #   - This is useful here because this schema is part of the public API
    #     contract, even though the nested candidate/skill payloads are still
    #     flexible dictionaries for the prototype stage.
    model_config = ConfigDict(extra="forbid")

    # `candidate` contains the main candidate profile object returned by the
    # service layer
    #   - At the moment this is a plain dictionary because the profile fields
    #     are still evolving with the prototype schema.
    #   - This field is required because the route only returns this model when
    #     a candidate has been found.
    candidate: dict[str, Any] = Field(
        description="Canonical candidate profile data.",
    )

    # `skills` contains the skill rows linked to the candidate
    #   - This defaults to an empty list so API clients do not need to handle
    #     `null` when a candidate has no skills.
    #   - Keeping this as a list also matches the output shape from the current
    #     service helper.
    skills: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Skills linked to the candidate.",
    )


class CandidateResumeSearchResult(BaseModel):
    """
    One ranked current-resume match returned by the candidate search endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    person_id: str
    full_name: str | None = None
    current_title: str | None = None
    candidate_status: str | None = None
    current_company_name: str | None = None
    resume_updated_at: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    document_source_uri: str | None = None
    match_score: float
    retrieval_sources: list[str] = Field(default_factory=list)
    text_rank: int | None = None
    semantic_rank: int | None = None
    text_score: float | None = None
    semantic_score: float | None = None
    semantic_block_type: str | None = None
    semantic_block_label: str | None = None
    source_systems: list[str] = Field(default_factory=list)
    source_category: str = "unknown"
    match_excerpt: str | None = None


class CandidateResumeSearchResponse(BaseModel):
    """
    Response envelope for canonical current-resume search results.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        description="Normalized free-text query used for the resume search.",
    )
    limit: int = Field(
        description="Maximum number of ranked results requested.",
    )
    results: list[CandidateResumeSearchResult] = Field(
        default_factory=list,
        description="Ranked candidate matches from canonical current resumes.",
    )


class CompanyDirectoryResponse(BaseModel):
    """
    Response envelope for canonical company lookup suggestions.
    """

    model_config = ConfigDict(extra="forbid")

    count: int = Field(
        description="Total number of canonical company names returned.",
    )
    companies: list[str] = Field(
        default_factory=list,
        description="Canonical company names sorted alphabetically.",
    )


class CandidateCompanyDiscoveryResult(BaseModel):
    """
    One ranked candidate returned by the company discovery endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    person_id: str
    full_name: str | None = None
    current_title: str | None = None
    candidate_status: str | None = None
    current_company_name: str | None = None
    resume_updated_at: str | None = None
    document_id: str
    document_title: str | None = None
    document_source_uri: str | None = None
    company_match_source: str
    company_match_score: float
    match_excerpt: str | None = None


class CandidateCompanyDiscoveryResponse(BaseModel):
    """
    Response envelope for one company-to-candidate discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(
        description="Normalized company name used for the discovery query.",
    )
    limit: int = Field(
        description="Maximum number of ranked candidate matches requested.",
    )
    results: list[CandidateCompanyDiscoveryResult] = Field(
        default_factory=list,
        description="Ranked candidates already linked to or mentioning the company.",
    )


class CompanyJobDiscoveryResult(BaseModel):
    """
    One job returned by the company job-discovery endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str
    title: str | None = None
    status: str | None = None
    source: str | None = None
    owner_name: str | None = None
    location: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    updated_from_source_at: str | None = None
    company_id: str | None = None
    company_name: str | None = None
    hiring_manager_contact_id: str | None = None
    hiring_manager_person_id: str | None = None
    hiring_manager_name: str | None = None
    hiring_manager_email: str | None = None
    hiring_manager_phone: str | None = None
    hiring_manager_role_title: str | None = None
    company_match_source: str


class CompanyJobDiscoveryResponse(BaseModel):
    """
    Response envelope for one company-to-job discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(
        description="Normalized company name used for the job discovery query.",
    )
    limit: int = Field(
        description="Maximum number of jobs requested.",
    )
    results: list[CompanyJobDiscoveryResult] = Field(
        default_factory=list,
        description="Recent canonical jobs already linked to the company.",
    )


class CompanyContactDiscoveryResult(BaseModel):
    """
    One contact or hiring manager returned by the company-contact discovery endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    contact_id: str
    person_id: str
    full_name: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    headline: str | None = None
    company_id: str | None = None
    company_name: str | None = None
    role_title: str | None = None
    contact_type: str | None = None
    seniority: str | None = None
    is_hiring_manager: bool
    role_is_current: bool | None = None
    role_start_date: str | None = None
    role_end_date: str | None = None
    company_match_source: str


class CompanyContactDiscoveryResponse(BaseModel):
    """
    Response envelope for one company-to-contact discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(
        description="Normalized company name used for the contact discovery query.",
    )
    limit: int = Field(
        description="Maximum number of contacts requested.",
    )
    results: list[CompanyContactDiscoveryResult] = Field(
        default_factory=list,
        description="Contacts and hiring managers already linked to the company.",
    )


class CompanyInteractionDiscoveryResult(BaseModel):
    """
    One recent interaction returned by the company-interaction discovery endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    interaction_type: str | None = None
    occurred_at: str | None = None
    subject: str | None = None
    summary: str | None = None
    body: str | None = None
    source_system: str | None = None
    person_id: str | None = None
    candidate_id: str | None = None
    company_id: str | None = None
    company_name: str | None = None
    full_name: str | None = None
    role_title: str | None = None
    contact_id: str | None = None
    job_id: str | None = None
    job_title: str | None = None
    candidate_last_contacted_at: str | None = None
    matched_entity_type: str


class CompanyInteractionDiscoveryResponse(BaseModel):
    """
    Response envelope for one company-to-interaction discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(
        description="Normalized company name used for the interaction discovery query.",
    )
    limit: int = Field(
        description="Maximum number of interactions requested.",
    )
    results: list[CompanyInteractionDiscoveryResult] = Field(
        default_factory=list,
        description="Recent interaction evidence for people linked to the company.",
    )


class CompanyOpportunityDiscoveryResult(BaseModel):
    """
    One opportunity returned by the company opportunity-discovery endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    title: str | None = None
    smart_summary: str | None = None
    stage: str | None = None
    last_contact_at: str | None = None
    next_task_at: str | None = None
    value: float | None = None
    company_id: str | None = None
    company_name: str | None = None
    contact_id: str | None = None
    contact_person_id: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_role_title: str | None = None
    company_match_source: str


class CompanyOpportunityDiscoveryResponse(BaseModel):
    """
    Response envelope for one company-to-opportunity discovery query.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(
        description="Normalized company name used for the opportunity discovery query.",
    )
    limit: int = Field(
        description="Maximum number of opportunities requested.",
    )
    results: list[CompanyOpportunityDiscoveryResult] = Field(
        default_factory=list,
        description="Recent opportunities already linked to the company.",
    )


class CandidateCompanyLeadDiscoveryResponse(BaseModel):
    """
    Candidate-first outreach view for one target company.
    """

    model_config = ConfigDict(extra="forbid")

    candidate: dict[str, Any] = Field(
        description="Canonical candidate profile data for the selected candidate.",
    )
    skills: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured skill rows already linked to the candidate.",
    )
    skill_names: list[str] = Field(
        default_factory=list,
        description="Deduplicated skill-name summary for quick recruiter review.",
    )
    company_name: str = Field(
        description="Normalized target company name used for discovery.",
    )
    candidate_already_at_company: bool = Field(
        description="Whether the selected candidate is already marked as working at the target company.",
    )
    peer_candidates: list[CandidateCompanyDiscoveryResult] = Field(
        default_factory=list,
        description="Other candidates in the database already linked to the target company.",
    )
    contacts: list[CompanyContactDiscoveryResult] = Field(
        default_factory=list,
        description="Known contacts and hiring managers already linked to the target company.",
    )
    interactions: list[CompanyInteractionDiscoveryResult] = Field(
        default_factory=list,
        description="Recent interaction evidence for people linked to the target company.",
    )
    jobs: list[CompanyJobDiscoveryResult] = Field(
        default_factory=list,
        description="Canonical jobs already linked to the target company.",
    )
    opportunities: list[CompanyOpportunityDiscoveryResult] = Field(
        default_factory=list,
        description="Canonical opportunities already linked to the target company.",
    )


class UploadedResumeSearchResponse(BaseModel):
    """
    Response envelope for transient uploaded-resume semantic search.
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str | None = None
    content_type: str | None = None
    extractor: str | None = None
    page_count: int | None = None
    character_count: int = Field(
        description="Character count of the cleaned extracted text used for search.",
    )
    cleaned_text_preview: str = Field(
        description="Short preview of the cleaned extracted text used for retrieval.",
    )
    limit: int = Field(
        description="Maximum number of ranked results requested.",
    )
    results: list[CandidateResumeSearchResult] = Field(
        default_factory=list,
        description="Ranked candidate matches from the uploaded CV query.",
    )


class UploadedResumeSearchRequest(BaseModel):
    """
    Request body for transient uploaded-resume semantic search.
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    content_base64: str = Field(
        min_length=1,
        max_length=MAX_UPLOAD_BASE64_CHARACTERS,
        description="Base64-encoded uploaded CV file content.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of ranked candidate matches to return.",
    )


class UploadedJobDescriptionExtractResponse(BaseModel):
    """
    Response envelope for transient uploaded job-description extraction.
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str | None = None
    content_type: str | None = None
    extractor: str | None = None
    page_count: int | None = None
    character_count: int = Field(
        description="Character count of the cleaned extracted text.",
    )
    cleaned_text_preview: str = Field(
        description="Short preview of the cleaned extracted text.",
    )
    job_description_text: str = Field(
        description="Cleaned full text extracted from the uploaded file.",
    )


class UploadedJobDescriptionExtractRequest(BaseModel):
    """
    Request body for transient uploaded job-description extraction.
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    content_base64: str = Field(
        min_length=1,
        max_length=MAX_UPLOAD_BASE64_CHARACTERS,
        description="Base64-encoded uploaded job-description file content.",
    )


class CandidateJobDescriptionMatchRequest(BaseModel):
    """
    Request body for shortlist matching against one free-text job description.
    """

    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        min_length=1,
        max_length=MAX_LLM_INPUT_CHARACTERS,
        description="Free-text role brief used to retrieve and rank candidates.",
    )
    retrieval_limit: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of retrieved candidates to pass into reranking.",
    )
    shortlist_limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of final shortlisted candidates to return.",
    )


class CandidateJobDescriptionShortlistItem(BaseModel):
    """
    One shortlisted candidate returned by the match endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    person_id: str
    full_name: str | None = None
    current_title: str | None = None
    candidate_status: str | None = None
    current_company_name: str | None = None
    resume_updated_at: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    document_source_uri: str | None = None
    retrieval_score: float
    retrieval_sources: list[str] = Field(default_factory=list)
    text_rank: int | None = None
    semantic_rank: int | None = None
    text_score: float | None = None
    semantic_score: float | None = None
    semantic_block_type: str | None = None
    semantic_block_label: str | None = None
    source_systems: list[str] = Field(default_factory=list)
    source_category: str = "unknown"
    graph_context_score: float | None = None
    ranking_input_score: float | None = None
    fit_score: int
    fit_summary: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    match_excerpt: str | None = None
    graph_evidence: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Bounded graph-style evidence assembled from linked canonical "
            "entities such as skills, contacts, interactions, jobs, and "
            "opportunities."
        ),
    )


class CandidateJobDescriptionMatchResponse(BaseModel):
    """
    Response envelope for the top-candidate shortlist against a role brief.
    """

    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        description="Normalized job description used for retrieval and ranking.",
    )
    retrieval_limit: int = Field(
        description="Number of candidates considered for reranking.",
    )
    shortlist_limit: int = Field(
        description="Target maximum number of final shortlisted candidates.",
    )
    retrieved_candidate_count: int = Field(
        description="Number of candidates retrieved before reranking.",
    )
    shortlisted_candidates: list[CandidateJobDescriptionShortlistItem] = Field(
        default_factory=list,
        description="Final ranked shortlist for the supplied job description.",
    )


__all__ = [
    "CandidateCompanyDiscoveryResponse",
    "CandidateCompanyDiscoveryResult",
    "CandidateCompanyLeadDiscoveryResponse",
    "CompanyContactDiscoveryResponse",
    "CompanyContactDiscoveryResult",
    "CompanyInteractionDiscoveryResponse",
    "CompanyInteractionDiscoveryResult",
    "CompanyJobDiscoveryResponse",
    "CompanyJobDiscoveryResult",
    "CompanyOpportunityDiscoveryResponse",
    "CompanyOpportunityDiscoveryResult",
    "CandidateProfileResponse",
    "CandidateJobDescriptionMatchRequest",
    "CandidateJobDescriptionMatchResponse",
    "CandidateJobDescriptionShortlistItem",
    "UploadedResumeSearchRequest",
    "UploadedJobDescriptionExtractRequest",
    "CandidateResumeSearchResponse",
    "CandidateResumeSearchResult",
    "UploadedResumeSearchResponse",
    "UploadedJobDescriptionExtractResponse",
]
