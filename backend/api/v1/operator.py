"""
Protected read-only operator endpoints for MCP/API-style recruiter clients.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from backend.core.security import check_request_bearer_token
from backend.schemas.errors import ApiError, ApiErrorResponse
from backend.schemas.operator import (
    OperatorCandidateProfileResponse,
    OperatorCandidateResumeReferenceResponse,
    OperatorCompanyContextRequest,
    OperatorCompanyContextResponse,
    OperatorCompanyDirectoryResponse,
    OperatorCompanyLeadDiscoveryRequest,
    OperatorMemoryClearRequest,
    OperatorMemoryClearResponse,
    OperatorQuestionAnswerRequest,
    OperatorQuestionAnswerResponse,
    OperatorSearchCandidatesRequest,
    OperatorSearchCandidatesResponse,
)
from backend.services import mcp_read_adapter
from backend.services.mcp_read_adapter import McpReadAdapterError
from backend.services.operator_session_memory import clear_operator_memory
from backend.services.recruiter_question_answering import (
    RecruiterQuestionAnsweringError,
    answer_recruiter_question,
)
from backend.settings import get_settings

router = APIRouter(prefix="/operator", tags=["operator"])


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
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


def _authorize_operator_request(request: Request) -> JSONResponse | None:
    settings = get_settings()
    expected_token = getattr(settings, "admin_api_token", "")
    if not isinstance(expected_token, str) or expected_token.strip() == "":
        expected_token = getattr(settings, "make_api_token", "")

    if not isinstance(expected_token, str) or expected_token.strip() == "":
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Operator API bearer token is not configured.",
        )

    auth_result = check_request_bearer_token(
        request=request,
        expected_token=expected_token,
    )
    if auth_result.is_authorised:
        return None

    return build_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthorized",
        message="Valid operator bearer credentials were not provided.",
    )


def _build_adapter_error_response(exc: McpReadAdapterError) -> JSONResponse:
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=[
            {"tool": exc.tool},
            *exc.details,
        ],
    )


def _build_question_answer_error_response(
    exc: RecruiterQuestionAnsweringError,
) -> JSONResponse:
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=[
            {"stage": exc.stage},
            *exc.details,
        ],
    )


@router.get(
    "/company-directory",
    response_model=OperatorCompanyDirectoryResponse,
    responses={401: {"model": ApiErrorResponse}},
)
def get_operator_company_directory_route(
    request: Request,
    prefix: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> OperatorCompanyDirectoryResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    return OperatorCompanyDirectoryResponse(
        **mcp_read_adapter.list_company_directory(
            prefix=prefix,
            limit=limit,
        )
    )


@router.post(
    "/search-candidates-for-role",
    response_model=OperatorSearchCandidatesResponse,
    responses={401: {"model": ApiErrorResponse}},
)
def search_candidates_for_role_route(
    payload: OperatorSearchCandidatesRequest,
    request: Request,
) -> OperatorSearchCandidatesResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        result = mcp_read_adapter.search_candidates_for_role(**payload.model_dump())
    except McpReadAdapterError as exc:
        return _build_adapter_error_response(exc)

    return OperatorSearchCandidatesResponse(**result)


@router.get(
    "/candidates/{candidate_id}/profile",
    response_model=OperatorCandidateProfileResponse,
    responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
def get_operator_candidate_profile_route(
    candidate_id: str,
    request: Request,
    linked_context_limit: int = Query(default=5, ge=1, le=20),
) -> OperatorCandidateProfileResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        result = mcp_read_adapter.get_candidate_profile(
            candidate_id=candidate_id,
            linked_context_limit=linked_context_limit,
        )
    except McpReadAdapterError as exc:
        return _build_adapter_error_response(exc)

    return OperatorCandidateProfileResponse(**result)


@router.get(
    "/candidates/{candidate_id}/current-resume",
    response_model=OperatorCandidateResumeReferenceResponse,
    responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
def get_operator_candidate_resume_route(
    candidate_id: str,
    request: Request,
) -> OperatorCandidateResumeReferenceResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        result = mcp_read_adapter.get_candidate_current_resume(
            candidate_id=candidate_id,
        )
    except McpReadAdapterError as exc:
        return _build_adapter_error_response(exc)

    return OperatorCandidateResumeReferenceResponse(**result)


@router.post(
    "/search-company-context",
    response_model=OperatorCompanyContextResponse,
    responses={401: {"model": ApiErrorResponse}},
)
def search_company_context_route(
    payload: OperatorCompanyContextRequest,
    request: Request,
) -> OperatorCompanyContextResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        result = mcp_read_adapter.search_company_context(**payload.model_dump())
    except McpReadAdapterError as exc:
        return _build_adapter_error_response(exc)

    return OperatorCompanyContextResponse(**result)


@router.post(
    "/discover-company-leads",
    response_model=None,
    responses={401: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
def discover_company_leads_route(
    payload: OperatorCompanyLeadDiscoveryRequest,
    request: Request,
) -> dict[str, Any] | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        return mcp_read_adapter.discover_company_leads_for_candidate(
            **payload.model_dump()
        )
    except McpReadAdapterError as exc:
        return _build_adapter_error_response(exc)


@router.post(
    "/answer-question",
    response_model=OperatorQuestionAnswerResponse,
    responses={401: {"model": ApiErrorResponse}},
)
def answer_recruiter_question_route(
    payload: OperatorQuestionAnswerRequest,
    request: Request,
) -> OperatorQuestionAnswerResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    try:
        result = answer_recruiter_question(**payload.model_dump())
    except RecruiterQuestionAnsweringError as exc:
        return _build_question_answer_error_response(exc)

    return OperatorQuestionAnswerResponse(**result)


@router.post(
    "/memory/clear",
    response_model=OperatorMemoryClearResponse,
    responses={401: {"model": ApiErrorResponse}},
)
def clear_operator_memory_route(
    payload: OperatorMemoryClearRequest,
    request: Request,
) -> OperatorMemoryClearResponse | JSONResponse:
    authorization_error = _authorize_operator_request(request)
    if authorization_error is not None:
        return authorization_error

    clear_operator_memory(
        user_id=payload.user_id,
        conversation_id=payload.conversation_id,
    )
    return OperatorMemoryClearResponse(
        cleared=True,
        user_id=payload.user_id,
        conversation_id=payload.conversation_id,
    )
