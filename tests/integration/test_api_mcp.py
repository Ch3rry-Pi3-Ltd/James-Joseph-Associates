from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db.mcp_operations import McpRateLimitDecision
from backend.main import app
from backend.settings import get_settings

_MCP_TOKEN = "test-mcp-token"
_MCP_HEADERS = {
    "Authorization": f"Bearer {_MCP_TOKEN}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture(scope="module")
def mcp_client() -> Iterator[TestClient]:
    previous_token = os.environ.get("MCP_API_TOKEN")
    os.environ["MCP_API_TOKEN"] = _MCP_TOKEN
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    if previous_token is None:
        os.environ.pop("MCP_API_TOKEN", None)
    else:
        os.environ["MCP_API_TOKEN"] = previous_token
    get_settings.cache_clear()


def _allowed_rate_limit() -> McpRateLimitDecision:
    return McpRateLimitDecision(
        allowed=True,
        request_count=1,
        limit=60,
        retry_after_seconds=45,
    )


def _mcp_request(
    client: TestClient,
    *,
    method: str,
    request_id: int,
    params: dict | None = None,
):
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return client.post("/mcp/", headers=_MCP_HEADERS, json=payload)


def test_remote_mcp_requires_dedicated_bearer_token(
    mcp_client: TestClient,
) -> None:
    with patch(
        "backend.services.mcp_transport.audit_mcp_event_best_effort"
    ):
        response = mcp_client.post(
            "/mcp/",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            },
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"


def test_remote_mcp_fails_closed_when_credential_is_unconfigured(
    mcp_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCP_API_TOKEN", "")
    get_settings.cache_clear()
    with patch(
        "backend.services.mcp_transport.audit_mcp_event_best_effort"
    ):
        response = _mcp_request(
            mcp_client,
            method="tools/list",
            request_id=2,
        )
    monkeypatch.setenv("MCP_API_TOKEN", _MCP_TOKEN)
    get_settings.cache_clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_remote_mcp_initialize_and_tool_discovery_are_read_only(
    mcp_client: TestClient,
) -> None:
    with (
        patch(
            "backend.services.mcp_transport.enforce_mcp_rate_limit",
            return_value=_allowed_rate_limit(),
        ),
        patch(
            "backend.services.mcp_transport.audit_mcp_event_best_effort"
        ),
    ):
        initialize_response = _mcp_request(
            mcp_client,
            method="initialize",
            request_id=3,
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "integration-test-client",
                    "version": "1.0",
                },
            },
        )
        tools_response = _mcp_request(
            mcp_client,
            method="tools/list",
            request_id=4,
            params={},
        )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["serverInfo"]["name"] == (
        "James Joseph Associates Recruitment Intelligence"
    )
    assert tools_response.status_code == 200

    tools = tools_response.json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "discover_company_leads_for_candidate",
        "get_candidate_current_resume",
        "get_candidate_profile",
        "list_company_directory",
        "search_candidates_for_role",
        "search_company_context",
    }
    assert all(
        tool["annotations"]
        == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        for tool in tools
    )


def test_remote_mcp_executes_bounded_candidate_search(
    mcp_client: TestClient,
) -> None:
    service_result = {
        "role_brief": "Rust quantitative developer",
        "retrieval_query": "Rust quantitative developer",
        "detected_target_company": None,
        "candidate_pool_size": 1,
        "search_limit": 5,
        "candidate_pool_limit": 25,
        "shortlist_limit": 5,
        "search_results": [
            {
                "candidate_id": "candidate-1",
                "full_name": "Example Candidate",
            }
        ],
        "shortlist_results": [],
    }

    with (
        patch(
            "backend.services.mcp_transport.enforce_mcp_rate_limit",
            return_value=_allowed_rate_limit(),
        ),
        patch(
            "backend.services.mcp_transport.audit_mcp_event_best_effort"
        ),
        patch(
            "backend.services.mcp_server.audit_mcp_event_best_effort"
        ) as mock_audit,
        patch(
            "backend.services.mcp_server.mcp_read_adapter."
            "search_candidates_for_role",
            return_value=service_result,
        ) as mock_search,
    ):
        response = _mcp_request(
            mcp_client,
            method="tools/call",
            request_id=5,
            params={
                "name": "search_candidates_for_role",
                "arguments": {
                    "role_brief": "Rust quantitative developer",
                    "search_limit": 5,
                    "include_shortlist": False,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"] == service_result
    mock_search.assert_called_once_with(
        role_brief="Rust quantitative developer",
        search_limit=5,
        candidate_pool_limit=25,
        shortlist_limit=5,
        include_shortlist=False,
    )
    audit_event = mock_audit.call_args.kwargs
    assert audit_event["outcome"] == "success"
    assert audit_event["tool_name"] == "search_candidates_for_role"
    assert audit_event["metadata"]["argument_fields"] == [
        "candidate_pool_limit",
        "include_shortlist",
        "role_brief",
        "search_limit",
        "shortlist_limit",
    ]
    assert "Rust quantitative developer" not in str(audit_event["metadata"])


def test_remote_mcp_returns_429_when_shared_limit_is_exhausted(
    mcp_client: TestClient,
) -> None:
    decision = McpRateLimitDecision(
        allowed=False,
        request_count=60,
        limit=60,
        retry_after_seconds=23,
    )
    with (
        patch(
            "backend.services.mcp_transport.enforce_mcp_rate_limit",
            return_value=decision,
        ),
        patch(
            "backend.services.mcp_transport.audit_mcp_event_best_effort"
        ),
    ):
        response = _mcp_request(
            mcp_client,
            method="tools/list",
            request_id=6,
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "23"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
