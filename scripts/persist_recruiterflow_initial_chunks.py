"""
Persist the first bounded Recruiterflow job and candidate chunks from Dropbox.

This script is the first narrow static-import runner for the Recruiterflow
backup ZIP in Tom's Dropbox. It intentionally imports only:

- `job/1.134.json`
- `candidate/1.100.json`

That keeps the first write slice bounded while still proving the real export
shape can land in the canonical Supabase schema.

Example
-------
Run the script with defaults:

    .\\.venv\\Scripts\\python.exe scripts\\persist_recruiterflow_initial_chunks.py

The script prints a short summary and writes a JSON artifact under `temp/`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from backend.db.dropbox_oauth import (
    get_dropbox_oauth_connection,
    save_dropbox_oauth_connection,
)
from backend.services.dropbox_api import download_dropbox_file
from backend.services.dropbox_oauth import (
    DropboxTokenSet,
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.recruiterflow_import import (
    persist_recruiterflow_candidate,
    persist_recruiterflow_job,
)

DROPBOX_ACCOUNT_ID = "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0"
RECRUITERFLOW_ZIP_PATH = (
    "/+++ RFL - Recruiterflow DATA backup downloaded 19.05.26/"
    "James Joseph Associates.b0ac635f.zip"
)
JOB_MEMBER_NAME = "job/1.134.json"
CANDIDATE_MEMBER_NAME = "candidate/1.100.json"
ARTIFACT_PATH = (
    Path("temp")
    / "recruiterflow_initial_chunks_persisted.json"
)


def _load_dropbox_connection(dropbox_account_id: str) -> dict[str, Any]:
    """
    Return one Dropbox OAuth connection row that is safe to use for reads.

    Example
    -------
    A stored Dropbox connection may need a token refresh before the ZIP can be
    downloaded. This helper performs that check and persists the refreshed row
    when necessary.
    """

    stored_connection = get_dropbox_oauth_connection(dropbox_account_id)
    if stored_connection is None:
        raise RuntimeError(
            f"Stored Dropbox OAuth connection was not found for {dropbox_account_id}."
        )

    access_token = stored_connection.get("access_token")
    refresh_token = stored_connection.get("refresh_token")
    obtained_at = stored_connection.get("obtained_at")
    expires_in_seconds = stored_connection.get("expires_in_seconds")

    if (
        not isinstance(access_token, str)
        or access_token.strip() == ""
        or not isinstance(refresh_token, str)
        or refresh_token.strip() == ""
    ):
        raise RuntimeError("Stored Dropbox connection is missing required tokens.")

    if not is_dropbox_access_token_expired(
        obtained_at=obtained_at,
        expires_in_seconds=expires_in_seconds,
    ):
        return stored_connection

    refreshed_token_set = refresh_dropbox_access_token(refresh_token=refresh_token)
    merged_token_set = DropboxTokenSet(
        access_token=refreshed_token_set.access_token,
        token_type=refreshed_token_set.token_type,
        expires_in=refreshed_token_set.expires_in,
        refresh_token=refreshed_token_set.refresh_token or refresh_token,
        scope=refreshed_token_set.scope or stored_connection.get("scope"),
        account_id=refreshed_token_set.account_id or dropbox_account_id,
        raw_payload={
            **stored_connection,
            **refreshed_token_set.raw_payload,
        },
    )
    save_dropbox_oauth_connection(merged_token_set)
    refreshed_connection = get_dropbox_oauth_connection(dropbox_account_id)
    if refreshed_connection is None:
        raise RuntimeError("Dropbox connection refresh succeeded but was not saved.")
    return refreshed_connection

def main() -> None:
    """
    Persist the first bounded Recruiterflow job and candidate chunks.

    Example
    -------
    A successful run prints counts such as:

        persisted jobs: 134
        persisted candidates: 100
        resolved applications: 42
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

    if not isinstance(raw_job_records, list) or not isinstance(raw_candidate_records, list):
        raise RuntimeError("Recruiterflow chunk members did not contain JSON lists.")

    persisted_jobs: list[dict[str, Any]] = []
    for job_item in raw_job_records:
        if not isinstance(job_item, dict):
            continue
        persisted_jobs.append(
            persist_recruiterflow_job(
                export_source_uri=RECRUITERFLOW_ZIP_PATH,
                member_name=JOB_MEMBER_NAME,
                job_payload=job_item,
            )
        )

    persisted_candidates: list[dict[str, Any]] = []
    for candidate_item in raw_candidate_records:
        if not isinstance(candidate_item, dict):
            continue
        persisted_candidates.append(
            persist_recruiterflow_candidate(
                export_source_uri=RECRUITERFLOW_ZIP_PATH,
                member_name=CANDIDATE_MEMBER_NAME,
                candidate_payload=candidate_item,
            )
        )

    summary = {
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "dropbox_account_id": DROPBOX_ACCOUNT_ID,
        "zip_path": RECRUITERFLOW_ZIP_PATH,
        "job_member_name": JOB_MEMBER_NAME,
        "candidate_member_name": CANDIDATE_MEMBER_NAME,
        "job_count": len(persisted_jobs),
        "candidate_count": len(persisted_candidates),
        "resolved_application_count": sum(
            item.get("resolved_application_count", 0)
            for item in persisted_candidates
            if isinstance(item.get("resolved_application_count", 0), int)
        ),
        "unresolved_job_link_count": sum(
            item.get("unresolved_job_link_count", 0)
            for item in persisted_candidates
            if isinstance(item.get("unresolved_job_link_count", 0), int)
        ),
        "job_results_preview": persisted_jobs[:3],
        "candidate_results_preview": persisted_candidates[:3],
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"artifact: {ARTIFACT_PATH}")
    print(f"persisted jobs: {summary['job_count']}")
    print(f"persisted candidates: {summary['candidate_count']}")
    print(f"resolved applications: {summary['resolved_application_count']}")
    print(f"unresolved job links: {summary['unresolved_job_link_count']}")


if __name__ == "__main__":
    main()
