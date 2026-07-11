"""
Run one bounded Recruitly collection ingest against the configured API key.
"""

from __future__ import annotations

import argparse
import json

from backend.settings import get_settings
from backend.services.recruitly_ingestion import ingest_recruitly_collection_page


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist one bounded Recruitly companies/contacts page.",
    )
    parser.add_argument(
        "--resource",
        choices=("companies", "contacts"),
        required=True,
        help="Recruitly collection to ingest.",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="Zero-based Recruitly page to ingest.",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=20,
        help="Maximum number of rows to ingest from the page.",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Optional Recruitly search query.",
    )
    parser.add_argument(
        "--import-run-id",
        default=None,
        help="Optional operator-supplied import run identifier.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    report = ingest_recruitly_collection_page(
        resource=args.resource,
        api_base_url=settings.recruitly_base_url,
        api_key=settings.recruitly_api_key,
        query=args.query,
        page=args.page,
        size=args.size,
        import_run_id=args.import_run_id,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
