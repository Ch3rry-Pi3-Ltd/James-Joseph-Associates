"""
Production remote MCP server exposing bounded read-only recruiter tools.
"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from fastapi.concurrency import run_in_threadpool
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from backend.schemas.operator import (
    OperatorCompanyContextRequest,
    OperatorCompanyLeadDiscoveryRequest,
    OperatorSearchCandidatesRequest,
)
from backend.services import mcp_read_adapter
from backend.services.mcp_operations import (
    audit_mcp_event_best_effort,
    build_mcp_argument_metadata,
)
from backend.services.mcp_read_adapter import McpReadAdapterError
from backend.settings import get_settings

_READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _split_allowlist(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_mcp_server() -> FastMCP:
    settings = get_settings()
    return FastMCP(
        name="James Joseph Associates Recruitment Intelligence",
        instructions=(
            "Use these read-only tools to retrieve bounded canonical recruitment "
            "evidence. Never claim that a record was changed, never infer missing "
            "facts, and cite returned candidate, company, contact, job, opportunity, "
            "interaction, or document identifiers when presenting conclusions."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_split_allowlist(settings.mcp_allowed_hosts),
            allowed_origins=_split_allowlist(settings.mcp_allowed_origins),
        ),
    )


mcp_server = _build_mcp_server()


@mcp_server.tool(
    title="Search candidates for a role",
    description=(
        "Search the canonical current-resume corpus for candidates matching a role "
        "brief. Optionally include the bounded recruiter shortlist."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def search_candidates_for_role(
    role_brief: str,
    ctx: Context,
    search_limit: int = 10,
    candidate_pool_limit: int = 25,
    shortlist_limit: int = 5,
    include_shortlist: bool = False,
) -> dict[str, Any]:
    arguments = {
        "role_brief": role_brief,
        "search_limit": search_limit,
        "candidate_pool_limit": candidate_pool_limit,
        "shortlist_limit": shortlist_limit,
        "include_shortlist": include_shortlist,
    }
    request = OperatorSearchCandidatesRequest.model_validate(arguments)
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="search_candidates_for_role",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.search_candidates_for_role(
            **request.model_dump()
        ),
    )


@mcp_server.tool(
    title="Get candidate profile",
    description=(
        "Return one canonical candidate, their skills, and bounded context linked "
        "through their current company."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_candidate_profile(
    candidate_id: str,
    ctx: Context,
    linked_context_limit: int = 5,
) -> dict[str, Any]:
    arguments = {
        "candidate_id": candidate_id,
        "linked_context_limit": linked_context_limit,
    }
    normalized_candidate_id = candidate_id.strip()
    if normalized_candidate_id == "":
        raise ToolError("Candidate ID must not be blank.")
    normalized_limit = max(1, min(int(linked_context_limit), 20))
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="get_candidate_profile",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.get_candidate_profile(
            candidate_id=normalized_candidate_id,
            linked_context_limit=normalized_limit,
        ),
    )


@mcp_server.tool(
    title="Get candidate current resume",
    description=(
        "Return the current resume document reference and provenance for one "
        "canonical candidate. This does not return raw database credentials."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_candidate_current_resume(
    candidate_id: str,
    ctx: Context,
) -> dict[str, Any]:
    arguments = {"candidate_id": candidate_id}
    normalized_candidate_id = candidate_id.strip()
    if normalized_candidate_id == "":
        raise ToolError("Candidate ID must not be blank.")
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="get_candidate_current_resume",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.get_candidate_current_resume(
            candidate_id=normalized_candidate_id
        ),
    )


@mcp_server.tool(
    title="Search company context",
    description=(
        "Return bounded candidates, contacts, interactions, jobs, and opportunities "
        "linked to a named company."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def search_company_context(
    company_name: str,
    ctx: Context,
    candidate_limit: int = 10,
    contact_limit: int = 10,
    interaction_limit: int = 10,
    job_limit: int = 10,
    opportunity_limit: int = 10,
) -> dict[str, Any]:
    arguments = {
        "company_name": company_name,
        "candidate_limit": candidate_limit,
        "contact_limit": contact_limit,
        "interaction_limit": interaction_limit,
        "job_limit": job_limit,
        "opportunity_limit": opportunity_limit,
    }
    request = OperatorCompanyContextRequest.model_validate(arguments)
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="search_company_context",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.search_company_context(
            **request.model_dump()
        ),
    )


@mcp_server.tool(
    title="List company directory",
    description=(
        "List a bounded alphabetical company directory, optionally filtered by a "
        "case-insensitive name fragment."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_company_directory(
    ctx: Context,
    prefix: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    arguments = {"prefix": prefix, "limit": limit}
    normalized_limit = max(1, min(int(limit), 500))
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="list_company_directory",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.list_company_directory(
            prefix=prefix,
            limit=normalized_limit,
        ),
    )


@mcp_server.tool(
    title="Discover company leads for a candidate",
    description=(
        "Return read-only outreach context connecting one candidate to contacts, "
        "interactions, jobs, and opportunities at a target company."
    ),
    annotations=_READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def discover_company_leads_for_candidate(
    candidate_id: str,
    company_name: str,
    ctx: Context,
    limit: int = 10,
) -> dict[str, Any]:
    arguments = {
        "candidate_id": candidate_id,
        "company_name": company_name,
        "limit": limit,
    }
    request = OperatorCompanyLeadDiscoveryRequest.model_validate(arguments)
    return await _execute_read_tool(
        ctx=ctx,
        tool_name="discover_company_leads_for_candidate",
        arguments=arguments,
        operation=lambda: mcp_read_adapter.discover_company_leads_for_candidate(
            **request.model_dump()
        ),
    )


async def _execute_read_tool(
    *,
    ctx: Context,
    tool_name: str,
    arguments: dict[str, Any],
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started_at = perf_counter()
    request = ctx.request_context.request
    state = getattr(request, "state", None)
    principal_hash = getattr(state, "mcp_principal_hash", None)
    transport_request_id = getattr(state, "mcp_transport_request_id", None)
    request_id = transport_request_id or ctx.request_id
    client_info = getattr(ctx.session, "client_params", None)
    client_name = getattr(client_info, "name", None)
    client_version = getattr(client_info, "version", None)
    metadata = build_mcp_argument_metadata(arguments)

    try:
        result = await run_in_threadpool(operation)
    except ValidationError as exc:
        await _audit_tool_event(
            principal_hash=principal_hash,
            request_id=request_id,
            tool_name=tool_name,
            outcome="rejected",
            duration_ms=_duration_ms(started_at),
            error_code="validation_error",
            client_name=client_name,
            client_version=client_version,
            metadata=metadata,
        )
        raise ToolError("The supplied tool arguments are invalid.") from exc
    except McpReadAdapterError as exc:
        await _audit_tool_event(
            principal_hash=principal_hash,
            request_id=request_id,
            tool_name=tool_name,
            outcome="error",
            duration_ms=_duration_ms(started_at),
            error_code=exc.code,
            client_name=client_name,
            client_version=client_version,
            metadata=metadata,
        )
        raise ToolError(exc.message) from exc
    except ToolError:
        raise
    except Exception as exc:
        await _audit_tool_event(
            principal_hash=principal_hash,
            request_id=request_id,
            tool_name=tool_name,
            outcome="error",
            duration_ms=_duration_ms(started_at),
            error_code="internal_error",
            client_name=client_name,
            client_version=client_version,
            metadata=metadata,
        )
        raise ToolError("The read-only recruiter tool could not complete.") from exc

    await _audit_tool_event(
        principal_hash=principal_hash,
        request_id=request_id,
        tool_name=tool_name,
        outcome="success",
        duration_ms=_duration_ms(started_at),
        error_code=None,
        client_name=client_name,
        client_version=client_version,
        metadata=metadata,
    )
    return result


async def _audit_tool_event(**event: Any) -> None:
    await run_in_threadpool(
        audit_mcp_event_best_effort,
        event_type="tool_call",
        **event,
    )


def _duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


__all__ = ["mcp_server"]
