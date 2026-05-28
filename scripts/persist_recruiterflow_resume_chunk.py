"""
Persist one Recruiterflow candidate chunk through the canonical resume path.

This script replaces the earlier attachment-first Recruiterflow proof scripts.
It keeps the important behavior aligned with JobAdder:

- extract resume text from the embedded ZIP CV file
- run the same LLM-backed structured extraction layer
- persist only accepted results into the canonical `resume` document model
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from backend.services.recruiterflow_resume_extraction import (
    extract_recruiterflow_candidate_resume_profile_with_quality_gate,
)
from backend.services.resume_extraction_persistence import (
    persist_accepted_resume_extraction_result,
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
DEFAULT_ACCEPTED_RESUME_LIMIT = 10


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
        "--accepted-resume-limit",
        type=int,
        default=DEFAULT_ACCEPTED_RESUME_LIMIT,
        help="Maximum number of accepted resume ingests to persist in one run.",
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
    accepted_resume_limit = max(1, int(args.accepted_resume_limit))

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
        status_counts = {"accepted": 0, "non_pass": 0, "unsupported": 0, "failed": 0}

        for candidate_item in raw_candidate_records[:candidate_limit]:
            if not isinstance(candidate_item, dict):
                continue

            if status_counts["accepted"] >= accepted_resume_limit:
                break

            selected_file_item = _select_preferred_resume_file(
                candidate_item.get("files", [])
            )
            if selected_file_item is None:
                continue

            file_item = selected_file_item
            try:
                source_candidate_id = int(candidate_item["id"])
                file_name = str(file_item["filename"])
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
                if result.get("quality_assessment", {}).get("status") == "pass":
                    persisted_summary = persist_accepted_resume_extraction_result(
                        result
                    )
                    persisted_resumes.append(persisted_summary)
                    status_counts["accepted"] += 1
                    if status_counts["accepted"] >= accepted_resume_limit:
                        break
                else:
                    status_counts["non_pass"] += 1
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
        "accepted_resume_limit": accepted_resume_limit,
        "candidate_count": min(candidate_limit, len(raw_candidate_records)),
        "accepted_resume_count": status_counts["accepted"],
        "non_pass_count": status_counts["non_pass"],
        "unsupported_count": status_counts["unsupported"],
        "failed_count": status_counts["failed"],
        "persisted_resume_preview": persisted_resumes[:10],
        "failed_items_preview": failed_items[:10],
    }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"artifact: {artifact_path}")
    print(f"candidate member: {summary['candidate_member_name']}")
    print(f"candidate rows scanned: {summary['candidate_count']}")
    print(f"accepted resumes: {summary['accepted_resume_count']}")
    print(f"non-pass resumes: {summary['non_pass_count']}")
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


if __name__ == "__main__":
    main()
