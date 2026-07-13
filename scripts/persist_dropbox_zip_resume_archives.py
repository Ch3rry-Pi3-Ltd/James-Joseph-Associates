"""
Persist Dropbox zip-member CV archives through the canonical Dropbox resume path.

This is the companion to the loose-file Dropbox runner. It exists for legacy
branches where Dropbox folders contain `.zip` bundles of CV files instead of
direct `.pdf` / `.docx` / `.doc` files.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any
from zipfile import ZipFile

from backend.db.candidate_semantic_blocks import backfill_candidate_semantic_blocks
from backend.db.document_chunk_backfill import backfill_document_chunks
from backend.db.document_embedding_backfill import backfill_chunk_embeddings
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
from scripts.persist_dropbox_folder_resume_chunk import (
    SUPPORTED_RESUME_SUFFIXES,
    _build_dropbox_extraction_source_record_key,
    _clean_string,
    _count_item_values,
    _finalize_file_timing,
    _find_existing_dropbox_resume_skip_record,
)
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    _load_dropbox_connection,
)

DEFAULT_BASE_FOLDER_PATH = "/### BIG BAD CV ARCHIVE inc. RFL/ARCHIVE - JBS - [to export to BH]"
DEFAULT_ARCHIVE_LIMIT: int | None = None
DEFAULT_MEMBER_LIMIT = 20
DEFAULT_DROPBOX_LIST_LIMIT = 200


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Persist Dropbox zip-member CV archives through the canonical "
            "Dropbox resume ingestion path."
        )
    )
    parser.add_argument(
        "--base-folder-path",
        default=DEFAULT_BASE_FOLDER_PATH,
        help="Dropbox folder to scan recursively for zip archives.",
    )
    parser.add_argument(
        "--archive-limit",
        type=int,
        default=DEFAULT_ARCHIVE_LIMIT,
        help="Optional cap on how many zip archives to process.",
    )
    parser.add_argument(
        "--member-limit",
        type=int,
        default=DEFAULT_MEMBER_LIMIT,
        help="Archive-member window size.",
    )
    parser.add_argument(
        "--member-offset",
        type=int,
        default=0,
        help="Zero-based resume-member offset within each zip archive.",
    )
    parser.add_argument(
        "--dropbox-list-limit",
        type=int,
        default=DEFAULT_DROPBOX_LIST_LIMIT,
        help="Dropbox page size for zip archive discovery.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Bypass the Dropbox-path skip check and reprocess already-ingested members.",
    )
    parser.add_argument(
        "--process-entire-archive",
        action="store_true",
        help="Walk each zip archive from the starting offset in member-limit windows.",
    )
    parser.add_argument(
        "--skip-chunk-backfill",
        action="store_true",
        help="Skip document chunk backfill for the processed archive members.",
    )
    parser.add_argument(
        "--skip-embedding-backfill",
        action="store_true",
        help="Skip document embedding backfill for the processed archive members.",
    )
    parser.add_argument(
        "--skip-semantic-backfill",
        action="store_true",
        help="Skip candidate semantic block backfill for newly persisted candidates.",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=1000,
        help="Maximum canonical resume documents to chunk per backfill pass.",
    )
    parser.add_argument(
        "--embedding-limit",
        type=int,
        default=4000,
        help="Maximum chunk rows to embed per backfill pass.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=25,
        help="Embedding provider batch size.",
    )
    parser.add_argument(
        "--semantic-candidate-limit",
        type=int,
        default=500,
        help="Maximum candidate rows to backfill in the structured semantic index.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the aggregate JSON report.",
    )
    return parser


def build_archive_artifact_path(archive_path: str, *, member_offset: int) -> Path:
    safe_name = (
        archive_path.strip("/")
        .replace("/", "__")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
    )
    if safe_name == "":
        safe_name = "dropbox_zip_root"
    safe_name = safe_name[:120].rstrip("._")
    return (
        Path("temp")
        / f"dropbox_zip_resume_{safe_name}_offset_{member_offset}_persisted.json"
    )


def main() -> None:
    args = build_parser().parse_args()

    base_folder_path = str(args.base_folder_path).strip()
    if base_folder_path == "":
        raise RuntimeError("base_folder_path must be a non-empty Dropbox path.")

    archive_limit = (
        None if args.archive_limit is None else max(1, int(args.archive_limit))
    )
    member_limit = max(1, int(args.member_limit))
    member_offset = max(0, int(args.member_offset))
    dropbox_list_limit = max(1, int(args.dropbox_list_limit))

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    access_token = stored_connection["access_token"]
    assert isinstance(access_token, str)

    archive_paths = list_zip_archives(
        access_token=access_token,
        base_folder_path=base_folder_path,
        dropbox_list_limit=dropbox_list_limit,
    )
    if archive_limit is not None:
        archive_paths = archive_paths[:archive_limit]

    archive_summaries: list[dict[str, Any]] = []
    failed_archives: list[dict[str, Any]] = []
    archive_prefixes: list[str] = []
    newly_persisted_candidate_ids: list[str] = []

    for archive_index, archive_path in enumerate(archive_paths, start=1):
        print(f"[{archive_index}/{len(archive_paths)}] Processing {archive_path}")
        artifact_path = build_archive_artifact_path(
            archive_path,
            member_offset=member_offset,
        )
        try:
            summary = run_dropbox_zip_archive_resume_persistence(
                access_token=access_token,
                archive_path=archive_path,
                member_limit=member_limit,
                member_offset=member_offset,
                force_reprocess=bool(args.force_reprocess),
                process_entire_archive=bool(args.process_entire_archive),
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(
                json.dumps(summary, indent=2, default=str),
                encoding="utf-8",
            )
            archive_summaries.append(
                {
                    "archive_path": archive_path,
                    "artifact_path": str(artifact_path),
                    **summary,
                }
            )
            if summary["persisted_resume_count"] > 0:
                archive_prefixes.append(f"{archive_path}::")
            for resume in summary["persisted_resume_preview"]:
                candidate_id = resume.get("candidate_id")
                if isinstance(candidate_id, str) and candidate_id.strip() != "":
                    newly_persisted_candidate_ids.append(candidate_id.strip())
            print(
                "  persisted={persisted} skipped={skipped} unsupported={unsupported} failed={failed}".format(
                    persisted=summary["persisted_resume_count"],
                    skipped=summary["skipped_count"],
                    unsupported=summary["unsupported_count"],
                    failed=summary["failed_count"],
                )
            )
        except Exception as exc:
            failed_archives.append(
                {
                    "archive_path": archive_path,
                    "artifact_path": str(artifact_path),
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
            print(f"  failed with {exc.__class__.__name__}: {exc}")

    unique_prefixes = sorted(set(archive_prefixes))
    unique_candidate_ids = sorted(set(newly_persisted_candidate_ids))

    chunk_summary: dict[str, Any] | None = None
    if unique_prefixes and not args.skip_chunk_backfill:
        chunk_summary = backfill_document_chunks(
            document_types=("resume",),
            linked_source_record_id_prefixes=tuple(unique_prefixes),
            include_already_chunked=False,
            limit=max(1, int(args.chunk_limit)),
        )

    embedding_summary: dict[str, Any] | None = None
    if unique_prefixes and not args.skip_embedding_backfill:
        embedding_summary = backfill_chunk_embeddings(
            document_types=("resume",),
            linked_source_record_id_prefixes=tuple(unique_prefixes),
            limit=max(1, int(args.embedding_limit)),
            batch_size=max(1, int(args.embedding_batch_size)),
        )

    semantic_summary: dict[str, Any] | None = None
    if unique_candidate_ids and not args.skip_semantic_backfill:
        semantic_summary = backfill_candidate_semantic_blocks(
            limit=max(len(unique_candidate_ids), int(args.semantic_candidate_limit)),
            candidate_ids=unique_candidate_ids,
            include_already_indexed=False,
            embedding_batch_size=max(1, int(args.embedding_batch_size)),
            dry_run=False,
        )

    aggregate_summary = {
        "base_folder_path": base_folder_path,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "archive_count": len(archive_paths),
        "processed_archive_count": len(archive_summaries),
        "failed_archive_count": len(failed_archives),
        "archive_summaries": archive_summaries,
        "failed_archives": failed_archives,
        "archive_source_record_prefixes": unique_prefixes,
        "newly_persisted_candidate_ids": unique_candidate_ids,
        "chunk_backfill_summary": chunk_summary,
        "embedding_backfill_summary": embedding_summary,
        "semantic_backfill_summary": semantic_summary,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(aggregate_summary, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"aggregate artifact: {args.output_json}")

    print(f"zip archives discovered: {len(archive_paths)}")
    print(f"zip archives processed: {len(archive_summaries)}")
    print(f"zip archives failed: {len(failed_archives)}")
    if chunk_summary is not None:
        print(
            "chunk backfill documents processed: "
            f"{chunk_summary['documents_processed']}"
        )
    if embedding_summary is not None:
        print(
            "embedding backfill chunks embedded: "
            f"{embedding_summary['chunks_embedded']}"
        )
    if semantic_summary is not None:
        print(
            "semantic block candidates processed: "
            f"{semantic_summary['candidates_processed']}"
        )


def run_dropbox_zip_archive_resume_persistence(
    *,
    access_token: str,
    archive_path: str,
    member_limit: int,
    member_offset: int,
    force_reprocess: bool = False,
    process_entire_archive: bool = False,
) -> dict[str, Any]:
    run_started_at = datetime.now(timezone.utc)
    downloaded_archive = download_dropbox_file(
        access_token=access_token,
        path=archive_path,
        timeout_seconds=240.0,
    )
    archive_bytes = downloaded_archive["content_bytes"]
    assert isinstance(archive_bytes, bytes)

    with ZipFile(BytesIO(archive_bytes)) as archive:
        eligible_member_names = [
            member_name
            for member_name in archive.namelist()
            if _looks_like_resume_member_name(member_name)
        ]
        selected_member_names = eligible_member_names[
            member_offset : (
                len(eligible_member_names)
                if process_entire_archive
                else member_offset + member_limit
            )
        ]

        persisted_resumes: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []
        unsupported_items: list[dict[str, Any]] = []
        skipped_items: list[dict[str, Any]] = []
        file_timing_preview: list[dict[str, Any]] = []
        status_counts = {
            "selected_resume_file": len(selected_member_names),
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
        window_offsets_processed = list(
            range(
                member_offset,
                member_offset + len(selected_member_names),
                member_limit,
            )
        )
        archive_folder_path = str(PurePosixPath(archive_path).parent)

        for file_index, member_name in enumerate(selected_member_names, start=1):
            file_started_at = perf_counter()
            virtual_dropbox_path = _build_archive_member_virtual_path(
                archive_path=archive_path,
                member_name=member_name,
            )
            file_name = PurePosixPath(member_name).name
            file_timing: dict[str, Any] = {
                "file_index": file_index,
                "dropbox_path": virtual_dropbox_path,
                "file_name": file_name,
                "status": None,
                "skip_lookup_seconds": 0.0,
                "download_seconds": 0.0,
                "resume_text_extraction_seconds": 0.0,
                "structured_resume_seconds": 0.0,
            }
            current_stage = "preflight"

            try:
                if not force_reprocess:
                    current_stage = "existing_dropbox_skip_lookup"
                    skip_lookup_started_at = perf_counter()
                    existing_skip_record = _find_existing_dropbox_resume_skip_record(
                        dropbox_path=virtual_dropbox_path
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
                                "dropbox_path": virtual_dropbox_path,
                                "file_name": file_name,
                                "source_record_id": _build_dropbox_extraction_source_record_key(
                                    dropbox_path=virtual_dropbox_path
                                ),
                                "document_id": existing_skip_record.get("document_id"),
                                "document_title": existing_skip_record.get("document_title"),
                                "quality_status": existing_skip_record.get("quality_status"),
                                "quality_score": existing_skip_record.get("quality_score"),
                            }
                        )
                        continue

                current_stage = "archive_member_read"
                member_bytes = archive.read(member_name)
                file_timing["download_seconds"] = 0.0

                current_stage = "resume_text_extraction"
                text_extraction_started_at = perf_counter()
                extracted_resume_text = extract_text_from_resume_bytes(
                    content_bytes=member_bytes,
                    file_name=file_name,
                    content_type=None,
                )
                file_timing["resume_text_extraction_seconds"] = round(
                    perf_counter() - text_extraction_started_at,
                    4,
                )

                member_file = {
                    "file_name": file_name,
                    "content_type": None,
                    "content_bytes": member_bytes,
                    "file_metadata": downloaded_archive.get("file_metadata"),
                }

                duplicate_resume_match: dict[str, Any] | None = None
                prepared_extraction_input: dict[str, Any] | None = None
                if not force_reprocess and isinstance(extracted_resume_text, dict):
                    current_stage = "duplicate_resume_match_lookup"
                    prepared_resume_bundle = build_dropbox_resume_text_bundle(
                        dropbox_path=virtual_dropbox_path,
                        dropbox_folder_path=archive_folder_path,
                        downloaded_file=member_file,
                        extracted_resume_text=extracted_resume_text,
                    )
                    prepared_extraction_input = (
                        build_resume_extraction_input_from_resume_bundle(
                            resume_text_bundle=prepared_resume_bundle,
                        )
                    )
                    cleaned_resume_text = prepared_extraction_input.get(
                        "cleaned_resume_text"
                    )
                    if (
                        isinstance(cleaned_resume_text, str)
                        and cleaned_resume_text.strip() != ""
                    ):
                        duplicate_resume_match = find_existing_resume_duplicate_match(
                            cleaned_resume_text=cleaned_resume_text,
                        )

                if (
                    duplicate_resume_match is not None
                    and prepared_extraction_input is not None
                ):
                    current_stage = "duplicate_resume_persistence"
                    persisted_summary = persist_dropbox_duplicate_resume_match(
                        extraction_input=prepared_extraction_input,
                        matched_resume=duplicate_resume_match,
                    )
                    persisted_resumes.append(
                        {
                            **persisted_summary,
                            "dropbox_path": virtual_dropbox_path,
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

                current_stage = "structured_resume_extraction"
                structured_resume_started_at = perf_counter()
                result = extract_dropbox_candidate_resume_profile_with_quality_gate(
                    dropbox_path=virtual_dropbox_path,
                    dropbox_folder_path=archive_folder_path,
                    downloaded_file=member_file,
                    extracted_resume_text=extracted_resume_text,
                )
                current_stage = "structured_resume_persistence"
                persisted_summary = persist_scored_resume_extraction_result(result)
                file_timing["structured_resume_seconds"] = round(
                    perf_counter() - structured_resume_started_at,
                    4,
                )
                persisted_resumes.append(
                    {
                        **persisted_summary,
                        "dropbox_path": virtual_dropbox_path,
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
                unsupported_items.append(
                    {
                        "dropbox_path": virtual_dropbox_path,
                        "file_name": file_name,
                        "stage": current_stage,
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
            except Exception as exc:
                status_counts["failed"] += 1
                file_timing["status"] = "failed"
                failed_items.append(
                    {
                        "dropbox_path": virtual_dropbox_path,
                        "file_name": file_name,
                        "stage": current_stage,
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

    processed_file_denominator = max(processed_file_count, 1)
    timing_averages_seconds = {
        key: round(value / processed_file_denominator, 4)
        for key, value in timing_totals_seconds.items()
    }
    rounded_timing_totals_seconds = {
        key: round(value, 4) for key, value in timing_totals_seconds.items()
    }
    unsupported_stage_counts = _count_item_values(unsupported_items, key="stage")
    unsupported_error_type_counts = _count_item_values(
        unsupported_items, key="error_type"
    )
    failed_stage_counts = _count_item_values(failed_items, key="stage")
    failed_error_type_counts = _count_item_values(failed_items, key="error_type")
    return {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "run_started_at": run_started_at.isoformat(),
        "source_system": "dropbox",
        "archive_path": archive_path,
        "archive_folder_path": str(PurePosixPath(archive_path).parent),
        "member_limit": member_limit,
        "member_offset": member_offset,
        "force_reprocess": force_reprocess,
        "process_entire_archive": process_entire_archive,
        "archive_member_count": len(selected_member_names),
        "total_eligible_resume_member_count": len(eligible_member_names),
        "selected_resume_file_count": status_counts["selected_resume_file"],
        "window_offsets_processed": window_offsets_processed,
        "processed_file_count": processed_file_count,
        "persisted_resume_count": len(persisted_resumes),
        "accepted_resume_count": status_counts["accepted"],
        "non_pass_count": status_counts["non_pass"],
        "unsupported_count": status_counts["unsupported"],
        "failed_count": status_counts["failed"],
        "skipped_count": status_counts["skipped"],
        "already_processed_count": status_counts["skipped"],
        "new_resume_file_count": max(
            status_counts["selected_resume_file"] - status_counts["skipped"],
            0,
        ),
        "persisted_resume_preview": persisted_resumes[:50],
        "skipped_preview": skipped_items[:50],
        "unsupported_preview": unsupported_items[:50],
        "failed_preview": failed_items[:50],
        "timing_totals_seconds": rounded_timing_totals_seconds,
        "timing_averages_seconds": timing_averages_seconds,
        "file_timing_preview": file_timing_preview,
        "unsupported_stage_counts": unsupported_stage_counts,
        "unsupported_error_type_counts": unsupported_error_type_counts,
        "failed_stage_counts": failed_stage_counts,
        "failed_error_type_counts": failed_error_type_counts,
    }


def list_zip_archives(
    *,
    access_token: str,
    base_folder_path: str,
    dropbox_list_limit: int,
) -> list[str]:
    preview = fetch_dropbox_list_folder(
        access_token=access_token,
        path=base_folder_path,
        recursive=True,
        limit=dropbox_list_limit,
        timeout_seconds=240.0,
    )
    entries = (
        list(preview.get("entries", []))
        if isinstance(preview.get("entries"), list)
        else []
    )
    cursor = preview.get("cursor")
    has_more = bool(preview.get("has_more"))

    while has_more:
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

    archive_paths = [
        str(entry["path_display"])
        for entry in entries
        if isinstance(entry, dict)
        and entry.get(".tag") == "file"
        and isinstance(entry.get("path_display"), str)
        and _looks_like_zip_entry_name(_clean_string(entry.get("name")))
    ]
    return sorted(archive_paths)


def _looks_like_zip_entry_name(file_name: str | None) -> bool:
    return isinstance(file_name, str) and file_name.lower().endswith(".zip")


def _looks_like_resume_member_name(member_name: str) -> bool:
    cleaned_member_name = _clean_string(member_name)
    if cleaned_member_name is None:
        return False
    if cleaned_member_name.endswith("/"):
        return False
    return cleaned_member_name.lower().endswith(SUPPORTED_RESUME_SUFFIXES)


def _build_archive_member_virtual_path(*, archive_path: str, member_name: str) -> str:
    return f"{archive_path}::{member_name}"


if __name__ == "__main__":
    main()
