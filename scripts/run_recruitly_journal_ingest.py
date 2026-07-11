"""
Run one bounded Recruitly journal ingest against the configured API key.
"""

from __future__ import annotations

import argparse
import json

from backend.settings import get_settings
from backend.services.recruitly_ingestion import ingest_recruitly_record_journal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist one bounded Recruitly journal slice.",
    )
    parser.add_argument(
        "--record-type",
        required=True,
        help="Recruitly record type such as company, contact, job, or opportunity.",
    )
    parser.add_argument(
        "--record-id",
        required=True,
        help="Recruitly record identifier whose journal should be ingested.",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="Zero-based Recruitly journal page to ingest.",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=20,
        help="Maximum number of journal rows to ingest from the page.",
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
    report = ingest_recruitly_record_journal(
        api_base_url=settings.recruitly_base_url,
        api_key=settings.recruitly_api_key,
        record_type=args.record_type,
        record_id=args.record_id,
        page=args.page,
        size=args.size,
        import_run_id=args.import_run_id,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
