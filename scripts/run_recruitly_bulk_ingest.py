"""
Run a bulk Recruitly ingest sweep against the configured API key.

This operator script exists because the protected API routes and tiny helper
scripts are intentionally one-page-at-a-time. For the next workflow slice we
need a deterministic way to sweep Recruitly collections in canonical order and,
optionally, pull journal evidence for the imported records.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.settings import get_settings
from backend.services.recruitly_api import (
    fetch_recruitly_companies_preview,
    fetch_recruitly_contacts_preview,
    fetch_recruitly_jobs_preview,
    fetch_recruitly_opportunities_preview,
)
from backend.services.recruitly_ingestion import (
    ingest_recruitly_company,
    ingest_recruitly_contact,
    ingest_recruitly_job,
    ingest_recruitly_opportunity,
    ingest_recruitly_record_journal,
)

ResourceName = str

RESOURCE_ORDER: tuple[ResourceName, ...] = (
    "companies",
    "contacts",
    "jobs",
    "opportunities",
)

JOURNAL_RECORD_TYPE_BY_RESOURCE: dict[str, str] = {
    "companies": "company",
    "contacts": "contact",
    "jobs": "job",
    "opportunities": "opportunity",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep Recruitly collections into canonical storage and optionally "
            "ingest journal entries for the imported records."
        ),
    )
    parser.add_argument(
        "--resource",
        action="append",
        choices=RESOURCE_ORDER,
        dest="resources",
        help=(
            "Recruitly collection to ingest. Repeat for multiple collections. "
            "Defaults to companies, contacts, jobs, opportunities."
        ),
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Optional Recruitly search query applied to every collection sweep.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Maximum rows to request per Recruitly collection page.",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=0,
        help="Zero-based collection page to start from.",
    )
    parser.add_argument(
        "--max-pages-per-resource",
        type=int,
        default=1000,
        help="Hard stop per collection to avoid accidental infinite loops.",
    )
    parser.add_argument(
        "--include-journals",
        action="store_true",
        help="Also ingest Recruitly journal entries for imported records.",
    )
    parser.add_argument(
        "--journal-page-size",
        type=int,
        default=100,
        help="Maximum journal rows to request per Recruitly journal page.",
    )
    parser.add_argument(
        "--max-journal-pages-per-record",
        type=int,
        default=100,
        help="Hard stop per record journal sweep.",
    )
    parser.add_argument(
        "--journal-resource",
        action="append",
        choices=RESOURCE_ORDER,
        dest="journal_resources",
        help=(
            "Resource families whose journals should be ingested. Repeat for "
            "multiple families. Defaults to contacts, jobs, opportunities."
        ),
    )
    parser.add_argument(
        "--max-journal-records-per-resource",
        type=int,
        default=None,
        help="Optional cap on how many imported records per resource get journal sweeps.",
    )
    parser.add_argument(
        "--import-run-id",
        default=None,
        help="Optional operator-supplied import run identifier prefix.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the aggregate JSON report.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()

    resources = tuple(args.resources or RESOURCE_ORDER)
    journal_resources = tuple(
        args.journal_resources or ("contacts", "jobs", "opportunities")
    )
    run_started_at = datetime.now(timezone.utc)
    import_run_prefix = args.import_run_id or run_started_at.strftime(
        "recruitly-bulk-%Y%m%dT%H%M%SZ"
    )

    collection_summaries: list[dict[str, Any]] = []
    imported_record_ids_by_resource: dict[str, list[str]] = {
        resource: [] for resource in resources
    }

    for resource in resources:
        resource_summary = _ingest_resource_pages(
            resource=resource,
            api_base_url=settings.recruitly_base_url,
            api_key=settings.recruitly_api_key,
            query=args.query,
            page_size=max(1, min(int(args.page_size), 100)),
            start_page=max(0, int(args.start_page)),
            max_pages=max(1, int(args.max_pages_per_resource)),
            import_run_prefix=import_run_prefix,
        )
        collection_summaries.append(resource_summary)
        imported_record_ids_by_resource[resource] = resource_summary["imported_record_ids"]

    journal_summaries: list[dict[str, Any]] = []
    if args.include_journals:
        for resource in journal_resources:
            if resource not in imported_record_ids_by_resource:
                continue
            record_ids = imported_record_ids_by_resource[resource]
            if args.max_journal_records_per_resource is not None:
                record_ids = record_ids[: max(1, int(args.max_journal_records_per_resource))]
            journal_summaries.append(
                _ingest_resource_journals(
                    resource=resource,
                    record_ids=record_ids,
                    api_base_url=settings.recruitly_base_url,
                    api_key=settings.recruitly_api_key,
                    journal_page_size=max(1, min(int(args.journal_page_size), 100)),
                    max_pages=max(1, int(args.max_journal_pages_per_record)),
                    import_run_prefix=import_run_prefix,
                )
            )

    summary = {
        "started_at": run_started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "resources": list(resources),
        "query": args.query,
        "page_size": max(1, min(int(args.page_size), 100)),
        "include_journals": bool(args.include_journals),
        "journal_resources": list(journal_resources) if args.include_journals else [],
        "import_run_prefix": import_run_prefix,
        "collection_summaries": collection_summaries,
        "journal_summaries": journal_summaries,
        "total_rows_persisted": sum(
            int(item["persisted_rows"]) for item in collection_summaries
        ),
        "total_journal_interactions_persisted": sum(
            int(item["interactions_persisted"]) for item in journal_summaries
        ),
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"aggregate artifact: {args.output_json}")

    print(json.dumps(summary, indent=2, default=str))


def _ingest_resource_pages(
    *,
    resource: str,
    api_base_url: str,
    api_key: str,
    query: str | None,
    page_size: int,
    start_page: int,
    max_pages: int,
    import_run_prefix: str,
) -> dict[str, Any]:
    fetch_preview = _get_preview_fetcher(resource)
    ingest_row = _get_row_ingester(resource)

    pages: list[dict[str, Any]] = []
    imported_record_ids: list[str] = []
    persisted_rows = 0

    current_page = start_page
    for page_index in range(max_pages):
        preview = fetch_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=current_page,
            size=page_size,
        )
        rows = list(preview.get("data") or [])
        page_import_run_id = f"{import_run_prefix}:{resource}:page:{current_page}"

        persisted: list[dict[str, Any]] = []
        page_record_ids: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            record_id = _extract_recruitly_record_id(row)
            if record_id is not None:
                page_record_ids.append(record_id)
                imported_record_ids.append(record_id)
            persisted.append(
                ingest_row(
                    row,
                    import_run_id=page_import_run_id,
                )
            )

        pages.append(
            {
                "page": current_page,
                "item_count": int(preview["item_count"]),
                "total_count": preview["total_count"],
                "persisted_count": len(persisted),
                "record_ids": page_record_ids,
            }
        )
        persisted_rows += len(persisted)

        if _should_stop_paging(
            item_count=int(preview["item_count"]),
            total_count=preview["total_count"],
            page=current_page,
            size=page_size,
        ):
            break

        current_page += 1
        if page_index + 1 >= max_pages:
            break

    return {
        "resource": resource,
        "query": query,
        "start_page": start_page,
        "pages_requested": len(pages),
        "persisted_rows": persisted_rows,
        "imported_record_ids": imported_record_ids,
        "pages": pages,
    }


def _ingest_resource_journals(
    *,
    resource: str,
    record_ids: list[str],
    api_base_url: str,
    api_key: str,
    journal_page_size: int,
    max_pages: int,
    import_run_prefix: str,
) -> dict[str, Any]:
    record_type = JOURNAL_RECORD_TYPE_BY_RESOURCE[resource]
    record_summaries: list[dict[str, Any]] = []
    interactions_persisted = 0

    for record_id in record_ids:
        pages: list[dict[str, Any]] = []
        for page in range(max_pages):
            report = ingest_recruitly_record_journal(
                api_base_url=api_base_url,
                api_key=api_key,
                record_type=record_type,
                record_id=record_id,
                page=page,
                size=journal_page_size,
                import_run_id=(
                    f"{import_run_prefix}:journal:{record_type}:{record_id}:page:{page}"
                ),
            )
            page_interactions = int(report["interaction_count"])
            interactions_persisted += page_interactions
            pages.append(
                {
                    "page": page,
                    "item_count": int(report["item_count"]),
                    "total_count": report["total_count"],
                    "interaction_count": page_interactions,
                }
            )

            if _should_stop_paging(
                item_count=int(report["item_count"]),
                total_count=report["total_count"],
                page=page,
                size=journal_page_size,
            ):
                break

        record_summaries.append(
            {
                "record_id": record_id,
                "pages_requested": len(pages),
                "pages": pages,
            }
        )

    return {
        "resource": resource,
        "record_type": record_type,
        "records_requested": len(record_ids),
        "interactions_persisted": interactions_persisted,
        "records": record_summaries,
    }


def _get_preview_fetcher(resource: str) -> Any:
    if resource == "companies":
        return fetch_recruitly_companies_preview
    if resource == "contacts":
        return fetch_recruitly_contacts_preview
    if resource == "jobs":
        return fetch_recruitly_jobs_preview
    if resource == "opportunities":
        return fetch_recruitly_opportunities_preview
    raise ValueError(f"Unsupported Recruitly resource: {resource}")


def _get_row_ingester(resource: str) -> Any:
    if resource == "companies":
        return ingest_recruitly_company
    if resource == "contacts":
        return ingest_recruitly_contact
    if resource == "jobs":
        return ingest_recruitly_job
    if resource == "opportunities":
        return ingest_recruitly_opportunity
    raise ValueError(f"Unsupported Recruitly resource: {resource}")


def _extract_recruitly_record_id(payload: dict[str, Any]) -> str | None:
    raw_value = payload.get("id")
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        return normalized or None
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _should_stop_paging(
    *,
    item_count: int,
    total_count: int | None,
    page: int,
    size: int,
) -> bool:
    if item_count == 0:
        return True

    if item_count < size:
        return True

    if total_count is not None and (page + 1) * size >= total_count:
        return True

    return False


if __name__ == "__main__":
    main()
