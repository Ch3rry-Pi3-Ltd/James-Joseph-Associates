"""Read-only regression benchmark; prints counts/timings, never candidate content."""

import argparse
import json
from time import perf_counter

import httpx

from backend.settings import get_settings
from scripts.smoke_mcp_endpoint import _post_rpc

ROLE_BRIEF = (
    "Find candidates with securities lending, stock lending, repo, repurchase "
    "agreements or SFTR experience. Pirum and EquiLend are desirable, not mandatory."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="Omit to exercise local code against configured services.")
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    cases = [
        ("securities", "search_candidates_for_role", {"role_brief": ROLE_BRIEF, "search_limit": 5}),
        ("pirum", "search_company_context", {"company_name": "Pirum", "candidate_limit": 5}),
        ("equilend", "search_company_context", {"company_name": "EquiLend", "candidate_limit": 5}),
    ]
    with httpx.Client(timeout=40) as client:
        for repetition in range(args.repetitions):
            for label, tool, arguments in cases:
                started = perf_counter()
                if args.endpoint:
                    payload, _ = _post_rpc(
                        client, endpoint=args.endpoint, token=get_settings().mcp_api_token,
                        request_id=1, method="tools/call",
                        params={"name": tool, "arguments": arguments},
                    )
                    result = payload.get("result", {})
                    if result.get("isError"):
                        raise RuntimeError(f"{label}: MCP returned a tool error")
                    result = result["structuredContent"]
                elif tool == "search_candidates_for_role":
                    from backend.services.candidate_profiles import search_candidate_resumes
                    result = search_candidate_resumes(query=ROLE_BRIEF, limit=5)
                else:
                    from backend.services.mcp_read_adapter import search_company_context
                    result = search_company_context(**arguments)
                rows = result.get("search_results", result.get("results", result.get("candidates", [])))
                if not rows or len(rows) > 5 or not all(row.get("candidate_id") for row in rows):
                    raise RuntimeError(f"{label}: missing bounded candidate evidence")
                print(json.dumps({
                    "repetition": repetition + 1, "case": label,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "candidate_count": len(rows), "candidate_data_writes": 0,
                    "retrieval_metadata": result.get("retrieval_metadata", {}),
                }), flush=True)


if __name__ == "__main__":
    main()
