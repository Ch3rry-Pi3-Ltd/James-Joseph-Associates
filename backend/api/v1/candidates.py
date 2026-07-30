"""
Candidate endpoints for version 1 of the intelligence API.

This module defines the first candidate-focused read endpoint in the backend.

It gives the rest of the repository a stable way to verify:

- the API can expose one candidate profile view
- route handlers can call the candidate service layer
- the backend can return candidate data and linked skills together
- missing candidates return a controlled 404 response

Keeping candidate endpoints in their own module makes the project easier to
extend because:

- `backend.api.router` can stay focused on route registration
- candidate route logic stays separate from health and Make.com endpoints
- future candidate endpoints can follow the same local pattern
- the service layer remains reusable outside HTTP routes

In plain language:

- this module answers the question:

    "How does the API return one candidate profile?"

- it does not run SQL directly
- it does not define database tables
- it does not contain matching logic
- it only turns service-layer results into HTTP responses
"""

import base64
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from backend.schemas.candidates import (
    CandidateCompanyDiscoveryResponse,
    CandidateCompanyLeadDiscoveryResponse,
    CandidateJobDescriptionMatchRequest,
    CandidateJobDescriptionMatchResponse,
    CandidateMatchFeedbackRequest,
    CandidateMatchFeedbackResponse,
    CandidateShortlistExportRequest,
    CandidateProfileResponse,
    CandidateResumeSearchResponse,
    CompanyDirectoryResponse,
    CompanyContactDiscoveryResponse,
    CompanyInteractionDiscoveryResponse,
    CompanyJobDiscoveryResponse,
    CompanyOpportunityDiscoveryResponse,
    UploadedJobDescriptionExtractRequest,
    UploadedJobDescriptionExtractResponse,
    UploadedResumeSearchRequest,
    UploadedResumeSearchResponse,
    MAX_UPLOAD_BYTES,
)
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.services.candidate_matching import (
    CandidateMatchingError,
    build_candidate_job_description_shortlist,
)
from backend.services.candidate_match_feedback import save_candidate_match_feedback
from backend.services.candidate_profiles import (
    build_candidate_profile,
    discover_candidates_by_company,
    discover_company_leads_for_candidate,
    discover_contacts_by_company,
    discover_interactions_by_company,
    discover_jobs_by_company,
    discover_opportunities_by_company,
    list_company_directory,
    search_candidate_resumes,
)
from backend.services.candidate_resume_files import (
    CandidateResumeFileAccessError,
    fetch_candidate_current_resume_file,
)
from backend.services.candidate_shortlist_export import (
    build_candidate_shortlist_export_package,
)
from backend.services.uploaded_resume_matching import (
    UploadedResumeSearchError,
    search_candidates_by_uploaded_resume,
)
from backend.services.uploaded_job_description import (
    UploadedJobDescriptionError,
    extract_uploaded_job_description,
)


router = APIRouter(prefix="/candidates", tags=["candidates"])


def _build_content_disposition(disposition_type: str, file_name: str) -> str:
    """Build a header-safe filename without losing Unicode download names."""

    normalized_name = file_name.replace("\r", "_").replace("\n", "_")
    ascii_name = normalized_name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r'[^A-Za-z0-9._ ()\-]', "_", ascii_name).strip()
    ascii_name = ascii_name[:180] or "resume"
    header_value = f'{disposition_type}; filename="{ascii_name}"'

    if ascii_name != normalized_name:
        header_value += f"; filename*=UTF-8''{quote(normalized_name, safe='')}"

    return header_value


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """
    Build a standard API error response for candidate endpoints.

    Parameters
    ----------
    status_code : int
        HTTP status code to return.

    code : str
        Public API error code.

    message : str
        Safe human-readable error message.

    details : list[dict[str, Any]] | None
        Optional safe structured error details.

    Returns
    -------
    JSONResponse
        FastAPI response containing the standard `{"error": ...}` shape.

    Notes
    -----
    - This local helper avoids repeating the same error-response construction
      inside candidate endpoints.
    - The response body uses the project's standard top-level error shape:

        {
            "error": {
                "code": "...",
                "message": "...",
                "details": [...]
            }
        }

    - This helper only builds the response object.
    - It does not decide when an endpoint should return an error.

    Example
    -------
    A not-found response can be built like this:

        build_error_response(
            status_code=404,
            code="not_found",
            message="Candidate profile was not found.",
            details=[{"candidate_id": "example-id"}],
        )
    """

    error_response = ApiErrorResponse(
        error=ApiError(
            code=code,
            message=message,
            details=details or [],
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(),
    )


@router.get(
    "/company-directory",
    response_model=CompanyDirectoryResponse,
)
def get_company_directory_route() -> CompanyDirectoryResponse:
    """
    Return canonical company names for recruiter-facing picker controls.
    """

    return CompanyDirectoryResponse(**list_company_directory())

# Register a GET endpoint on this router
#   - `"/{candidate_id}/profile"` means the route expects a path value such as:
#
#           /candidates/33333333-3333-3333-3333-333333333331/profile
#
#   - Because this router itself has `prefix="/candidates"` and the top-level
#     API router has `prefix="/api/v1"`, the full public path becomes:
#
#           /api/v1/candidates/{candidate_id}/profile
#
#   - `response_model=CandidateProfileResponse` tells FastAPI:
#       - what successful response shape this route should return
#       - how to validate that response before sending it
#       - how to document the 200 response in the generated OpenAPI schema
#
#   - `responses={404: ...}` adds extra OpenAPI documentation for the not-found case.
#       - This does not create the 404 response by itself.
#       - The route function still has to explicitly return that error when the
#         candidate does not exist.
#       - What this does give us is:
#           - the documented error model
#           - a clearer generated API schema
#           - better Swagger / OpenAPI docs for clients
@router.get(
    "/{candidate_id}/profile",
    response_model=CandidateProfileResponse,
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "Candidate was not found.",
        }
    },
)
def get_candidate_profile_route(
    candidate_id: str,
) -> CandidateProfileResponse | JSONResponse:
    """
    Return one combined candidate profile view.

    Parameters
    ----------
    candidate_id : str
        Canonical candidate UUID to look up.

    Returns
    -------
    CandidateProfileResponse | JSONResponse
        Combined candidate profile response when the candidate exists.

        Standard API error response when the candidate does not exist.

    Route
    -----
    This module contributes:

        GET /api/v1/candidates/{candidate_id}/profile

    The `/api/v1` prefix is applied by `backend.api.router`.

    Notes
    -----
    - This route does not query Postgres directly.
    - It delegates the data lookup to `build_candidate_profile(...)`.
    - If the candidate does not exist, the route returns HTTP 404 using the
      project's standard API error shape.
    - If the candidate does exist, the route returns one combined object with:

        - `candidate`
        - `skills`

    Example
    -------
    A successful request looks like:

        GET /api/v1/candidates/33333333-3333-3333-3333-333333333331/profile

    And a successful response looks like:

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

    - ask the service layer for one candidate profile
    - return the combined candidate + skills structure if found
    - otherwise return a 404 error
    """

    profile = build_candidate_profile(candidate_id)

    if profile is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Candidate profile was not found.",
            details=[{"candidate_id": candidate_id}],
        )

    return CandidateProfileResponse(**profile)


@router.get(
    "/{candidate_id}/current-resume",
    response_model=None,
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "Current resume was not found for this candidate.",
        },
        501: {
            "model": ApiErrorResponse,
            "description": "Current resume source is not downloadable yet.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "Current resume download failed.",
        },
    },
)
def get_candidate_current_resume_route(
    candidate_id: str,
    download: bool = Query(
        default=False,
        description="Set to true to force attachment download instead of inline display.",
    ),
) -> Response:
    """
    Stream the candidate's linked current resume file when the source is resolvable.
    """

    try:
        result = fetch_candidate_current_resume_file(candidate_id)
    except CandidateResumeFileAccessError as exc:
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    file_name = result["file_name"]
    content_type = result["content_type"]
    disposition_type = "attachment" if download else "inline"

    headers = {
        "Content-Disposition": _build_content_disposition(
            disposition_type,
            file_name,
        ),
        "X-Document-Id": result["document_id"],
        "X-Content-Type-Options": "nosniff",
    }

    return Response(
        content=result["content_bytes"],
        media_type=content_type,
        headers=headers,
    )


@router.get(
    "/discover-by-company",
    response_model=CandidateCompanyDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Company discovery query was invalid.",
        }
    },
)
def discover_candidates_by_company_route(
    company_name: str = Query(
        description="Company name used to find linked candidate records.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of ranked candidate matches to return.",
    ),
) -> CandidateCompanyDiscoveryResponse | JSONResponse:
    """
    Find candidates already linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Company discovery query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_candidates_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    return CandidateCompanyDiscoveryResponse(**result)


@router.get(
    "/discover-jobs-by-company",
    response_model=CompanyJobDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Company job discovery query was invalid.",
        }
    },
)
def discover_jobs_by_company_route(
    company_name: str = Query(
        description="Company name used to find linked job records.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of jobs to return.",
    ),
) -> CompanyJobDiscoveryResponse | JSONResponse:
    """
    Find canonical jobs already linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Company job discovery query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_jobs_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    return CompanyJobDiscoveryResponse(**result)


@router.get(
    "/discover-contacts-by-company",
    response_model=CompanyContactDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Company contact discovery query was invalid.",
        }
    },
)
def discover_contacts_by_company_route(
    company_name: str = Query(
        description="Company name used to find linked contact and hiring-manager records.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of contacts to return.",
    ),
) -> CompanyContactDiscoveryResponse | JSONResponse:
    """
    Find contacts and hiring managers already linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Company contact discovery query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_contacts_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    return CompanyContactDiscoveryResponse(**result)


@router.get(
    "/discover-interactions-by-company",
    response_model=CompanyInteractionDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Company interaction discovery query was invalid.",
        }
    },
)
def discover_interactions_by_company_route(
    company_name: str = Query(
        description="Company name used to find prior interaction evidence.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of interaction rows to return.",
    ),
) -> CompanyInteractionDiscoveryResponse | JSONResponse:
    """
    Find recent interaction evidence for people linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Company interaction discovery query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_interactions_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    return CompanyInteractionDiscoveryResponse(**result)


@router.get(
    "/discover-opportunities-by-company",
    response_model=CompanyOpportunityDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Company opportunity discovery query was invalid.",
        }
    },
)
def discover_opportunities_by_company_route(
    company_name: str = Query(
        description="Company name used to find linked opportunity records.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of opportunities to return.",
    ),
) -> CompanyOpportunityDiscoveryResponse | JSONResponse:
    """
    Find canonical opportunities already linked to one company name.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Company opportunity discovery query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_opportunities_by_company(
        company_name=normalized_company_name,
        limit=limit,
    )
    return CompanyOpportunityDiscoveryResponse(**result)


@router.get(
    "/{candidate_id}/discover-company-leads",
    response_model=CandidateCompanyLeadDiscoveryResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Candidate company-lead query was invalid.",
        },
        404: {
            "model": ApiErrorResponse,
            "description": "Candidate profile was not found.",
        },
    },
)
def discover_company_leads_for_candidate_route(
    candidate_id: str,
    company_name: str = Query(
        description="Target company name used to find contacts, jobs, and interaction evidence for one candidate.",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of contacts, jobs, interactions, and peer candidates to return.",
    ),
) -> CandidateCompanyLeadDiscoveryResponse | JSONResponse:
    """
    Return a candidate-first outreach view for one target company.
    """

    normalized_company_name = company_name.strip()
    if normalized_company_name == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Candidate company-lead query must not be blank.",
            details=[{"company_name": company_name}],
        )

    result = discover_company_leads_for_candidate(
        candidate_id=candidate_id,
        company_name=normalized_company_name,
        limit=limit,
    )
    if result is None:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Candidate profile was not found.",
            details=[{"candidate_id": candidate_id}],
        )

    return CandidateCompanyLeadDiscoveryResponse(**result)


@router.get(
    "/search-resumes",
    response_model=CandidateResumeSearchResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Resume search query was invalid.",
        }
    },
)
def search_candidate_resumes_route(
    query: str = Query(
        description="Free-text query used to search canonical current resumes.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of ranked candidate matches to return.",
    ),
) -> CandidateResumeSearchResponse | JSONResponse:
    """
    Search the canonical current-resume corpus using one free-text query.
    """

    normalized_query = query.strip()
    if normalized_query == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Resume search query must not be blank.",
            details=[{"query": query}],
        )

    result = search_candidate_resumes(
        query=normalized_query,
        limit=limit,
    )
    return CandidateResumeSearchResponse(**result)


@router.post(
    "/search-uploaded-resume",
    response_model=UploadedResumeSearchResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Uploaded CV could not be processed.",
        },
        415: {
            "model": ApiErrorResponse,
            "description": "Uploaded CV format is not supported.",
        },
    },
)
async def search_uploaded_resume_route(
    request: UploadedResumeSearchRequest,
) -> UploadedResumeSearchResponse | JSONResponse:
    """
    Extract one uploaded CV and use it as a transient query against the corpus.
    """

    try:
        content_bytes = base64.b64decode(request.content_base64, validate=True)
    except Exception:
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Uploaded CV payload must contain valid base64 content.",
            details=[{"field": "content_base64"}],
        )

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        return build_error_response(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="upload_too_large",
            message="Uploaded CV exceeds the maximum supported file size.",
            details=[{"max_upload_bytes": MAX_UPLOAD_BYTES}],
        )

    try:
        result = search_candidates_by_uploaded_resume(
            content_bytes=content_bytes,
            file_name=request.file_name,
            content_type=request.content_type,
            limit=request.limit,
        )
    except UploadedResumeSearchError as exc:
        normalized_message = exc.message.lower()
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        error_code = "resume_source_not_supported"
        if "supported" not in normalized_message and "format" not in normalized_message:
            status_code = status.HTTP_400_BAD_REQUEST
            error_code = "validation_error"

        return build_error_response(
            status_code=status_code,
            code=error_code,
            message=exc.message,
            details=[{"stage": exc.stage}, *exc.details],
        )

    return UploadedResumeSearchResponse(**result)


@router.post(
    "/extract-uploaded-job-description",
    response_model=UploadedJobDescriptionExtractResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Uploaded job description could not be processed.",
        },
        415: {
            "model": ApiErrorResponse,
            "description": "Uploaded job description format is not supported.",
        },
    },
)
async def extract_uploaded_job_description_route(
    request: UploadedJobDescriptionExtractRequest,
) -> UploadedJobDescriptionExtractResponse | JSONResponse:
    """
    Extract one uploaded job description into cleaned text for the Match UI.
    """

    try:
        content_bytes = base64.b64decode(request.content_base64, validate=True)
    except Exception:
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Uploaded job description payload must contain valid base64 content.",
            details=[{"field": "content_base64"}],
        )

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        return build_error_response(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="upload_too_large",
            message="Uploaded job description exceeds the maximum supported file size.",
            details=[{"max_upload_bytes": MAX_UPLOAD_BYTES}],
        )

    try:
        result = extract_uploaded_job_description(
            content_bytes=content_bytes,
            file_name=request.file_name,
            content_type=request.content_type,
        )
    except UploadedJobDescriptionError as exc:
        normalized_message = exc.message.lower()
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        error_code = "resume_source_not_supported"
        if "supported" not in normalized_message and "format" not in normalized_message:
            status_code = status.HTTP_400_BAD_REQUEST
            error_code = "validation_error"

        return build_error_response(
            status_code=status_code,
            code=error_code,
            message=exc.message,
            details=[{"stage": exc.stage}, *exc.details],
        )

    return UploadedJobDescriptionExtractResponse(**result)


@router.post(
    "/match-job-description",
    response_model=CandidateJobDescriptionMatchResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Job description request was invalid.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Candidate shortlisting failed.",
        },
    },
)
def match_job_description_route(
    request: CandidateJobDescriptionMatchRequest,
) -> CandidateJobDescriptionMatchResponse | JSONResponse:
    """
    Retrieve and shortlist the strongest candidates for one job description.
    """

    normalized_job_description = request.job_description.strip()
    if normalized_job_description == "":
        return build_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="Job description must not be blank.",
            details=[{"field": "job_description"}],
        )

    try:
        result = build_candidate_job_description_shortlist(
            job_description=normalized_job_description,
            retrieval_limit=request.retrieval_limit,
            shortlist_limit=request.shortlist_limit,
        )
    except CandidateMatchingError as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="matching_failed",
            message=exc.message,
            details=[{"stage": exc.stage}, *exc.details],
        )
    except Exception as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Candidate shortlisting failed unexpectedly.",
            details=[{"error_type": exc.__class__.__name__}],
        )

    try:
        return CandidateJobDescriptionMatchResponse(**result)
    except ValidationError as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Candidate shortlisting response validation failed.",
            details=[{"error_type": exc.__class__.__name__}],
        )


@router.post(
    "/export-shortlist",
    response_model=None,
    responses={
        500: {
            "model": ApiErrorResponse,
            "description": "Shortlist export package could not be generated.",
        }
    },
)
def export_candidate_shortlist_route(
    request: CandidateShortlistExportRequest,
) -> Response:
    """Return a Word shortlist and retrievable CV files in one ZIP package."""

    try:
        package = build_candidate_shortlist_export_package(
            match_run_id=str(request.match_run_id),
            role_title=request.role_title,
            job_description=request.job_description,
            shortlisted_candidates=[
                candidate.model_dump()
                for candidate in request.shortlisted_candidates
            ],
        )
    except Exception as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="shortlist_export_failed",
            message="Shortlist export package could not be generated.",
            details=[{"error_type": exc.__class__.__name__}],
        )

    return Response(
        content=package["content_bytes"],
        media_type="application/zip",
        headers={
            "Content-Disposition": _build_content_disposition(
                "attachment",
                package["file_name"],
            ),
            "X-Exported-CV-Count": str(package["exported_cv_count"]),
            "X-Unavailable-CV-Count": str(package["unavailable_cv_count"]),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/match-feedback",
    response_model=CandidateMatchFeedbackResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Authenticated reviewer identity was not available.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Candidate match feedback could not be stored.",
        },
    },
)
def save_candidate_match_feedback_route(
    request: CandidateMatchFeedbackRequest,
    workspace_user_id: str | None = Header(
        default=None,
        alias="X-Workspace-User-Id",
    ),
    workspace_user_email: str | None = Header(
        default=None,
        alias="X-Workspace-User-Email",
    ),
) -> CandidateMatchFeedbackResponse | JSONResponse:
    """Store one authenticated recruiter's judgement on a shortlist result."""

    normalized_user_id = (workspace_user_id or "").strip()
    if normalized_user_id == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Authenticated reviewer identity is required.",
        )

    try:
        result = save_candidate_match_feedback(
            match_run_id=str(request.match_run_id),
            candidate_id=str(request.candidate_id),
            document_id=(
                str(request.document_id)
                if request.document_id is not None
                else None
            ),
            reviewer_user_id=normalized_user_id,
            reviewer_email=workspace_user_email,
            feedback_value=request.feedback_value,
            feedback_reason=request.feedback_reason,
            job_description=request.job_description,
            shortlist_rank=request.shortlist_rank,
            fit_score=request.fit_score,
            retrieval_score=request.retrieval_score,
            graph_context_score=request.graph_context_score,
            ranking_input_score=request.ranking_input_score,
            source_category=request.source_category,
        )
    except Exception as exc:
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Candidate match feedback could not be stored.",
            details=[{"error_type": exc.__class__.__name__}],
        )

    return CandidateMatchFeedbackResponse(
        feedback_id=result["id"],
        match_run_id=result["match_run_id"],
        candidate_id=result["candidate_id"],
        reviewer_user_id=result["reviewer_user_id"],
        reviewer_email=result.get("reviewer_email"),
        feedback_value=result["feedback_value"],
        feedback_reason=result.get("feedback_reason"),
        created_at=result["created_at"],
        updated_at=result["updated_at"],
    )


__all__ = ["router"]
