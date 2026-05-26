"""
Persist the first bounded Recruiterflow candidate and job file references.

This script extends the first Recruiterflow static-import slice by taking the
same narrow JSON chunks already used for jobs/candidates and persisting their
nested file metadata as canonical document references.

It intentionally does not download the actual Recruiterflow file bytes yet.
The goal of this step is narrower:

- make the document layer visible in Supabase
- preserve file provenance cleanly
- link candidate and job attachments back to canonical entities
- keep the first attachment slice bounded to the same inspected chunks

Example
-------
Run the script with defaults:

    .\\.venv\\Scripts\\python.exe scripts\\persist_recruiterflow_initial_file_references.py

The script prints a short summary and writes a JSON artifact under `temp/`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from backend.services.recruiterflow_import import (
    persist_recruiterflow_candidate_file_reference,
    persist_recruiterflow_job_file_reference,
)
from scripts.persist_recruiterflow_initial_chunks import (
    CANDIDATE_MEMBER_NAME,
    DROPBOX_ACCOUNT_ID,
    JOB_MEMBER_NAME,
    RECRUITERFLOW_ZIP_PATH,
    _load_dropbox_connection,
)
from backend.services.dropbox_api import download_dropbox_file

ARTIFACT_PATH = Path("temp") / "recruiterflow_initial_file_references_persisted.json"


def main() -> None:
    """
    Persist the first bounded Recruiterflow candidate and job file references.

    Example
    -------
    A successful run prints counts such as:

        persisted candidate file references: 42
        persisted job file references: 11
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
        raw_job_records = json.loads(archive.read(JOB_MEMBER_NAME).decode("utf-8"))
        raw_candidate_records = json.loads(
            archive.read(CANDIDATE_MEMBER_NAME).decode("utf-8")
        )

    if not isinstance(raw_job_records, list) or not isinstance(
        raw_candidate_records, list
    ):
        raise RuntimeError("Recruiterflow chunk members did not contain JSON lists.")

    persisted_job_file_references: list[dict[str, Any]] = []
    for job_item in raw_job_records:
        if not isinstance(job_item, dict):
            continue

        # Persist each nested file separately so every reference keeps its own
        # provenance row and can later be upgraded to a byte-backed document
        # without losing where it came from inside the Recruiterflow export.
        for file_item in job_item.get("files", []):
            if not isinstance(file_item, dict):
                continue
            persisted_job_file_references.append(
                persist_recruiterflow_job_file_reference(
                    export_source_uri=RECRUITERFLOW_ZIP_PATH,
                    member_name=JOB_MEMBER_NAME,
                    job_payload=job_item,
                    file_payload=file_item,
                )
            )

    persisted_candidate_file_references: list[dict[str, Any]] = []
    for candidate_item in raw_candidate_records:
        if not isinstance(candidate_item, dict):
            continue

        # Keep the attachment handling candidate-by-candidate rather than
        # flattening the whole chunk first. That makes failures easier to
        # reason about because the candidate context stays attached to each
        # nested file reference throughout the run.
        for file_item in candidate_item.get("files", []):
            if not isinstance(file_item, dict):
                continue
            persisted_candidate_file_references.append(
                persist_recruiterflow_candidate_file_reference(
                    export_source_uri=RECRUITERFLOW_ZIP_PATH,
                    member_name=CANDIDATE_MEMBER_NAME,
                    candidate_payload=candidate_item,
                    file_payload=file_item,
                )
            )

    summary = {
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "dropbox_account_id": DROPBOX_ACCOUNT_ID,
        "zip_path": RECRUITERFLOW_ZIP_PATH,
        "job_member_name": JOB_MEMBER_NAME,
        "candidate_member_name": CANDIDATE_MEMBER_NAME,
        "job_file_reference_count": len(persisted_job_file_references),
        "candidate_file_reference_count": len(persisted_candidate_file_references),
        "job_file_reference_preview": persisted_job_file_references[:3],
        "candidate_file_reference_preview": persisted_candidate_file_references[:3],
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"artifact: {ARTIFACT_PATH}")
    print(
        "persisted job file references: "
        f"{summary['job_file_reference_count']}"
    )
    print(
        "persisted candidate file references: "
        f"{summary['candidate_file_reference_count']}"
    )


if __name__ == "__main__":
    main()
