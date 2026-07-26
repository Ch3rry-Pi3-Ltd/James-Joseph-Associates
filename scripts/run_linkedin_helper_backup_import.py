"""Plan or execute one bounded native Linked Helper backup import."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from typing import Any

from backend.db.linkedin_helper_reconciliation import (
    load_canonical_companies_for_linkedin_helper,
    load_canonical_people_for_linkedin_helper,
    verify_linkedin_helper_import,
)
from backend.services.dropbox_api import download_dropbox_file
from backend.services.linkedin_helper_backup_import import (
    MAX_IMPORT_LIMIT,
    build_linkedin_helper_backup_import_plan,
    execute_linkedin_helper_backup_import_plan,
)
from scripts.dry_run_linkedin_helper_backup import DEFAULT_BACKUP_PATH
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile a bounded native Linked Helper backup slice and, only "
            "with --commit, persist safe people and their linked context."
        )
    )
    parser.add_argument("--dropbox-path", default=DEFAULT_BACKUP_PATH)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform canonical writes. Without this flag the command is read-only.",
    )
    return parser


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "offset": plan["offset"],
        "limit": plan["limit"],
        "people": {
            key: plan["people_report"][key]
            for key in ("total", "matched", "new", "ambiguous", "skipped")
        },
        "safe_people_planned": len(plan["people"]),
        "related_companies": {
            key: plan["company_report"][key]
            for key in ("total", "matched", "new", "ambiguous", "skipped")
        },
        "unresolved_role_companies": plan["unresolved_role_companies"],
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.limit <= 0 or args.limit > MAX_IMPORT_LIMIT:
        raise SystemExit(f"--limit must be between 1 and {MAX_IMPORT_LIMIT}.")
    if args.offset < 0:
        raise SystemExit("--offset must be zero or greater.")

    import_run_id = (
        "linkedin_helper_lhd2_import:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    downloaded_file = download_dropbox_file(
        access_token=str(stored_connection["access_token"]),
        path=args.dropbox_path,
        timeout_seconds=120,
    )
    plan = build_linkedin_helper_backup_import_plan(
        content_bytes=downloaded_file["content_bytes"],
        limit=args.limit,
        offset=args.offset,
        people_snapshot=load_canonical_people_for_linkedin_helper(),
        companies_snapshot=load_canonical_companies_for_linkedin_helper(),
        import_run_id=import_run_id,
    )
    output: dict[str, Any] = {
        "mode": "commit" if args.commit else "plan",
        "import_run_id": import_run_id,
        "dropbox_path": args.dropbox_path,
        "downloaded_mib": round(
            len(downloaded_file["content_bytes"]) / 1_048_576,
            2,
        ),
        "plan": summarize_plan(plan),
    }
    if not args.commit:
        output["canonical_writes"] = 0
        print(json.dumps(output, indent=2))
        return

    persistence = execute_linkedin_helper_backup_import_plan(plan)
    audit = verify_linkedin_helper_import(
        person_source_record_ids=[
            str(row["payload"]["source_record_id"]) for row in plan["people"]
        ],
        company_source_record_ids=[
            str(result["source_record_id"])
            for result in plan["company_report"]["results"]
            if result["classification"] in {"matched", "new"}
        ],
    )
    output["persistence"] = {
        key: persistence[key]
        for key in (
            "people_persisted",
            "companies_persisted",
            "roles_persisted",
            "skills_persisted",
            "skipped_companies",
        )
    }
    output["audit"] = audit
    output["passed"] = audit["people"]["passed"] and audit["companies"]["passed"]
    print(json.dumps(output, indent=2))
    if not output["passed"]:
        raise SystemExit("Post-write Linked Helper provenance audit failed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
