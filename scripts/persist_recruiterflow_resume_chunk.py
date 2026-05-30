"""
Persist one Recruiterflow candidate chunk through the canonical resume path.

This script replaces the earlier attachment-first Recruiterflow proof scripts.
It keeps the important behavior aligned with JobAdder:

- extract resume text from the embedded ZIP CV file
- run the same LLM-backed structured extraction layer
- persist scored results into the canonical `resume` document model
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from backend.db.connection import postgres_connection
from backend.services.recruiterflow_resume_extraction import (
    _extract_recruiterflow_file_id,
    extract_recruiterflow_candidate_resume_profile_with_quality_gate,
)
from backend.services.resume_extraction_persistence import (
    persist_scored_resume_extraction_result,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from backend.services.dropbox_api import download_dropbox_file
from scripts.persist_recruiterflow_initial_chunks import (
    DROPBOX_ACCOUNT_ID,
    RECRUITERFLOW_ZIP_PATH,
    _load_dropbox_connection,
)

DEFAULT_CANDIDATE_MEMBER_NAME = "candidate/1.100.json"
SUPPORTED_RESUME_SUFFIXES = (".pdf", ".docx", ".doc", ".rtf", ".txt")
DEFAULT_CANDIDATE_LIMIT = 10
DEFAULT_PERSISTED_RESUME_LIMIT = 10


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the Recruiterflow resume-chunk runner.
    """

    parser = argparse.ArgumentParser(
        description="Persist one Recruiterflow candidate chunk through the canonical resume path."
    )
    parser.add_argument(
        "--candidate-member",
        default=DEFAULT_CANDIDATE_MEMBER_NAME,
        help="ZIP member name for the candidate JSON chunk to import.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=DEFAULT_CANDIDATE_LIMIT,
        help="Maximum number of candidate rows to process from the chunk.",
    )
    parser.add_argument(
        "--persisted-resume-limit",
        "--accepted-resume-limit",
        dest="persisted_resume_limit",
        type=int,
        default=DEFAULT_PERSISTED_RESUME_LIMIT,
        help="Maximum number of scored resume ingests to persist in one run.",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Bypass the source-record skip check and reprocess already-ingested CVs.",
    )
    return parser.parse_args()


def build_artifact_path(candidate_member_name: str) -> Path:
    """
    Return the artifact path for one Recruiterflow resume-chunk run.
    """

    safe_name = candidate_member_name.replace("/", "_")
    return Path("temp") / f"recruiterflow_resume_{safe_name}_persisted.json"


def main() -> None:
    """
    Persist one Recruiterflow candidate chunk through canonical resume extraction.
    """

    args = parse_args()
    candidate_member_name = str(args.candidate_member)
    artifact_path = build_artifact_path(candidate_member_name)
    candidate_limit = max(1, int(args.candidate_limit))
    persisted_resume_limit = max(1, int(args.persisted_resume_limit))
    force_reprocess = bool(args.force_reprocess)

    stored_connection = _load_dropbox_connection(DROPBOX_ACCOUNT_ID)
    access_token = stored_connection["access_token"]
    assert isinstance(access_token, str)

    downloaded_zip = download_dropbox_file(
        access_token=access_token,
        path=RECRUITERFLOW_ZIP_PATH,
        timeout_seconds=240.0,
    )
    content_bytes = downloaded_zip["content_bytes"]
    assert isinstance(content_bytes, bytes)

    with ZipFile(BytesIO(content_bytes)) as archive:
        raw_candidate_records = json.loads(
            archive.read(candidate_member_name).decode("utf-8")
        )

        if not isinstance(raw_candidate_records, list):
            raise RuntimeError(
                "Recruiterflow candidate chunk did not contain a JSON list."
            )

        persisted_resumes: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []
        skipped_items: list[dict[str, Any]] = []
        status_counts = {
            "accepted": 0,
            "non_pass": 0,
            "unsupported": 0,
            "failed": 0,
            "skipped": 0,
            "no_resume_selected": 0,
            "selected_resume_candidate": 0,
        }

        for candidate_item in raw_candidate_records[:candidate_limit]:
            if not isinstance(candidate_item, dict):
                continue

            if (status_counts["accepted"] + status_counts["non_pass"]) >= persisted_resume_limit:
                break

            selected_file_item = _select_preferred_resume_file(
                candidate_item.get("files", [])
            )
            if selected_file_item is None:
                status_counts["no_resume_selected"] += 1
                continue

            status_counts["selected_resume_candidate"] += 1
            file_item = selected_file_item
            try:
                source_candidate_id = int(candidate_item["id"])
                file_name = str(file_item["filename"])
                source_file_id = _extract_recruiterflow_file_id(file_payload=file_item)
                extraction_source_record_key = _build_recruiterflow_extraction_source_record_key(
                    source_candidate_id=source_candidate_id,
                    source_file_id=source_file_id,
                )
                if not force_reprocess:
                    existing_skip_record = _find_existing_recruiterflow_resume_skip_record(
                        extraction_source_record_id=extraction_source_record_key,
                    )
                    if existing_skip_record is not None:
                        status_counts["skipped"] += 1
                        skipped_items.append(
                            {
                                "source_candidate_id": source_candidate_id,
                                "source_file_id": source_file_id,
                                "file_name": file_name,
                                "source_record_id": extraction_source_record_key,
                                "document_id": existing_skip_record.get("document_id"),
                                "document_title": existing_skip_record.get("document_title"),
                                "quality_status": existing_skip_record.get("quality_status"),
                                "quality_score": existing_skip_record.get("quality_score"),
                            }
                        )
                        continue

                embedded_member_name = _resolve_embedded_candidate_file_member(
                    archive=archive,
                    source_candidate_id=source_candidate_id,
                    file_name=file_name,
                )
                if embedded_member_name is None:
                    status_counts["failed"] += 1
                    failed_items.append(
                        {
                            "source_candidate_id": source_candidate_id,
                            "file_name": file_name,
                            "stage": "embedded_member_lookup",
                            "error_type": "EmbeddedMemberNotFound",
                            "message": "Embedded candidate CV member was not found in the ZIP export.",
                        }
                    )
                    continue

                embedded_bytes = archive.read(embedded_member_name)
                downloaded_file = {
                    "source_uri": f"{RECRUITERFLOW_ZIP_PATH}#{embedded_member_name}",
                    "file_name": file_name,
                    "content_type": None,
                    "content_bytes": embedded_bytes,
                    "byte_count": len(embedded_bytes),
                    "status_code": 200,
                }
                extracted_resume_text = extract_text_from_resume_bytes(
                    content_bytes=embedded_bytes,
                    file_name=file_name,
                    content_type=None,
                )
                result = extract_recruiterflow_candidate_resume_profile_with_quality_gate(
                    export_source_uri=RECRUITERFLOW_ZIP_PATH,
                    member_name=candidate_member_name,
                    candidate_payload=candidate_item,
                    file_payload=file_item,
                    downloaded_file=downloaded_file,
                    extracted_resume_text=extracted_resume_text,
                )
                persisted_summary = persist_scored_resume_extraction_result(result)
                persisted_resumes.append(
                    {
                        **persisted_summary,
                        "model_name": result.get("model_profile", {}).get(
                            "model_name"
                        ),
                        "quality_score": result.get(
                            "quality_assessment", {}
                        ).get("quality_score"),
                        "quality_gate": result.get("quality_gate"),
                    }
                )
                if result.get("quality_assessment", {}).get("status") == "pass":
                    status_counts["accepted"] += 1
                else:
                    status_counts["non_pass"] += 1
                if (status_counts["accepted"] + status_counts["non_pass"]) >= persisted_resume_limit:
                    break
            except ResumeTextExtractionError as exc:
                status_counts["unsupported"] += 1
                failed_items.append(
                    {
                        "source_candidate_id": source_candidate_id,
                        "file_name": file_name,
                        "stage": "resume_text_extraction",
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )
            except Exception as exc:
                status_counts["failed"] += 1
                failed_items.append(
                    {
                        "source_candidate_id": source_candidate_id,
                        "file_name": file_name,
                        "stage": "structured_resume_extraction_or_persistence",
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )

    summary = {
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "dropbox_account_id": DROPBOX_ACCOUNT_ID,
        "zip_path": RECRUITERFLOW_ZIP_PATH,
        "candidate_member_name": candidate_member_name,
        "candidate_limit": candidate_limit,
        "persisted_resume_limit": persisted_resume_limit,
        "force_reprocess": force_reprocess,
        "candidate_count": min(candidate_limit, len(raw_candidate_records)),
        "selected_resume_candidate_count": status_counts["selected_resume_candidate"],
        "no_resume_selected_count": status_counts["no_resume_selected"],
        "already_processed_count": status_counts["skipped"],
        "new_resume_candidate_count": (
            status_counts["selected_resume_candidate"] - status_counts["skipped"]
        ),
        "persisted_resume_count": status_counts["accepted"] + status_counts["non_pass"],
        "accepted_resume_count": status_counts["accepted"],
        "non_pass_count": status_counts["non_pass"],
        "skipped_count": status_counts["skipped"],
        "unsupported_count": status_counts["unsupported"],
        "failed_count": status_counts["failed"],
        "persisted_resume_preview": persisted_resumes[:10],
        "skipped_items_preview": skipped_items[:10],
        "failed_items_preview": failed_items[:10],
    }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"artifact: {artifact_path}")
    print(f"candidate member: {summary['candidate_member_name']}")
    print(f"candidate rows scanned: {summary['candidate_count']}")
    print(
        "resume-like candidates selected: "
        f"{summary['selected_resume_candidate_count']}"
    )
    print(
        "no resume selected: "
        f"{summary['no_resume_selected_count']}"
    )
    print(
        "already processed: "
        f"{summary['already_processed_count']}"
    )
    print(
        "new resume candidates: "
        f"{summary['new_resume_candidate_count']}"
    )
    print(f"persisted resumes: {summary['persisted_resume_count']}")
    print(f"pass resumes: {summary['accepted_resume_count']}")
    print(f"non-pass resumes: {summary['non_pass_count']}")
    print(f"skipped resumes: {summary['skipped_count']}")
    print(f"unsupported files: {summary['unsupported_count']}")
    print(f"failed files: {summary['failed_count']}")


def _select_preferred_resume_file(
    raw_files: Any,
) -> dict[str, Any] | None:
    """
    Return the single best Recruiterflow file to treat as the candidate CV.

    Parameters
    ----------
    raw_files : Any
        Raw `candidate.files` value from the Recruiterflow export.

    Returns
    -------
    dict[str, Any] | None
        One selected file payload, or `None` when nothing looks resume-like.

    Notes
    -----
    Recruiterflow exports can contain multiple candidate files. To keep the
    canonical flow aligned with the JobAdder path, this runner promotes only
    one file per candidate into the resume-extraction pipeline.
    """

    if not isinstance(raw_files, list):
        return None

    candidate_files = [
        item for item in raw_files if isinstance(item, dict) and _looks_like_resume_file(item)
    ]
    if not candidate_files:
        return None

    candidate_files.sort(key=_resume_file_sort_key, reverse=True)
    return candidate_files[0]


def _looks_like_resume_file(file_payload: dict[str, Any]) -> bool:
    """
    Return whether one Recruiterflow file is a reasonable CV candidate.
    """

    file_name = _clean_string(file_payload.get("filename")) or _clean_string(
        file_payload.get("name")
    )
    if file_name is None:
        return False

    lowered_name = file_name.lower()
    return lowered_name.endswith(SUPPORTED_RESUME_SUFFIXES)


def _resume_file_sort_key(file_payload: dict[str, Any]) -> tuple[int, int, str]:
    """
    Rank Recruiterflow files so the best CV candidate wins deterministically.
    """

    file_name = (
        _clean_string(file_payload.get("filename"))
        or _clean_string(file_payload.get("name"))
        or ""
    )
    lowered_name = file_name.lower()
    looks_explicitly_like_cv = int("cv" in lowered_name or "resume" in lowered_name)
    is_primary = int(bool(file_payload.get("is_primary")))
    upload_time = _clean_string(file_payload.get("upload_time")) or ""
    return (is_primary, looks_explicitly_like_cv, upload_time)


def _resolve_embedded_candidate_file_member(
    *,
    archive: ZipFile,
    source_candidate_id: int,
    file_name: str,
) -> str | None:
    """
    Return the embedded ZIP member for one selected Recruiterflow candidate CV.
    """

    normalized_target = file_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    preferred_prefix = f"candidate/files/{source_candidate_id}/".lower()
    matched_members: list[str] = []

    for member_name in archive.namelist():
        lowered_member_name = member_name.lower()
        if not lowered_member_name.startswith(preferred_prefix):
            continue
        if lowered_member_name.rsplit("/", 1)[-1] == normalized_target:
            matched_members.append(member_name)

    if not matched_members:
        return None

    matched_members.sort()
    return matched_members[0]


def _clean_string(value: Any) -> str | None:
    """
    Return a stripped string value, or `None` for blank-like input.
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    return cleaned_value or None


def _build_recruiterflow_extraction_source_record_key(
    *,
    source_candidate_id: int,
    source_file_id: int | None,
) -> str:
    """
    Return the canonical Recruiterflow resume-extraction source-record key.

    Parameters
    ----------
    source_candidate_id : int
        Recruiterflow candidate identifier.

    source_file_id : int | None
        Recruiterflow file identifier selected as the CV artefact.

    Returns
    -------
    str
        Stable extraction source-record key such as `4847:5679`.

    Raises
    ------
    RuntimeError
        If the selected file payload does not expose a usable upstream file ID.
    """

    if source_file_id is None:
        raise RuntimeError(
            "Recruiterflow resume extraction requires an upstream file ID to build the source-record key."
        )

    return f"{source_candidate_id}:{source_file_id}"


def _find_existing_recruiterflow_resume_skip_record(
    *,
    extraction_source_record_id: str,
) -> dict[str, Any] | None:
    """
    Return one existing Recruiterflow resume-extraction row that is safe to skip.

    Parameters
    ----------
    extraction_source_record_id : str
        Stable source-record key for the Recruiterflow candidate/file pair.

    Returns
    -------
    dict[str, Any] | None
        Existing scored resume record metadata, or `None` when the CV has not
        yet been persisted through the canonical path.

    Notes
    -----
    This is a deliberately narrow DB-backed skip rule:

    - same source-system candidate/file pair
    - same canonical resume extraction source-record type
    - only skip when a canonical resume document is already linked

    That keeps the runner from paying for duplicate text extraction and LLM
    work on unchanged static-export CVs.
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
        WHERE sr.source_system = 'recruiterflow'
          AND sr.source_record_type = 'recruiterflow_resume_extraction'
          AND sr.source_record_id = %(source_record_id)s
          AND d.document_type = 'resume'
        LIMIT 1
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"source_record_id": extraction_source_record_id},
            )
            row = cursor.fetchone()

    return dict(row) if row is not None else None


if __name__ == "__main__":
    main()
