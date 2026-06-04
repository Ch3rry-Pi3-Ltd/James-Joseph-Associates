"""
Repair suspicious Dropbox-derived candidate names from their source filenames.

This script is intentionally narrow:

- target only canonical candidates sourced from direct Dropbox CV ingestion
- repair obvious bad filename-derived names in `people`
- leave unresolved rows in an artifact for later inspection

It does not delete rows by default.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from backend.db.connection import postgres_connection
from backend.services.dropbox_resume_extraction import (
    DROPBOX_FILENAME_NOISE_TOKENS,
    derive_dropbox_candidate_name_parts,
)

DEFAULT_ARTIFACT_PATH = Path("temp/dropbox_candidate_name_repair.json")


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the Dropbox-name repair script.
    """

    parser = argparse.ArgumentParser(
        description="Repair suspicious Dropbox-derived candidate names from their source filenames."
    )
    parser.add_argument(
        "--artifact-path",
        default=str(DEFAULT_ARTIFACT_PATH),
        help="Where to write the repair summary JSON artifact.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of suspicious Dropbox candidates to inspect.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the name repairs instead of running in report-only mode.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Find and optionally repair suspicious Dropbox candidate names.
    """

    args = parse_args()
    artifact_path = Path(str(args.artifact_path))
    limit = max(0, int(args.limit))
    apply_changes = bool(args.apply)
    rows = _fetch_dropbox_candidate_rows(limit=limit)

    updated_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    if apply_changes:
        with postgres_connection() as connection:
            with connection.cursor() as cursor:
                for row in rows:
                    classification = _classify_dropbox_candidate_row(row)
                    if classification["action"] == "update":
                        _update_person_name(
                            cursor,
                            person_id=row["person_id"],
                            full_name=classification["replacement_full_name"],
                            first_name=classification["replacement_first_name"],
                            last_name=classification["replacement_last_name"],
                        )
                        updated_rows.append(classification)
                    elif classification["action"] == "unresolved":
                        unresolved_rows.append(classification)
                    else:
                        skipped_rows.append(classification)
            connection.commit()
    else:
        for row in rows:
            classification = _classify_dropbox_candidate_row(row)
            if classification["action"] == "update":
                updated_rows.append(classification)
            elif classification["action"] == "unresolved":
                unresolved_rows.append(classification)
            else:
                skipped_rows.append(classification)

    summary = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "apply": apply_changes,
        "inspected_count": len(rows),
        "updated_count": len(updated_rows),
        "skipped_count": len(skipped_rows),
        "unresolved_count": len(unresolved_rows),
        "updated_preview": updated_rows[:50],
        "unresolved_preview": unresolved_rows[:50],
        "skipped_preview": skipped_rows[:20],
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"artifact: {artifact_path}")
    print(f"apply: {apply_changes}")
    print(f"inspected Dropbox candidates: {summary['inspected_count']}")
    print(f"updated candidates: {summary['updated_count']}")
    print(f"skipped candidates: {summary['skipped_count']}")
    print(f"unresolved candidates: {summary['unresolved_count']}")


def _fetch_dropbox_candidate_rows(*, limit: int) -> list[dict[str, Any]]:
    """
    Return Dropbox-derived candidates whose current names still look suspicious.
    """

    limit_clause = ""
    params: dict[str, Any] = {}
    if limit > 0:
        limit_clause = "limit %(limit)s"
        params["limit"] = limit

    query = f"""
        with dropbox_candidates as (
            select distinct on (c.id)
                c.id as candidate_id,
                p.id as person_id,
                p.full_name,
                p.first_name,
                p.last_name,
                c.candidate_status,
                sr.source_record_id as dropbox_path,
                sr.source_payload -> 'candidate_context' ->> 'source_file_name' as source_file_name,
                sr.source_payload -> 'candidate_context' ->> 'source_path' as source_path
            from source_records sr
            join source_record_links srl
              on srl.source_record_id = sr.id
             and srl.candidate_id is not null
            join candidates c
              on c.id = srl.candidate_id
            join people p
              on p.id = c.person_id
            where sr.source_system = 'dropbox'
              and sr.source_record_type = 'dropbox_candidate_file'
              and c.candidate_status = 'Dropbox archive CV'
            order by c.id, sr.created_at desc
        )
        select *
        from dropbox_candidates
        where lower(coalesce(full_name, '')) ~ '(totaljobs|cv.?library|jobsite|reed|monster|resume|updated|latest|\\mjs\\M)'
           or coalesce(full_name, '') ~ '[0-9]'
           or coalesce(full_name, '') ~ '[a-z][A-Z]'
           or full_name = 'Unknown Candidate'
        order by full_name asc
        {limit_clause}
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def _classify_dropbox_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Decide whether one Dropbox candidate row should be updated, skipped, or flagged.
    """

    source_file_name = _clean_string(row.get("source_file_name"))
    if source_file_name is None:
        source_path = _clean_string(row.get("source_path")) or _clean_string(
            row.get("dropbox_path")
        )
        source_file_name = (
            PurePosixPath(source_path).name if source_path is not None else None
        )

    file_stem = PurePosixPath(source_file_name).stem if source_file_name else ""
    replacement_first_name, replacement_last_name, replacement_full_name = (
        derive_dropbox_candidate_name_parts(file_stem)
    )

    classification = {
        "candidate_id": row["candidate_id"],
        "person_id": row["person_id"],
        "current_full_name": row.get("full_name"),
        "current_first_name": row.get("first_name"),
        "current_last_name": row.get("last_name"),
        "source_file_name": source_file_name,
        "source_path": row.get("source_path") or row.get("dropbox_path"),
        "replacement_full_name": replacement_full_name,
        "replacement_first_name": replacement_first_name,
        "replacement_last_name": replacement_last_name,
        "action": None,
        "reason": None,
    }

    if replacement_full_name is None:
        classification["action"] = "unresolved"
        classification["reason"] = "no_name_derived_from_filename"
        return classification

    if _looks_suspicious_name(replacement_full_name):
        classification["action"] = "unresolved"
        classification["reason"] = "replacement_name_still_suspicious"
        return classification

    current_full_name = _clean_string(row.get("full_name"))
    if current_full_name == replacement_full_name:
        classification["action"] = "skip"
        classification["reason"] = "already_matches_replacement"
        return classification

    classification["action"] = "update"
    classification["reason"] = "repair_suspicious_dropbox_filename_name"
    return classification


def _looks_suspicious_name(value: str | None) -> bool:
    """
    Return whether one person-name string still contains transport noise.
    """

    if value is None:
        return True
    lowered = value.casefold()
    if any(token in lowered for token in DROPBOX_FILENAME_NOISE_TOKENS):
        return True
    if re.search(r"\bjs\b", lowered):
        return True
    if re.search(r"\d", value):
        return True
    if re.search(r"[a-z][A-Z]", value):
        return True
    if value == "Unknown Candidate":
        return True
    return False


def _update_person_name(
    cursor: Any,
    *,
    person_id: str,
    full_name: str,
    first_name: str | None,
    last_name: str | None,
) -> None:
    """
    Update one canonical person name in place.
    """

    cursor.execute(
        """
        update people
        set
            full_name = %(full_name)s,
            first_name = %(first_name)s,
            last_name = %(last_name)s,
            updated_at = now()
        where id = %(person_id)s
        """,
        {
            "person_id": person_id,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
        },
    )


def _clean_string(value: Any) -> str | None:
    """
    Return a stripped string, or `None` for blank-like input.
    """

    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    return cleaned_value or None


if __name__ == "__main__":
    main()
