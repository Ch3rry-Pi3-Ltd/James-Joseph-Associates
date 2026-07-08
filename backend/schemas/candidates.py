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
    document_id: str
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

    file_name: str | None = None
    content_type: str | None = None
    content_base64: str = Field(
        min_length=1,
        description="Base64-encoded uploaded CV file content.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of ranked candidate matches to return.",
    )


class CandidateJobDescriptionMatchRequest(BaseModel):
    """
    Request body for shortlist matching against one free-text job description.
    """

    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(
        min_length=1,
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
    document_id: str
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
    fit_score: int
    fit_summary: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    match_excerpt: str | None = None


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
    "CompanyJobDiscoveryResponse",
    "CompanyJobDiscoveryResult",
    "CandidateProfileResponse",
    "CandidateJobDescriptionMatchRequest",
    "CandidateJobDescriptionMatchResponse",
    "CandidateJobDescriptionShortlistItem",
    "UploadedResumeSearchRequest",
    "CandidateResumeSearchResponse",
    "CandidateResumeSearchResult",
    "UploadedResumeSearchResponse",
]
