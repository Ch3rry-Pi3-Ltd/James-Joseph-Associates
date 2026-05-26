"""
Download and extract a bounded batch of primary Recruiterflow candidate files.

This script extends the first Recruiterflow static-import slice from:

- entity snapshots
- file references

into the first byte-backed attachment content run.

It intentionally stays bounded:

- reads the same `candidate/1.100.json` chunk already inspected
- only processes files marked `is_primary = true`
- only processes the first small batch

That gives us a safe first pass for:

- reading real Recruiterflow candidate attachment bytes from the embedded ZIP
  export
- extracting text for supported PDF/DOCX files
- upgrading reference-only candidate documents into byte-backed rows
- surfacing extraction health in the review UI

Example
-------
Run the script with defaults:

    .\\.venv\\Scripts\\python.exe scripts\\persist_recruiterflow_primary_candidate_file_content.py

The script prints a short summary and writes a JSON artifact under `temp/`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from backend.services.recruiterflow_files import (
    RecruiterflowFileDownloadError,
    download_recruiterflow_file_reference,
)
from backend.services.recruiterflow_import import (
    persist_recruiterflow_candidate_file_content,
)
from backend.services.resume_text import (
    ResumeTextExtractionError,
    extract_text_from_resume_bytes,
)
from scripts.persist_recruiterflow_initial_chunks import (
    CANDIDATE_MEMBER_NAME,
    DROPBOX_ACCOUNT_ID,
    RECRUITERFLOW_ZIP_PATH,
    _load_dropbox_connection,
)
from backend.services.dropbox_api import download_dropbox_file

ARTIFACT_PATH = Path("temp") / "recruiterflow_primary_candidate_file_content_persisted.json"
MAX_PRIMARY_FILES = 25


def _is_primary_candidate_file(file_payload: dict[str, Any]) -> bool:
    """
    Return whether a Recruiterflow candidate file should enter the first batch.

    Example
    -------
    A nested file payload with:

        {"is_primary": true}

    returns `True`.
    """

    return file_payload.get("is_primary") is True


def _resolve_embedded_candidate_file_member(
    *,
    archive: ZipFile,
    source_candidate_id: int,
    file_name: str,
) -> str | None:
    """
    Return the embedded ZIP member name for one candidate attachment.

    Notes
    -----
    The Recruiterflow export stores real candidate files under:

    - `candidate/files/{candidate_id}/...`

    so the static importer should prefer that embedded content over the signed
    URLs in the JSON payload, which can expire before we import the backup.

    Example
    -------
    A candidate `4847` with file name
    `Bernardita Gutierrez CV EN 03-2026.pdf` resolves to:

        candidate/files/4847/Bernardita Gutierrez CV EN 03-2026.pdf
    """

    prefix = f"candidate/files/{source_candidate_id}/"
    member_names = [
        info.filename
        for info in archive.infolist()
        if info.filename.startswith(prefix) and not info.is_dir()
    ]
    if not member_names:
        return None

    exact_match = f"{prefix}{file_name}"
    if exact_match in member_names:
        return exact_match

    if len(member_names) == 1:
        return member_names[0]

    return None


def main() -> None:
    """
    Persist the first bounded batch of primary Recruiterflow candidate files.

    Example
    -------
    A successful run prints counts such as:

        selected primary files: 25
        extracted successfully: 18
        unsupported files: 4
        failed files: 3
    """

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
            archive.read(CANDIDATE_MEMBER_NAME).decode("utf-8")
        )

        if not isinstance(raw_candidate_records, list):
            raise RuntimeError(
                "Recruiterflow candidate chunk did not contain a JSON list."
            )

        selected_primary_files: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for candidate_item in raw_candidate_records:
            if not isinstance(candidate_item, dict):
                continue

            # Keep selection candidate-by-candidate so the later persistence
            # result can still be read in the same business context the export
            # gave us.
            for file_item in candidate_item.get("files", []):
                if not isinstance(file_item, dict):
                    continue
                if not _is_primary_candidate_file(file_item):
                    continue

                selected_primary_files.append((candidate_item, file_item))
                if len(selected_primary_files) >= MAX_PRIMARY_FILES:
                    break

            if len(selected_primary_files) >= MAX_PRIMARY_FILES:
                break

        persisted_results: list[dict[str, Any]] = []
        status_counts = {
            "extracted": 0,
            "unsupported": 0,
            "failed": 0,
        }

        for candidate_item, file_item in selected_primary_files:
            downloaded_file: dict[str, Any] | None = None
            extraction_result: dict[str, Any] | None = None
            extraction_error: ResumeTextExtractionError | None = None
            download_error_message: str | None = None

            source_candidate_id = int(candidate_item["id"])
            file_name = str(file_item["filename"])
            embedded_member_name = _resolve_embedded_candidate_file_member(
                archive=archive,
                source_candidate_id=source_candidate_id,
                file_name=file_name,
            )

            try:
                if embedded_member_name is not None:
                    embedded_bytes = archive.read(embedded_member_name)
                    downloaded_file = {
                        "source_uri": f"{RECRUITERFLOW_ZIP_PATH}#{embedded_member_name}",
                        "file_name": file_name,
                        "content_type": None,
                        "content_bytes": embedded_bytes,
                        "byte_count": len(embedded_bytes),
                        "status_code": 200,
                    }
                else:
                    source_uri = file_item.get("link")
                    if not isinstance(source_uri, str) or source_uri.strip() == "":
                        download_error_message = (
                            "Recruiterflow candidate file is missing both an embedded "
                            "ZIP member and a signed download link."
                        )
                    else:
                        downloaded_file = download_recruiterflow_file_reference(
                            source_uri=source_uri,
                            timeout_seconds=120.0,
                        )

                if downloaded_file is not None:
                    extraction_result = extract_text_from_resume_bytes(
                        content_bytes=downloaded_file["content_bytes"],
                        file_name=downloaded_file.get("file_name"),
                        content_type=downloaded_file.get("content_type"),
                    )
            except RecruiterflowFileDownloadError as exc:
                download_error_message = str(exc)
            except ResumeTextExtractionError as exc:
                extraction_error = exc

            persisted_summary = persist_recruiterflow_candidate_file_content(
                export_source_uri=RECRUITERFLOW_ZIP_PATH,
                member_name=CANDIDATE_MEMBER_NAME,
                candidate_payload=candidate_item,
                file_payload=file_item,
                downloaded_file=downloaded_file,
                extraction_result=extraction_result,
                extraction_error=extraction_error,
                download_error_message=download_error_message,
            )
            persisted_results.append(persisted_summary)

            sync_status = persisted_summary.get("sync_status")
            if sync_status in status_counts:
                status_counts[sync_status] += 1

    summary = {
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "dropbox_account_id": DROPBOX_ACCOUNT_ID,
        "zip_path": RECRUITERFLOW_ZIP_PATH,
        "candidate_member_name": CANDIDATE_MEMBER_NAME,
        "selected_primary_file_count": len(selected_primary_files),
        "extracted_count": status_counts["extracted"],
        "unsupported_count": status_counts["unsupported"],
        "failed_count": status_counts["failed"],
        "results_preview": persisted_results[:10],
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"artifact: {ARTIFACT_PATH}")
    print(f"selected primary files: {summary['selected_primary_file_count']}")
    print(f"extracted successfully: {summary['extracted_count']}")
    print(f"unsupported files: {summary['unsupported_count']}")
    print(f"failed files: {summary['failed_count']}")


if __name__ == "__main__":
    main()
