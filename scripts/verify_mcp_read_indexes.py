"""Verify MCP read-path indexes and report privacy-safe query-plan metrics."""

from __future__ import annotations

import json
from typing import Any

from backend.db.connection import postgres_connection


EXPECTED_INDEXES = {
    "idx_person_company_roles_person_recency",
    "idx_source_record_links_candidate_id",
    "idx_source_record_links_person_id",
}


def _plan_summary(plan_document: list[dict[str, Any]]) -> dict[str, Any]:
    document = plan_document[0]
    root = document["Plan"]
    node_types: list[str] = []
    index_names: list[str] = []

    def visit(node: dict[str, Any]) -> None:
        node_types.append(str(node.get("Node Type") or "unknown"))
        if node.get("Index Name"):
            index_names.append(str(node["Index Name"]))
        for child in node.get("Plans") or []:
            visit(child)

    visit(root)
    return {
        "execution_time_ms": document.get("Execution Time"),
        "shared_hit_blocks": root.get("Shared Hit Blocks", 0),
        "shared_read_blocks": root.get("Shared Read Blocks", 0),
        "node_types": node_types,
        "index_names": index_names,
    }


def main() -> int:
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = ANY(%s)
                ORDER BY indexname
                """,
                (list(EXPECTED_INDEXES),),
            )
            indexes = {str(row["indexname"]) for row in cursor.fetchall()}
            if indexes != EXPECTED_INDEXES:
                missing = sorted(EXPECTED_INDEXES - indexes)
                raise RuntimeError(f"Expected MCP indexes are missing: {missing}")

            cursor.execute(
                "SELECT candidate_id FROM source_record_links "
                "WHERE candidate_id IS NOT NULL LIMIT 1"
            )
            candidate_id = cursor.fetchone()["candidate_id"]
            cursor.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                "SELECT 1 FROM source_record_links "
                "WHERE candidate_id = %s LIMIT 3",
                (candidate_id,),
            )
            candidate_plan = _plan_summary(cursor.fetchone()["QUERY PLAN"])

            cursor.execute(
                "SELECT person_id FROM source_record_links "
                "WHERE person_id IS NOT NULL LIMIT 1"
            )
            person_id = cursor.fetchone()["person_id"]
            cursor.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                "SELECT 1 FROM source_record_links "
                "WHERE person_id = %s LIMIT 3",
                (person_id,),
            )
            person_plan = _plan_summary(cursor.fetchone()["QUERY PLAN"])

            cursor.execute("SELECT person_id FROM person_company_roles LIMIT 1")
            employment_person_id = cursor.fetchone()["person_id"]
            cursor.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                "SELECT 1 FROM person_company_roles "
                "WHERE person_id = %s "
                "ORDER BY is_current DESC, end_date DESC NULLS LAST, "
                "start_date DESC NULLS LAST LIMIT 5",
                (employment_person_id,),
            )
            employment_plan = _plan_summary(cursor.fetchone()["QUERY PLAN"])

    print(
        json.dumps(
            {
                "verified_indexes": sorted(indexes),
                "plans": {
                    "candidate_provenance": candidate_plan,
                    "person_provenance": person_plan,
                    "recent_employment": employment_plan,
                },
                "writes_performed": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
