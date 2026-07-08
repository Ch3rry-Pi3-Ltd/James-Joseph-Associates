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
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, Response

from backend.schemas.candidates import (
    CandidateCompanyDiscoveryResponse,
    CandidateJobDescriptionMatchRequest,
    CandidateJobDescriptionMatchResponse,
    CandidateProfileResponse,
    CandidateResumeSearchResponse,
    CompanyJobDiscoveryResponse,
    UploadedResumeSearchRequest,
    UploadedResumeSearchResponse,
)
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.services.candidate_matching import (
    CandidateMatchingError,
    build_candidate_job_description_shortlist,
)
from backend.services.candidate_profiles import (
    build_candidate_profile,
    discover_candidates_by_company,
    discover_jobs_by_company,
    search_candidate_resumes,
)
from backend.services.candidate_resume_files import (
    CandidateResumeFileAccessError,
    fetch_candidate_current_resume_file,
)
from backend.services.uploaded_resume_matching import (
    UploadedResumeSearchError,
    search_candidates_by_uploaded_resume,
)


router = APIRouter(prefix="/candidates", tags=["candidates"])


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
        "Content-Disposition": f'{disposition_type}; filename="{file_name}"',
        "X-Document-Id": result["document_id"],
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

    return CandidateJobDescriptionMatchResponse(**result)


__all__ = ["router"]
