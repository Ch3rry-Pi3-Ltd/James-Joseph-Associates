"""Read-only query-plan diagnostics; emits plan timings, never result records."""

import argparse
from contextlib import contextmanager
import json
from unittest.mock import patch

from backend.db import candidates as candidate_db
from backend.db.connection import get_postgres_connection


def _capture_search_sql(*, company: bool, query: str, resume_only: bool):
    captured: dict[str, object] = {}

    class CaptureCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, sql, params):
            captured["query"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    class CaptureConnection:
        def cursor(self):
            return CaptureCursor()

    @contextmanager
    def capture_connection():
        yield CaptureConnection()

    with patch.object(candidate_db, "postgres_connection", capture_connection):
        if company:
            candidate_db.search_candidates_by_company_name(
                company_name=query,
                limit=15,
            )
        else:
            candidate_db.search_candidates_by_resume_text(
                query=query,
                limit=15,
                include_cross_field_matches=not resume_only,
            )

    return str(captured["query"]), dict(captured["params"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", action="store_true")
    parser.add_argument(
        "--resume-only",
        action="store_true",
        help="Profile only the indexed current-CV branch.",
    )
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--query")
    args = parser.parse_args()
    company = args.company
    search_term = args.query or (
        "Pirum" if company else "sftr securities lending repo repurchase agreements"
    )
    query, params = _capture_search_sql(
        company=company,
        query=search_term,
        resume_only=args.resume_only,
    )
    with get_postgres_connection() as db:
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL statement_timeout = '25000ms'")
        prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " if args.analyze else "EXPLAIN (FORMAT JSON) "
        plan = db.execute(prefix + query, params).fetchone()["QUERY PLAN"][0]
        def summarize(node):
            keys = ["Node Type", "Relation Name", "Index Name", "Plan Rows", "Actual Rows",
                    "Actual Total Time", "Actual Loops", "Shared Hit Blocks", "Shared Read Blocks"]
            return {**{k:node[k] for k in keys if k in node},
                    "children": [summarize(child) for child in node.get("Plans", [])]}
        print(json.dumps({"execution_ms": plan.get("Execution Time"), "jit": plan.get("JIT"), "plan": summarize(plan["Plan"])}))


if __name__ == "__main__":
    main()
