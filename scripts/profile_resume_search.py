"""Read-only query-plan diagnostics; emits plan timings, never result records."""

import ast
import argparse
import inspect
import json

from backend.db.candidates import search_candidates_by_resume_text, search_candidates_by_company_name
from backend.db.connection import get_postgres_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--query")
    args = parser.parse_args()
    company = args.company
    function = search_candidates_by_company_name if company else search_candidates_by_resume_text
    tree = ast.parse(inspect.getsource(function))
    query = next(node.value.value for node in ast.walk(tree)
                 if isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == "search_sql"
                     for target in node.targets))
    params = {"company_name": args.query or "Pirum", "limit": 15} if company else {
        "query": args.query or "sftr securities lending repo repurchase agreements", "limit": 15,
    }
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
