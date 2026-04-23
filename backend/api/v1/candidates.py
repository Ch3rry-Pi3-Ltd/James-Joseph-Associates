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

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.schemas.candidates import CandidateProfileResponse
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.services.candidate_profiles import build_candidate_profile


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


__all__ = ["router"]
