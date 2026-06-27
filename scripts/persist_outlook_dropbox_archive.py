"""
Persist the Outlook Dropbox export archive through the canonical Dropbox CV path.

This script is the operational bridge between:

1. Outlook Inbox CV attachment export into Dropbox
2. canonical Dropbox CV persistence into Supabase
3. chunk + embedding backfill for semantic retrieval

The intent is simple: once Outlook CVs have been archived under
`/+++ Outlook CV Export/...`, ingest them exactly like the other Dropbox CV
folders so they are:

- persisted with Dropbox-backed provenance
- downloadable in the candidate UI
- chunked and embedded for retrieval
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from backend.db.document_chunk_backfill import backfill_document_chunks
from backend.db.document_embedding_backfill import backfill_chunk_embeddings
from backend.services.dropbox_api import (
    fetch_dropbox_list_folder,
    fetch_dropbox_list_folder_continue,
)
from scripts.persist_dropbox_folder_resume_chunk import (
    DROPBOX_ACCOUNT_ID,
    _looks_like_resume_entry,
    _load_dropbox_connection,
    build_artifact_path,
    run_dropbox_folder_resume_persistence,
)

DEFAULT_BASE_FOLDER_PATH = "/+++ Outlook CV Export"
DEFAULT_FILE_LIMIT = 20
DEFAULT_DROPBOX_LIST_LIMIT = 200
DEFAULT_CHUNK_LIMIT = 250
DEFAULT_EMBEDDING_LIMIT = 1000
DEFAULT_EMBEDDING_BATCH_SIZE = 25


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Persist the Outlook Dropbox export archive through the canonical "
            "Dropbox CV ingestion path, then backfill chunks and embeddings."
        )
    )
    parser.add_argument(
        "--base-folder-path",
        default=DEFAULT_BASE_FOLDER_PATH,
        help="Dropbox root folder containing exported Outlook CV files.",
    )
    parser.add_argument(
        "--folder-limit",
        type=int,
        default=None,
        help="Optional cap on how many resume-bearing subfolders to process.",
    )
    parser.add_argument(
        "--file-limit",
        type=int,
        default=DEFAULT_FILE_LIMIT,
        help="Per-folder resume window size used by the Dropbox CV runner.",
    )
    parser.add_argument(
        "--dropbox-list-limit",
        type=int,
        default=DEFAULT_DROPBOX_LIST_LIMIT,
        help="Dropbox page size for folder discovery and per-folder ingestion.",
    )
    parser.add_argument(
        "--resume-file-offset",
        type=int,
        default=0,
        help="Starting resume offset inside each folder.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Reprocess Dropbox CV paths even when they were already ingested.",
    )
    parser.add_argument(
        "--skip-chunk-backfill",
        action="store_true",
        help="Skip document chunk backfill after ingestion.",
    )
    parser.add_argument(
        "--skip-embedding-backfill",
        action="store_true",
        help="Skip embedding backfill after ingestion.",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=DEFAULT_CHUNK_LIMIT,
        help="Maximum number of resume documents to chunk per backfill pass.",
    )
    parser.add_argument(
        "--chunk-max-chars",
        type=int,
        default=1200,
        help="Maximum chunk length in characters.",
    )
    parser.add_argument(
        "--chunk-overlap-chars",
        type=int,
        default=150,
        help="Chunk overlap size in characters.",
    )
    parser.add_argument(
        "--embedding-limit",
        type=int,
        default=DEFAULT_EMBEDDING_LIMIT,
        help="Maximum number of chunk rows to embed per pass.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=DEFAULT_EMBEDDING_BATCH_SIZE,
        help="Embedding provider batch size.",
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

    base_folder_path = str(args.base_folder_path).strip()
    if base_folder_path == "":
        raise RuntimeError("base_folder_path must be a non-empty Dropbox path.")

    dropbox_list_limit = max(1, int(args.dropbox_list_limit))
    file_limit = max(1, int(args.file_limit))
    resume_file_offset = max(0, int(args.resume_file_offset))
    folder_limit = (
        None
        if args.folder_limit is None
        else max(1, int(args.folder_limit))
    )

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    access_token = stored_connection["access_token"]
    assert isinstance(access_token, str)

    resume_folders = list_resume_bearing_dropbox_folders(
        access_token=access_token,
        base_folder_path=base_folder_path,
        dropbox_list_limit=dropbox_list_limit,
    )
    if folder_limit is not None:
        resume_folders = resume_folders[:folder_limit]

    folder_summaries: list[dict[str, Any]] = []
    failed_folders: list[dict[str, Any]] = []

    for folder_index, folder_path in enumerate(resume_folders, start=1):
        print(f"[{folder_index}/{len(resume_folders)}] Processing {folder_path}")
        artifact_path = build_artifact_path(
            folder_path,
            resume_file_offset=resume_file_offset,
        )
        try:
            summary = run_dropbox_folder_resume_persistence(
                access_token=access_token,
                folder_path=folder_path,
                file_limit=file_limit,
                dropbox_list_limit=dropbox_list_limit,
                resume_file_offset=resume_file_offset,
                force_reprocess=bool(args.force_reprocess),
                process_entire_folder=True,
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(
                json.dumps(summary, indent=2, default=str),
                encoding="utf-8",
            )
            folder_summaries.append(
                {
                    "folder_path": folder_path,
                    "artifact_path": str(artifact_path),
                    **summary,
                }
            )
            print(
                "  persisted={persisted} skipped={skipped} unsupported={unsupported} failed={failed}".format(
                    persisted=summary["persisted_resume_count"],
                    skipped=summary["skipped_count"],
                    unsupported=summary["unsupported_count"],
                    failed=summary["failed_count"],
                )
            )
        except Exception as exc:
            failed_folders.append(
                {
                    "folder_path": folder_path,
                    "artifact_path": str(artifact_path),
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
            print(
                f"  failed with {exc.__class__.__name__}: {exc}"
            )

    chunk_runs: list[dict[str, Any]] = []
    if not args.skip_chunk_backfill:
        chunk_runs = _run_chunk_backfill(
            base_folder_path=base_folder_path,
            chunk_limit=max(1, int(args.chunk_limit)),
            chunk_max_chars=max(100, int(args.chunk_max_chars)),
            chunk_overlap_chars=max(0, int(args.chunk_overlap_chars)),
        )

    embedding_runs: list[dict[str, Any]] = []
    if not args.skip_embedding_backfill:
        embedding_runs = _run_embedding_backfill(
            base_folder_path=base_folder_path,
            embedding_limit=max(1, int(args.embedding_limit)),
            embedding_batch_size=max(1, int(args.embedding_batch_size)),
        )

    summary = {
        "base_folder_path": base_folder_path,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "resume_folder_count": len(resume_folders),
        "processed_folder_count": len(folder_summaries),
        "failed_folder_count": len(failed_folders),
        "folder_summaries": folder_summaries,
        "failed_folders": failed_folders,
        "chunk_backfill_runs": chunk_runs,
        "embedding_backfill_runs": embedding_runs,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"aggregate artifact: {args.output_json}")

    print(f"resume folders discovered: {len(resume_folders)}")
    print(f"resume folders processed: {len(folder_summaries)}")
    print(f"resume folders failed: {len(failed_folders)}")
    if chunk_runs:
        print(
            f"chunk backfill documents processed: {sum(run['documents_processed'] for run in chunk_runs)}"
        )
    if embedding_runs:
        print(
            f"embedding backfill chunks embedded: {sum(run['chunks_embedded'] for run in embedding_runs)}"
        )


def list_resume_bearing_dropbox_folders(
    *,
    access_token: str,
    base_folder_path: str,
    dropbox_list_limit: int,
) -> list[str]:
    """
    Return sorted Dropbox folder paths that contain at least one resume-like file.
    """

    preview = fetch_dropbox_list_folder(
        access_token=access_token,
        path=base_folder_path,
        recursive=True,
        limit=dropbox_list_limit,
        timeout_seconds=240.0,
    )
    entries = list(preview.get("entries", [])) if isinstance(preview.get("entries"), list) else []
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

    folder_paths = {
        str(PurePosixPath(entry["path_display"]).parent)
        for entry in entries
        if isinstance(entry, dict)
        and _looks_like_resume_entry(entry)
        and isinstance(entry.get("path_display"), str)
        and entry.get("path_display", "").strip() != ""
    }

    return sorted(folder_paths)


def _run_chunk_backfill(
    *,
    base_folder_path: str,
    chunk_limit: int,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    while True:
        summary = backfill_document_chunks(
            document_types=("resume",),
            linked_source_record_id_prefixes=(base_folder_path,),
            include_already_chunked=False,
            limit=chunk_limit,
            max_chars=chunk_max_chars,
            overlap_chars=chunk_overlap_chars,
            dry_run=False,
        )
        runs.append(summary)
        print(
            f"chunk pass {len(runs)}: selected={summary['documents_selected']} processed={summary['documents_processed']} inserted={summary['chunks_inserted']}"
        )
        if summary["documents_selected"] == 0:
            break
    return runs


def _run_embedding_backfill(
    *,
    base_folder_path: str,
    embedding_limit: int,
    embedding_batch_size: int,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    while True:
        summary = backfill_chunk_embeddings(
            document_types=("resume",),
            linked_source_record_id_prefixes=(base_folder_path,),
            limit=embedding_limit,
            batch_size=embedding_batch_size,
            dry_run=False,
        )
        runs.append(summary)
        print(
            f"embedding pass {len(runs)}: selected={summary['chunks_selected']} embedded={summary['chunks_embedded']}"
        )
        if summary["chunks_selected"] == 0:
            break
    return runs


if __name__ == "__main__":
    main()
