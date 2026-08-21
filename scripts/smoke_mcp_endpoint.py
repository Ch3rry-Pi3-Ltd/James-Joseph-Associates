"""Run an authenticated, read-only smoke test against a deployed MCP endpoint."""

from __future__ import annotations

import argparse
import json
import os
from time import perf_counter
from typing import Any

import httpx


EXPECTED_TOOLS = {
    "discover_company_leads_for_candidate",
    "get_candidate_current_resume",
    "get_candidate_profile",
    "list_company_directory",
    "search_candidates_for_role",
    "search_company_context",
}


def _post_rpc(
    client: httpx.Client,
    *,
    endpoint: str,
    token: str,
    request_id: int,
    method: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    started_at = perf_counter()
    response = client.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        },
    )
    duration_ms = round((perf_counter() - started_at) * 1000)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"MCP {method} returned an error response.")
    return payload, duration_ms


def run_smoke(*, endpoint: str, token: str, timeout_seconds: float) -> dict[str, Any]:
    """Exercise only bounded read-only MCP operations and return safe metrics."""

    with httpx.Client(timeout=timeout_seconds) as client:
        unauthorized = client.post(
            endpoint,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        if unauthorized.status_code != 401:
            raise RuntimeError("MCP endpoint did not reject an unauthenticated request.")

        initialize, initialize_ms = _post_rpc(
            client,
            endpoint=endpoint,
            token=token,
            request_id=2,
            method="initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "jja-mcp-smoke", "version": "1.0"},
            },
        )
        tools_payload, tools_ms = _post_rpc(
            client,
            endpoint=endpoint,
            token=token,
            request_id=3,
            method="tools/list",
            params={},
        )
        tools = tools_payload["result"]["tools"]
        tool_names = {str(tool["name"]) for tool in tools}
        if tool_names != EXPECTED_TOOLS:
            raise RuntimeError("Deployed MCP tool set differs from the approved surface.")
        if not all(
            tool.get("annotations")
            == {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
            for tool in tools
        ):
            raise RuntimeError("One or more deployed MCP tools are not read-only.")

        company_payload, company_ms = _post_rpc(
            client,
            endpoint=endpoint,
            token=token,
            request_id=4,
            method="tools/call",
            params={
                "name": "list_company_directory",
                "arguments": {"prefix": "A", "limit": 5},
            },
        )
        company_result = company_payload["result"]["structuredContent"]
        company_records = company_result.get("company_records") or []
        if not company_records or not all(
            str(record.get("name") or "").casefold().startswith("a")
            and record.get("company_id")
            and isinstance(record.get("quality_flags"), list)
            for record in company_records
        ):
            raise RuntimeError("Company directory contract failed its prefix/evidence check.")

        candidate_payload, candidate_ms = _post_rpc(
            client,
            endpoint=endpoint,
            token=token,
            request_id=5,
            method="tools/call",
            params={
                "name": "search_candidates_for_role",
                "arguments": {
                    "role_brief": (
                        "Senior Data Engineer with Python, SQL, ETL, cloud data "
                        "platforms, Databricks, Airflow and team leadership"
                    ),
                    "search_limit": 5,
                },
            },
        )
        candidate_result = candidate_payload["result"]["structuredContent"]
        candidates = candidate_result.get("search_results") or []
        if not candidates or len(candidates) > 5:
            raise RuntimeError("Candidate search returned an invalid bounded result count.")
        if not all(
            candidate.get("candidate_id")
            and isinstance(candidate.get("skills"), list)
            and len(candidate.get("skills") or []) <= 12
            for candidate in candidates
        ):
            raise RuntimeError("Candidate search omitted or exceeded bounded evidence.")

    return {
        "ok": True,
        "server_name_present": bool(
            initialize.get("result", {}).get("serverInfo", {}).get("name")
        ),
        "tool_count": len(tool_names),
        "company_count": len(company_records),
        "candidate_count": len(candidates),
        "retrieval_metadata": candidate_result.get("retrieval_metadata") or {},
        "duration_ms": {
            "initialize": initialize_ms,
            "tools_list": tools_ms,
            "company_directory": company_ms,
            "candidate_search": candidate_ms,
        },
        "writes_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(
            "MCP_SMOKE_ENDPOINT",
            "https://james-joseph-associates.vercel.app/mcp",
        ),
    )
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    token = os.environ.get("MCP_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("MCP_API_TOKEN is required for the deployed smoke test.")
    print(
        json.dumps(
            run_smoke(
                endpoint=args.endpoint,
                token=token,
                timeout_seconds=args.timeout_seconds,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
