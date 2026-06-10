"""
Persist a bounded Dropbox CV folder slice through the canonical resume path.

This script is the direct-Dropbox analogue of the Recruiterflow resume runner.
It intentionally stays narrow:

- list one Dropbox folder
- pick resume-like files from the first page
- skip already-persisted Dropbox paths early
- extract text
- run the same scored structured extraction path
- persist the result into the canonical resume model
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any

from backend.db.connection import postgres_connection
from backend.services.dropbox_api import (
    download_dropbox_file,
    fetch_dropbox_list_folder,
    fetch_dropbox_list_folder_continue,
)
from backend.services.dropbox_resume_extraction import (
    build_dropbox_resume_text_bundle,
    extract_dropbox_candidate_resume_profile_with_quality_gate,
)
from backend.services.resume_extraction import (
    build_resume_extraction_input_from_resume_bundle,
)
from backend.services.resume_extraction_persistence import (
    find_existing_resume_duplicate_match,
    persist_dropbox_duplicate_resume_match,
    persist_scored_resume_extraction_result,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)

DEFAULT_DROPBOX_FOLDER_PATH = "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive"
SUPPORTED_RESUME_SUFFIXES = (".pdf", ".docx", ".doc", ".rtf", ".txt")
DEFAULT_FILE_LIMIT = 20
DEFAULT_DROPBOX_LIST_LIMIT = 200
DEFAULT_RESUME_FILE_OFFSET = 0


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the bounded Dropbox-folder CV runner.
    """

    parser = argparse.ArgumentParser(
        description="Persist a bounded Dropbox CV folder slice through the canonical resume path."
    )
    parser.add_argument(
        "--folder-path",
        default=DEFAULT_DROPBOX_FOLDER_PATH,
        help="Dropbox folder path to inspect for direct CV files.",
    )
    parser.add_argument(
        "--file-limit",
        type=int,
        default=DEFAULT_FILE_LIMIT,
        help="Maximum number of resume-like files to process from the folder listing.",
    )
    parser.add_argument(
        "--dropbox-list-limit",
        type=int,
        default=DEFAULT_DROPBOX_LIST_LIMIT,
        help="Maximum number of Dropbox folder entries to request in the first page.",
    )
    parser.add_argument(
        "--resume-file-offset",
        type=int,
        default=DEFAULT_RESUME_FILE_OFFSET,
        help="Zero-based offset into the resume-like files of the folder.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Bypass the Dropbox-path skip check and reprocess already-ingested CVs.",
    )
    parser.add_argument(
        "--process-entire-folder",
        action="store_true",
        help="Walk the whole folder from the starting offset in file-limit windows.",
    )
    return parser.parse_args()


def build_artifact_path(folder_path: str, *, resume_file_offset: int) -> Path:
    """
    Return the artifact path for one Dropbox folder run.
    """

    safe_name = folder_path.strip("/").replace("/", "__").replace(" ", "_")
    if safe_name == "":
        safe_name = "dropbox_root"
    return (
        Path("temp")
        / f"dropbox_resume_{safe_name}_offset_{resume_file_offset}_persisted.json"
    )


def main() -> None:
    """
    Persist a bounded Dropbox folder slice through canonical resume extraction.
    """

    args = parse_args()
    folder_path = str(args.folder_path)
    file_limit = max(1, int(args.file_limit))
    dropbox_list_limit = max(file_limit, int(args.dropbox_list_limit))
    resume_file_offset = max(0, int(args.resume_file_offset))
    force_reprocess = bool(args.force_reprocess)
    process_entire_folder = bool(args.process_entire_folder)
    artifact_path = build_artifact_path(
        folder_path,
        resume_file_offset=resume_file_offset,
    )
    run_started_at = datetime.now(timezone.utc)

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    access_token = stored_connection["access_token"]
    assert isinstance(access_token, str)

    folder_preview, entries = _list_folder_entries(
        access_token=access_token,
        folder_path=folder_path,
        dropbox_list_limit=dropbox_list_limit,
        stop_after_resume_file_count=(
            None if process_entire_folder else resume_file_offset + file_limit
        ),
    )
    total_eligible_resume_file_count = _count_resume_entries(entries)
    selected_entries = _slice_resume_entries(
        entries,
        resume_file_offset=resume_file_offset,
        file_limit=(
            max(0, total_eligible_resume_file_count - resume_file_offset)
            if process_entire_folder
            else file_limit
        ),
    )
    window_offsets_processed = list(
        range(
            resume_file_offset,
            resume_file_offset + len(selected_entries),
            file_limit,
        )
    )

    persisted_resumes: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    file_timing_preview: list[dict[str, Any]] = []
    status_counts = {
        "selected_resume_file": len(selected_entries),
        "accepted": 0,
        "non_pass": 0,
        "unsupported": 0,
        "failed": 0,
        "skipped": 0,
    }
    timing_totals_seconds = {
        "skip_lookup_seconds": 0.0,
        "download_seconds": 0.0,
        "resume_text_extraction_seconds": 0.0,
        "structured_resume_seconds": 0.0,
        "total_file_seconds": 0.0,
    }
    processed_file_count = 0

    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    for file_index, entry in enumerate(selected_entries, start=1):
        file_started_at = perf_counter()
        dropbox_path = _clean_string(entry.get("path_display")) or _clean_string(
            entry.get("path_lower")
        )
        file_name = _clean_string(entry.get("name")) or (
            PurePosixPath(dropbox_path).name if dropbox_path is not None else None
        )
        file_timing: dict[str, Any] = {
            "file_index": file_index,
            "dropbox_path": dropbox_path,
            "file_name": file_name,
            "status": None,
            "skip_lookup_seconds": 0.0,
            "download_seconds": 0.0,
            "resume_text_extraction_seconds": 0.0,
            "structured_resume_seconds": 0.0,
        }

        try:
            if dropbox_path is None or file_name is None:
                raise RuntimeError("Dropbox folder entry did not expose a usable path.")

            if not force_reprocess:
                skip_lookup_started_at = perf_counter()
                existing_skip_record = _find_existing_dropbox_resume_skip_record(
                    dropbox_path=dropbox_path
                )
                file_timing["skip_lookup_seconds"] = round(
                    perf_counter() - skip_lookup_started_at,
                    4,
                )
                if existing_skip_record is not None:
                    status_counts["skipped"] += 1
                    file_timing["status"] = "skipped"
                    skipped_items.append(
                        {
                            "dropbox_path": dropbox_path,
                            "file_name": file_name,
                            "source_record_id": _build_dropbox_extraction_source_record_key(
                                dropbox_path=dropbox_path
                            ),
                            "document_id": existing_skip_record.get("document_id"),
                            "document_title": existing_skip_record.get("document_title"),
                            "quality_status": existing_skip_record.get("quality_status"),
                            "quality_score": existing_skip_record.get("quality_score"),
                        }
                    )
                    continue

            download_started_at = perf_counter()
            downloaded_file = download_dropbox_file(
                access_token=access_token,
                path=dropbox_path,
                timeout_seconds=240.0,
            )
            file_timing["download_seconds"] = round(
                perf_counter() - download_started_at,
                4,
            )

            content_bytes = downloaded_file["content_bytes"]
            assert isinstance(content_bytes, bytes)

            text_extraction_started_at = perf_counter()
            extracted_resume_text = extract_text_from_resume_bytes(
                content_bytes=content_bytes,
                file_name=downloaded_file.get("file_name"),
                content_type=downloaded_file.get("content_type"),
            )
            file_timing["resume_text_extraction_seconds"] = round(
                perf_counter() - text_extraction_started_at,
                4,
            )

            duplicate_resume_match: dict[str, Any] | None = None
            prepared_extraction_input: dict[str, Any] | None = None
            if not force_reprocess and isinstance(extracted_resume_text, dict):
                prepared_resume_bundle = build_dropbox_resume_text_bundle(
                    dropbox_path=dropbox_path,
                    dropbox_folder_path=folder_path,
                    downloaded_file=downloaded_file,
                    extracted_resume_text=extracted_resume_text,
                )
                prepared_extraction_input = (
                    build_resume_extraction_input_from_resume_bundle(
                        resume_text_bundle=prepared_resume_bundle,
                    )
                )
                cleaned_resume_text = prepared_extraction_input.get("cleaned_resume_text")
                if isinstance(cleaned_resume_text, str) and cleaned_resume_text.strip() != "":
                    duplicate_resume_match = find_existing_resume_duplicate_match(
                        cleaned_resume_text=cleaned_resume_text,
                    )

            if (
                duplicate_resume_match is not None
                and prepared_extraction_input is not None
            ):
                persisted_summary = persist_dropbox_duplicate_resume_match(
                    extraction_input=prepared_extraction_input,
                    matched_resume=duplicate_resume_match,
                )
                persisted_resumes.append(
                    {
                        **persisted_summary,
                        "dropbox_path": dropbox_path,
                        "file_name": file_name,
                        "model_name": None,
                        "quality_score": persisted_summary.get("quality_score"),
                        "quality_gate": {"llm_extraction_skipped": True},
                    }
                )
                if persisted_summary.get("quality_status") == "pass":
                    status_counts["accepted"] += 1
                    file_timing["status"] = "accepted"
                else:
                    status_counts["non_pass"] += 1
                    file_timing["status"] = "non_pass"
                continue

            structured_resume_started_at = perf_counter()
            result = extract_dropbox_candidate_resume_profile_with_quality_gate(
                dropbox_path=dropbox_path,
                dropbox_folder_path=folder_path,
                downloaded_file=downloaded_file,
                extracted_resume_text=extracted_resume_text,
            )
            persisted_summary = persist_scored_resume_extraction_result(result)
            file_timing["structured_resume_seconds"] = round(
                perf_counter() - structured_resume_started_at,
                4,
            )

            persisted_resumes.append(
                {
                    **persisted_summary,
                    "dropbox_path": dropbox_path,
                    "file_name": file_name,
                    "model_name": result.get("model_profile", {}).get("model_name"),
                    "quality_score": result.get("quality_assessment", {}).get(
                        "quality_score"
                    ),
                    "quality_gate": result.get("quality_gate"),
                }
            )
            if result.get("quality_assessment", {}).get("status") == "pass":
                status_counts["accepted"] += 1
                file_timing["status"] = "accepted"
            else:
                status_counts["non_pass"] += 1
                file_timing["status"] = "non_pass"
        except ResumeTextExtractionError as exc:
            status_counts["unsupported"] += 1
            file_timing["status"] = "unsupported"
            failed_items.append(
                {
                    "dropbox_path": dropbox_path,
                    "file_name": file_name,
                    "stage": "resume_text_extraction",
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
        except Exception as exc:
            status_counts["failed"] += 1
            file_timing["status"] = "failed"
            failed_items.append(
                {
                    "dropbox_path": dropbox_path,
                    "file_name": file_name,
                    "stage": "structured_resume_extraction_or_persistence",
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
        finally:
            _finalize_file_timing(
                file_timing=file_timing,
                timing_totals_seconds=timing_totals_seconds,
                file_started_at=file_started_at,
                file_timing_preview=file_timing_preview,
            )
            processed_file_count += 1

    summary = _build_run_summary(
        run_started_at=run_started_at,
        folder_path=folder_path,
        file_limit=file_limit,
        dropbox_list_limit=dropbox_list_limit,
        resume_file_offset=resume_file_offset,
        force_reprocess=force_reprocess,
        process_entire_folder=process_entire_folder,
        folder_preview=folder_preview,
        entries=entries,
        total_eligible_resume_file_count=total_eligible_resume_file_count,
        window_offsets_processed=window_offsets_processed,
        processed_file_count=processed_file_count,
        status_counts=status_counts,
        timing_totals_seconds=timing_totals_seconds,
        file_timing_preview=file_timing_preview,
        persisted_resumes=persisted_resumes,
        skipped_items=skipped_items,
        failed_items=failed_items,
    )
    artifact_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"artifact: {artifact_path}")
    print(f"folder path: {summary['folder_path']}")
    print(f"listed entries: {summary['folder_entry_count']}")
    print(f"total eligible resume-like files: {summary['total_eligible_resume_file_count']}")
    print(f"resume-like files selected: {summary['selected_resume_file_count']}")
    print(f"resume-file offset: {summary['resume_file_offset']}")
    if process_entire_folder:
        print(f"window offsets processed: {summary['window_offsets_processed']}")
    print(f"already processed: {summary['already_processed_count']}")
    print(f"new resume files: {summary['new_resume_file_count']}")
    print(f"persisted resumes: {summary['persisted_resume_count']}")
    print(f"pass resumes: {summary['accepted_resume_count']}")
    print(f"non-pass resumes: {summary['non_pass_count']}")
    print(f"skipped resumes: {summary['skipped_count']}")
    print(f"unsupported files: {summary['unsupported_count']}")
    print(f"failed files: {summary['failed_count']}")


def _build_run_summary(
    *,
    run_started_at: datetime,
    folder_path: str,
    file_limit: int,
    dropbox_list_limit: int,
    resume_file_offset: int,
    force_reprocess: bool,
    process_entire_folder: bool,
    folder_preview: dict[str, Any],
    entries: list[dict[str, Any]],
    total_eligible_resume_file_count: int,
    window_offsets_processed: list[int],
    processed_file_count: int,
    status_counts: dict[str, int],
    timing_totals_seconds: dict[str, float],
    file_timing_preview: list[dict[str, Any]],
    persisted_resumes: list[dict[str, Any]],
    skipped_items: list[dict[str, Any]],
    failed_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build the artifact summary for one Dropbox folder run.
    """

    processed_file_denominator = max(processed_file_count, 1)
    timing_averages_seconds = {
        key: round(value / processed_file_denominator, 4)
        for key, value in timing_totals_seconds.items()
    }
    rounded_timing_totals_seconds = {
        key: round(value, 4) for key, value in timing_totals_seconds.items()
    }

    return {
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "run_started_at": run_started_at.isoformat(),
        "dropbox_account_id": DROPBOX_ACCOUNT_ID,
        "folder_path": folder_path,
        "file_limit": file_limit,
        "dropbox_list_limit": dropbox_list_limit,
        "resume_file_offset": resume_file_offset,
        "force_reprocess": force_reprocess,
        "process_entire_folder": process_entire_folder,
        "folder_entry_count": len(entries),
        "folder_has_more": bool(folder_preview.get("has_more")),
        "total_eligible_resume_file_count": total_eligible_resume_file_count,
        "window_offsets_processed": window_offsets_processed,
        "listed_file_preview": [
            {
                "name": entry.get("name"),
                "path_display": entry.get("path_display"),
                "tag": entry.get(".tag"),
            }
            for entry in entries[:20]
        ],
        "processed_file_count": processed_file_count,
        "selected_resume_file_count": status_counts["selected_resume_file"],
        "already_processed_count": status_counts["skipped"],
        "new_resume_file_count": (
            status_counts["selected_resume_file"] - status_counts["skipped"]
        ),
        "persisted_resume_count": status_counts["accepted"] + status_counts["non_pass"],
        "accepted_resume_count": status_counts["accepted"],
        "non_pass_count": status_counts["non_pass"],
        "skipped_count": status_counts["skipped"],
        "unsupported_count": status_counts["unsupported"],
        "failed_count": status_counts["failed"],
        "timing_totals_seconds": rounded_timing_totals_seconds,
        "timing_averages_seconds": timing_averages_seconds,
        "file_timing_preview": file_timing_preview[:20],
        "persisted_resume_preview": persisted_resumes[:10],
        "skipped_items_preview": skipped_items[:10],
        "failed_items_preview": failed_items[:10],
    }


def _list_folder_entries(
    *,
    access_token: str,
    folder_path: str,
    dropbox_list_limit: int,
    stop_after_resume_file_count: int | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Page through Dropbox folder results until enough eligible CV files are available.
    """

    folder_preview = fetch_dropbox_list_folder(
        access_token=access_token,
        path=folder_path,
        recursive=False,
        limit=dropbox_list_limit,
        timeout_seconds=240.0,
    )
    raw_entries = folder_preview.get("entries", [])
    entries = raw_entries if isinstance(raw_entries, list) else []
    cursor = folder_preview.get("cursor")
    has_more = bool(folder_preview.get("has_more"))

    while has_more:
        if (
            stop_after_resume_file_count is not None
            and _count_resume_entries(entries) >= stop_after_resume_file_count
        ):
            break
        if not isinstance(cursor, str) or cursor.strip() == "":
            break

        continuation_page = fetch_dropbox_list_folder_continue(
            access_token=access_token,
            cursor=cursor,
            timeout_seconds=240.0,
        )
        continued_entries = continuation_page.get("entries", [])
        if isinstance(continued_entries, list):
            entries.extend(continued_entries)

        cursor = continuation_page.get("cursor")
        has_more = bool(continuation_page.get("has_more"))
        folder_preview["cursor"] = cursor
        folder_preview["has_more"] = has_more

    return folder_preview, entries


def _count_resume_entries(raw_entries: list[dict[str, Any]]) -> int:
    """
    Return the number of resume-like file entries in one Dropbox listing.
    """

    return sum(
        1
        for entry in raw_entries
        if isinstance(entry, dict) and _looks_like_resume_entry(entry)
    )


def _select_resume_entries(
    raw_entries: list[dict[str, Any]],
    *,
    file_limit: int,
) -> list[dict[str, Any]]:
    """
    Return the bounded set of resume-like Dropbox file entries to process.
    """

    selected_entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        if not _looks_like_resume_entry(entry):
            continue
        selected_entries.append(entry)
        if len(selected_entries) >= file_limit:
            break
    return selected_entries


def _slice_resume_entries(
    raw_entries: list[dict[str, Any]],
    *,
    resume_file_offset: int,
    file_limit: int,
) -> list[dict[str, Any]]:
    """
    Return one bounded window of resume-like Dropbox file entries.
    """

    eligible_entries = [
        entry
        for entry in raw_entries
        if isinstance(entry, dict) and _looks_like_resume_entry(entry)
    ]
    return eligible_entries[resume_file_offset : resume_file_offset + file_limit]


def _looks_like_resume_entry(entry: dict[str, Any]) -> bool:
    """
    Return whether one Dropbox folder entry is a usable resume-like file.
    """

    if entry.get(".tag") != "file":
        return False

    file_name = _clean_string(entry.get("name"))
    if file_name is None:
        return False

    lowered_name = file_name.lower()
    if lowered_name.endswith(".lnk"):
        return False
    return lowered_name.endswith(SUPPORTED_RESUME_SUFFIXES)


def _build_dropbox_extraction_source_record_key(*, dropbox_path: str) -> str:
    """
    Return the canonical Dropbox resume-extraction source-record key.
    """

    return f"{dropbox_path}:{dropbox_path}"


def _find_existing_dropbox_resume_skip_record(*, dropbox_path: str) -> dict[str, Any] | None:
    """
    Return one existing Dropbox resume-extraction row that is safe to skip.
    """

    query = """
        SELECT
            sr.id AS source_record_uuid,
            sr.source_record_id,
            sr.source_payload -> 'quality_assessment' ->> 'status' AS quality_status,
            NULLIF(
                sr.source_payload -> 'quality_assessment' ->> 'quality_score',
                ''
            )::int AS quality_score,
            d.id AS document_id,
            d.title AS document_title
        FROM source_records sr
        JOIN source_record_links srl
            ON srl.source_record_id = sr.id
        JOIN documents d
            ON d.id = srl.document_id
        WHERE sr.source_system = 'dropbox'
          AND sr.source_record_type = 'dropbox_resume_extraction'
          AND sr.source_record_id = %(source_record_id)s
          AND d.document_type = 'resume'
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "source_record_id": _build_dropbox_extraction_source_record_key(
                        dropbox_path=dropbox_path
                    )
                },
            )
            row = cursor.fetchone()

    return dict(row) if row is not None else None


def _finalize_file_timing(
    *,
    file_timing: dict[str, Any],
    timing_totals_seconds: dict[str, float],
    file_started_at: float,
    file_timing_preview: list[dict[str, Any]],
) -> None:
    """
    Finalize one file timing row and fold it into preview + totals.
    """

    file_timing["total_file_seconds"] = round(
        perf_counter() - file_started_at,
        4,
    )

    for key in timing_totals_seconds:
        timing_totals_seconds[key] += float(file_timing.get(key, 0.0) or 0.0)

    if len(file_timing_preview) < 20:
        file_timing_preview.append(dict(file_timing))


def _clean_string(value: Any) -> str | None:
    """
    Return a stripped string value, or `None` for blank-like input.
    """

    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    return cleaned_value or None


if __name__ == "__main__":
    main()
