"""Run restartable, audited Linked Helper backup imports in bounded batches."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from backend.db.database_usage import get_database_size_bytes
from backend.db.linkedin_helper_reconciliation import (
    load_canonical_companies_for_linkedin_helper,
    load_canonical_people_for_linkedin_helper,
    verify_linkedin_helper_import,
)
from backend.services.dropbox_api import download_dropbox_file
from backend.services.linkedin_helper_backup import (
    map_linkedin_helper_backup_companies,
    map_linkedin_helper_backup_people,
)
from backend.services.linkedin_helper_backup_import import (
    MAX_IMPORT_LIMIT,
    build_linkedin_helper_import_plan_from_mapped_payloads,
    execute_linkedin_helper_backup_import_plan_transactional,
)
from scripts.dry_run_linkedin_helper_backup import DEFAULT_BACKUP_PATH
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)

CHECKPOINT_VERSION = 1
DEFAULT_BATCH_SIZE = 20
DEFAULT_CHECKPOINT_PATH = Path(
    "temp/linkedin_helper_backup_import_checkpoint.json"
)
DEFAULT_MAX_DATABASE_SIZE_GIB = 2.5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download one Linked Helper backup once, then plan or commit "
            "restartable audited 20-profile batches."
        )
    )
    parser.add_argument("--dropbox-path", default=DEFAULT_BACKUP_PATH)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_PATH,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from the next offset in an existing checkpoint.",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Delete the selected checkpoint before starting a fresh run.",
    )
    parser.add_argument(
        "--max-database-size-gib",
        type=float,
        default=DEFAULT_MAX_DATABASE_SIZE_GIB,
        help=(
            "Stop before the next batch once allocated Postgres size reaches "
            "this threshold. Defaults to a conservative 2.5 GiB."
        ),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform writes. Without this flag every batch is read-only.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _validate_args(args)
    if args.reset_checkpoint and args.checkpoint.exists():
        args.checkpoint.unlink()
    checkpoint = _load_checkpoint(args.checkpoint) if args.resume else None
    if args.resume and checkpoint is None:
        raise SystemExit(f"Checkpoint not found: {args.checkpoint}")
    if args.commit and not args.resume and args.checkpoint.exists():
        raise SystemExit(
            f"Checkpoint already exists: {args.checkpoint}. "
            "Use --resume or --reset-checkpoint."
        )

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    downloaded_file = download_dropbox_file(
        access_token=str(stored_connection["access_token"]),
        path=args.dropbox_path,
        timeout_seconds=120,
    )
    content_bytes = downloaded_file["content_bytes"]
    backup_sha256 = hashlib.sha256(content_bytes).hexdigest()
    run_id = (
        "linkedin_helper_lhd2_batch_import:"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    all_people = map_linkedin_helper_backup_people(
        content_bytes,
        limit=None,
        offset=0,
        include_profile_details=True,
        import_run_id=run_id,
    )
    all_companies = map_linkedin_helper_backup_companies(
        content_bytes,
        limit=None,
        offset=0,
        import_run_id=run_id,
    )
    total_people = len(all_people)
    profiles_with_context = sum(
        _profile_has_context(person) for person in all_people
    )
    starting_database_size = get_database_size_bytes()
    offset, cumulative = _resolve_run_state(
        checkpoint=checkpoint,
        dropbox_path=args.dropbox_path,
        backup_sha256=backup_sha256,
        total_people=total_people,
        start_offset=args.start_offset,
    )
    database_limit_bytes = int(args.max_database_size_gib * (1024**3))
    batches_completed = 0
    stopped_for_database_size = False

    while offset < total_people and batches_completed < args.max_batches:
        end_offset = min(offset + args.batch_size, total_people)
        people_snapshot = load_canonical_people_for_linkedin_helper()
        companies_snapshot = load_canonical_companies_for_linkedin_helper()
        plan = build_linkedin_helper_import_plan_from_mapped_payloads(
            people=all_people[offset:end_offset],
            all_companies=all_companies,
            limit=args.batch_size,
            offset=offset,
            people_snapshot=people_snapshot,
            companies_snapshot=companies_snapshot,
        )
        batch_output: dict[str, Any] = {
            "mode": "commit" if args.commit else "plan",
            "offset": offset,
            "end_offset": end_offset,
            "plan": _summarize_plan(plan),
        }
        if not args.commit:
            batch_output["canonical_writes"] = 0
            print(json.dumps(batch_output), flush=True)
            offset = end_offset
            batches_completed += 1
            continue

        size_before = get_database_size_bytes()
        batch_output["database_size_before"] = _format_size(size_before)
        if size_before >= database_limit_bytes:
            batch_output["stopped"] = "database_size_limit"
            print(json.dumps(batch_output), flush=True)
            stopped_for_database_size = True
            break

        persistence = execute_linkedin_helper_backup_import_plan_transactional(plan)
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
        passed = audit["people"]["passed"] and audit["companies"]["passed"]
        if not passed:
            raise RuntimeError(
                f"Post-write provenance audit failed at offset {offset}."
            )

        size_after = get_database_size_bytes()
        persisted_summary = {
            key: persistence[key]
            for key in (
                "people_persisted",
                "companies_persisted",
                "roles_persisted",
                "skills_persisted",
                "skipped_companies",
            )
        }
        batch_output.update(
            {
                "persistence": persisted_summary,
                "audit": audit,
                "database_size_after": _format_size(size_after),
                "database_growth_mib": round(
                    (size_after - size_before) / (1024**2),
                    2,
                ),
                "passed": True,
            }
        )
        cumulative = _add_persistence_counts(cumulative, persistence)
        offset = end_offset
        batches_completed += 1
        _write_checkpoint(
            args.checkpoint,
            {
                "version": CHECKPOINT_VERSION,
                "dropbox_path": args.dropbox_path,
                "backup_sha256": backup_sha256,
                "total_people": total_people,
                "profile_context": {
                    "with_company_headline_history_or_skills": profiles_with_context,
                    "identity_only": total_people - profiles_with_context,
                },
                "batch_size": args.batch_size,
                "next_offset": offset,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "cumulative": cumulative,
                "last_batch": batch_output,
            },
        )
        print(json.dumps(batch_output), flush=True)
        if size_after >= database_limit_bytes:
            stopped_for_database_size = True
            break

    print(
        json.dumps(
            {
                "mode": "commit" if args.commit else "plan",
                "backup_mib": round(len(content_bytes) / (1024**2), 2),
                "database_size_start": _format_size(starting_database_size),
                "total_people": total_people,
                "profile_context": {
                    "with_company_headline_history_or_skills": profiles_with_context,
                    "identity_only": total_people - profiles_with_context,
                },
                "batches_completed": batches_completed,
                "next_offset": offset,
                "remaining_rows": max(total_people - offset, 0),
                "checkpoint": str(args.checkpoint) if args.commit else None,
                "cumulative": cumulative,
                "completed": offset >= total_people,
                "stopped_for_database_size": stopped_for_database_size,
            },
            indent=2,
        )
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.start_offset < 0:
        raise SystemExit("--start-offset must be zero or greater.")
    if args.batch_size <= 0 or args.batch_size > MAX_IMPORT_LIMIT:
        raise SystemExit(
            f"--batch-size must be between 1 and {MAX_IMPORT_LIMIT}."
        )
    if args.max_batches <= 0:
        raise SystemExit("--max-batches must be greater than zero.")
    if args.max_database_size_gib <= 0:
        raise SystemExit("--max-database-size-gib must be greater than zero.")
    if args.resume and args.reset_checkpoint:
        raise SystemExit("--resume and --reset-checkpoint cannot be combined.")


def _resolve_run_state(
    *,
    checkpoint: dict[str, Any] | None,
    dropbox_path: str,
    backup_sha256: str,
    total_people: int,
    start_offset: int,
) -> tuple[int, dict[str, int]]:
    if checkpoint is None:
        if start_offset > total_people:
            raise SystemExit("--start-offset exceeds the backup profile count.")
        return start_offset, _empty_cumulative_counts()
    expected = {
        "version": CHECKPOINT_VERSION,
        "dropbox_path": dropbox_path,
        "backup_sha256": backup_sha256,
        "total_people": total_people,
    }
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise SystemExit(
                f"Checkpoint {key} does not match the selected backup."
            )
    next_offset = int(checkpoint["next_offset"])
    cumulative = {
        key: int(checkpoint.get("cumulative", {}).get(key, 0))
        for key in _empty_cumulative_counts()
    }
    return next_offset, cumulative


def _empty_cumulative_counts() -> dict[str, int]:
    return {
        "people_persisted": 0,
        "companies_persisted": 0,
        "roles_persisted": 0,
        "skills_persisted": 0,
        "batches_completed": 0,
    }


def _add_persistence_counts(
    cumulative: dict[str, int],
    persistence: dict[str, Any],
) -> dict[str, int]:
    updated = dict(cumulative)
    for key in (
        "people_persisted",
        "companies_persisted",
        "roles_persisted",
        "skills_persisted",
    ):
        updated[key] += int(persistence[key])
    updated["batches_completed"] += 1
    return updated


def _load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Checkpoint is not a JSON object: {path}")
    return payload


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
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


def _format_size(size_bytes: int) -> dict[str, float | int]:
    return {
        "bytes": size_bytes,
        "gib": round(size_bytes / (1024**3), 3),
    }


def _profile_has_context(person: dict[str, Any]) -> bool:
    source_payload = person.get("source_payload", {})
    return bool(
        person.get("company_name")
        or person.get("headline")
        or source_payload.get("employment_history")
        or source_payload.get("skills")
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
