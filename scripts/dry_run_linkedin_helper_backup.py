"""Run read-only Linked Helper backup reconciliation against canonical people."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db.linkedin_helper_reconciliation import (
    load_canonical_companies_for_linkedin_helper,
    load_canonical_people_for_linkedin_helper,
)
from backend.services.dropbox_api import download_dropbox_file
from backend.services.linkedin_helper_backup import (
    map_linkedin_helper_backup_companies,
    map_linkedin_helper_backup_people,
)
from backend.services.linkedin_helper_reconciliation import (
    build_canonical_company_identity_index,
    build_canonical_identity_index,
    reconcile_linkedin_helper_companies,
    reconcile_linkedin_helper_people,
)
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)

DEFAULT_BACKUP_PATH = (
    "/%%% - Linked Helper Backups for Roger/"
    "lh-tom_owens-#35783-backup-2026-07-10t12_06_59_798z.lhd2"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Map and reconcile a bounded Linked Helper backup slice without "
            "writing canonical data."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Required safety flag. This command never writes canonical data.",
    )
    parser.add_argument(
        "--dropbox-path",
        default=DEFAULT_BACKUP_PATH,
        help="Dropbox path to the latest Linked Helper .lhd2 backup.",
    )
    parser.add_argument(
        "--entity",
        choices=("people", "companies", "both"),
        default="people",
        help="Backup entity to reconcile. Defaults to people.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum people to map. Defaults to a bounded 100-record sample.",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--review-artifact",
        help=(
            "Optional local JSON path for identifiable review rows. Prefer a "
            "gitignored temp path and handle it as confidential data."
        ),
    )
    return parser


def run_dry_run(
    *,
    content_bytes: bytes,
    limit: int,
    offset: int,
    canonical_snapshot: dict[str, Any],
    import_run_id: str,
) -> dict[str, Any]:
    payloads = map_linkedin_helper_backup_people(
        content_bytes,
        limit=limit,
        offset=offset,
        include_profile_details=False,
        import_run_id=import_run_id,
    )
    canonical_index = build_canonical_identity_index(
        people=canonical_snapshot["people"],
        source_links=canonical_snapshot["source_links"],
    )
    return reconcile_linkedin_helper_people(
        payloads=payloads,
        canonical_index=canonical_index,
    )


def run_company_dry_run(
    *,
    content_bytes: bytes,
    limit: int,
    offset: int,
    canonical_snapshot: dict[str, Any],
    import_run_id: str,
) -> dict[str, Any]:
    payloads = map_linkedin_helper_backup_companies(
        content_bytes,
        limit=limit,
        offset=offset,
        import_run_id=import_run_id,
    )
    canonical_index = build_canonical_company_identity_index(
        companies=canonical_snapshot["companies"],
        source_links=canonical_snapshot["source_links"],
    )
    return reconcile_linkedin_helper_companies(
        payloads=payloads,
        canonical_index=canonical_index,
    )


def write_review_artifact(path: str, report: dict[str, Any]) -> Path:
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(
            {
                "warning": "Confidential identity reconciliation review data.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "results": report["results"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(artifact_path, 0o600)
    except OSError:
        pass
    return artifact_path


def main() -> None:
    args = build_parser().parse_args()
    if not args.dry_run:
        raise SystemExit("--dry-run is required. This command does not support writes.")
    if args.limit <= 0:
        raise SystemExit("--limit must be greater than zero.")
    if args.offset < 0:
        raise SystemExit("--offset must be zero or greater.")

    import_run_id = (
        "linkedin_helper_lhd2_dry_run:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    downloaded_file = download_dropbox_file(
        access_token=str(stored_connection["access_token"]),
        path=args.dropbox_path,
        timeout_seconds=120,
    )
    reports: dict[str, dict[str, Any]] = {}
    if args.entity in {"people", "both"}:
        reports["people"] = run_dry_run(
            content_bytes=downloaded_file["content_bytes"],
            limit=args.limit,
            offset=args.offset,
            canonical_snapshot=load_canonical_people_for_linkedin_helper(),
            import_run_id=import_run_id,
        )
    if args.entity in {"companies", "both"}:
        reports["companies"] = run_company_dry_run(
            content_bytes=downloaded_file["content_bytes"],
            limit=args.limit,
            offset=args.offset,
            canonical_snapshot=load_canonical_companies_for_linkedin_helper(),
            import_run_id=import_run_id,
        )

    summary = {
        "mode": "dry_run",
        "canonical_writes": 0,
        "entity": args.entity,
        "dropbox_path": args.dropbox_path,
        "downloaded_mib": round(
            len(downloaded_file["content_bytes"]) / 1_048_576,
            2,
        ),
        "offset": args.offset,
        "limit": args.limit,
    }
    if len(reports) == 1:
        report = next(iter(reports.values()))
        summary.update(_report_summary(report))
    else:
        summary["reports"] = {
            entity_name: _report_summary(report)
            for entity_name, report in reports.items()
        }
    if args.review_artifact:
        review_report = (
            next(iter(reports.values()))
            if len(reports) == 1
            else {
                "results": [
                    {"entity": entity_name, **result}
                    for entity_name, entity_report in reports.items()
                    for result in entity_report["results"]
                ]
            }
        )
        artifact_path = write_review_artifact(args.review_artifact, review_report)
        summary["review_artifact"] = str(artifact_path)
    print(json.dumps(summary, indent=2))


def _report_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "total": report["total"],
        "matched": report["matched"],
        "new": report["new"],
        "ambiguous": report["ambiguous"],
        "skipped": report["skipped"],
        "match_methods": report["match_methods"],
    }


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
