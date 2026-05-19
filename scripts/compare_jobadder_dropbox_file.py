"""
Compare one JobAdder candidate attachment against one Dropbox file.

Why this script exists
----------------------
We have already established that for `tw398`:

- JobAdder applications hold the vacancy/application context
- JobAdder candidate records hold the structured CV attachments
- Dropbox holds job specs, advert-response `.eml` archives, and duplicate CV
  files

The next concrete question is narrower:

    "Is a Dropbox CV copy byte-identical to the corresponding JobAdder
    candidate attachment, or is Dropbox holding a different file version?"

This script answers that question for one chosen pair.

What this script does
---------------------
For one supplied JobAdder candidate attachment and one Dropbox path, it:

1. calls the live backend JobAdder `download-proof` route
2. downloads the Dropbox file transiently through the local helper
3. computes the Dropbox SHA-256 hash locally
4. compares:
   - file name
   - byte count
   - SHA-256 hash
5. optionally writes a JSON report

What this script does not do
----------------------------
It does not:

- persist either file locally
- write anything to Supabase
- decide long-term source-of-truth rules by itself

Example
-------
Compare the `sanjeev sadha.docx` JobAdder attachment against the Dropbox copy:

    uv run python scripts/compare_jobadder_dropbox_file.py ^
        --jobadder-account 2236 ^
        --candidate-id 17071060 ^
        --attachment-id 21562882 ^
        --dropbox-account-id "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0" ^
        --dropbox-path "/#################----CV's- IN-JAD-JobAdder/sanjeev sadha.docx" ^
        --output-json temp\\jobadder_dropbox_compare_sanjeev.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.dropbox_oauth import get_dropbox_oauth_connection
from backend.services.dropbox_api import download_dropbox_file
from backend.services.dropbox_oauth import (
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.settings import get_settings

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for JobAdder vs Dropbox file comparison.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for one cross-source file comparison run.

    Example
    -------
    A typical operator invocation looks like:

        --jobadder-account 2236 --candidate-id 17071060 --attachment-id 21562882
    """

    parser = argparse.ArgumentParser(
        description=(
            "Compare one JobAdder candidate attachment against one Dropbox file "
            "using file metadata and SHA-256 hashes."
        )
    )
    parser.add_argument("--jobadder-account", type=int, required=True)
    parser.add_argument("--candidate-id", type=int, required=True)
    parser.add_argument("--attachment-id", type=int, required=True)
    parser.add_argument("--dropbox-account-id", required=True)
    parser.add_argument("--dropbox-path", required=True)
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for the live backend that exposes the JobAdder proof route.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final comparison report.",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate the high-signal local arguments before any provider calls start.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments for the current run.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - non-positive JobAdder identifiers
    - a blank Dropbox account ID
    - a blank Dropbox path
    - missing local Dropbox OAuth settings
    """

    if args.jobadder_account < 1:
        raise RuntimeError("JOBADDER_ACCOUNT must be at least 1.")
    if args.candidate_id < 1:
        raise RuntimeError("CANDIDATE_ID must be at least 1.")
    if args.attachment_id < 1:
        raise RuntimeError("ATTACHMENT_ID must be at least 1.")
    if not isinstance(args.dropbox_account_id, str) or args.dropbox_account_id.strip() == "":
        raise RuntimeError("DROPBOX_ACCOUNT_ID must be a non-empty string.")
    if not isinstance(args.dropbox_path, str) or args.dropbox_path.strip() == "":
        raise RuntimeError("DROPBOX_PATH must be a non-empty string.")
    if not isinstance(args.api_base_url, str) or args.api_base_url.strip() == "":
        raise RuntimeError("API_BASE_URL must be a non-empty string.")

    settings = get_settings()
    missing_settings: list[str] = []
    if settings.dropbox_client_id.strip() == "":
        missing_settings.append("DROPBOX_CLIENT_ID")
    if settings.dropbox_client_secret.strip() == "":
        missing_settings.append("DROPBOX_CLIENT_SECRET")
    if settings.dropbox_redirect_uri.strip() == "":
        missing_settings.append("DROPBOX_REDIRECT_URI")

    if missing_settings:
        raise RuntimeError(
            "Missing Dropbox OAuth settings: " + ", ".join(missing_settings)
        )


def load_ready_dropbox_connection(*, dropbox_account_id: str) -> dict[str, Any]:
    """
    Load the stored Dropbox connection and refresh it if it is already expired.

    Parameters
    ----------
    dropbox_account_id : str
        Dropbox account identifier used to fetch the stored OAuth connection.

    Returns
    -------
    dict[str, Any]
        Stored Dropbox OAuth connection row containing a usable access token.
    """

    stored_connection = get_dropbox_oauth_connection(dropbox_account_id)

    if stored_connection is None:
        raise RuntimeError("Stored Dropbox connection was not found.")

    raw_access_token = stored_connection.get("access_token")
    raw_refresh_token = stored_connection.get("refresh_token")
    raw_scope = stored_connection.get("scope")
    raw_obtained_at = stored_connection.get("obtained_at")
    raw_expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(raw_access_token, str) or raw_access_token.strip() == "":
        raise RuntimeError("The stored Dropbox connection is missing an access token.")

    # Keep the Dropbox side resilient locally even though the JobAdder side is
    # coming through the live backend route. That way the comparison script is
    # only as brittle as the side that actually requires live secret-backed
    # refresh behavior.
    if is_dropbox_access_token_expired(
        obtained_at=raw_obtained_at,
        expires_in_seconds=raw_expires_in_seconds,
    ):
        if not isinstance(raw_refresh_token, str) or raw_refresh_token.strip() == "":
            raise RuntimeError(
                "The stored Dropbox connection is missing a refresh token."
            )

        refreshed_token_set = refresh_dropbox_access_token(
            refresh_token=raw_refresh_token,
        )

        refreshed_access_token = refreshed_token_set.access_token
        merged_scope = (
            refreshed_token_set.scope
            if isinstance(refreshed_token_set.scope, str)
            and refreshed_token_set.scope.strip() != ""
            else (
                raw_scope
                if isinstance(raw_scope, str) and raw_scope.strip() != ""
                else None
            )
        )

        stored_connection = dict(stored_connection)
        stored_connection["access_token"] = refreshed_access_token
        stored_connection["scope"] = merged_scope

    return stored_connection


def fetch_jobadder_download_proof(
    *,
    api_base_url: str,
    jobadder_account: int,
    candidate_id: int,
    attachment_id: int,
) -> dict[str, Any]:
    """
    Fetch one JobAdder attachment download-proof wrapper from the live backend.

    Parameters
    ----------
    api_base_url : str
        Base URL for the deployed backend.

    jobadder_account : int
        JobAdder account identifier used in the route path.

    candidate_id : int
        Candidate identifier used in the route path.

    attachment_id : int
        Attachment identifier used in the route path.

    Returns
    -------
    dict[str, Any]
        Decoded JSON proof payload returned by the backend.

    Example
    -------
    A successful payload looks like:

        {
            "candidate_id": 17071060,
            "attachment_id": 21562882,
            "file_name": "sanjeev sadha.docx",
            "byte_count": 18931,
            "sha256": "...",
        }
    """

    # Keep the JobAdder side on the deployed backend because that runtime
    # already has the working Production OAuth configuration. This avoids
    # relying on locally pulled secret files, which are intentionally not a
    # trustworthy reflection of sensitive Vercel env values.
    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}"
        f"/candidates/{candidate_id}/attachments/{attachment_id}/download-proof"
    )
    request_url = api_base_url.rstrip("/") + route_path

    try:
        response = httpx.get(request_url, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError("Could not reach the live backend proof route.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("The live backend proof route did not return JSON.") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"JobAdder download-proof route failed: status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError("The live backend proof route did not return an object.")

    return payload


def build_dropbox_file_proof(
    *,
    access_token: str,
    path: str,
) -> dict[str, Any]:
    """
    Download one Dropbox file transiently and compute comparison metadata.

    Parameters
    ----------
    access_token : str
        Ready-to-use Dropbox access token.

    path : str
        Full Dropbox file path to compare.

    Returns
    -------
    dict[str, Any]
        Metadata and SHA-256 hash for the Dropbox file.

    Example
    -------
    A successful proof looks like:

        {
            "path": "/archive/example.docx",
            "file_name": "example.docx",
            "byte_count": 18931,
            "sha256": "...",
        }
    """

    downloaded_file = download_dropbox_file(
        access_token=access_token,
        path=path,
    )
    content_bytes = downloaded_file["content_bytes"]

    return {
        "path": path,
        "file_name": downloaded_file.get("file_name"),
        "content_type": downloaded_file.get("content_type"),
        "content_length": downloaded_file.get("file_metadata", {}).get("size"),
        "byte_count": len(content_bytes),
        "sha256": hashlib.sha256(content_bytes).hexdigest(),
        "file_metadata": downloaded_file.get("file_metadata"),
    }


def compare_proofs(
    *,
    jobadder_proof: dict[str, Any],
    dropbox_proof: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare the two source proofs and summarize the match status.

    Parameters
    ----------
    jobadder_proof : dict[str, Any]
        Proof metadata returned by the live JobAdder route.

    dropbox_proof : dict[str, Any]
        Proof metadata computed locally for the Dropbox file.

    Returns
    -------
    dict[str, Any]
        High-signal comparison summary.

    Notes
    -----
    This helper answers one narrow operational question:

    - are the two sources holding the same file?

    It therefore compares only the fields that matter for that decision:

    - file name
    - byte count
    - SHA-256 hash
    """

    jobadder_file_name = jobadder_proof.get("file_name")
    dropbox_file_name = dropbox_proof.get("file_name")
    jobadder_byte_count = jobadder_proof.get("byte_count")
    dropbox_byte_count = dropbox_proof.get("byte_count")
    jobadder_sha256 = jobadder_proof.get("sha256")
    dropbox_sha256 = dropbox_proof.get("sha256")

    return {
        "file_name_match": jobadder_file_name == dropbox_file_name,
        "byte_count_match": jobadder_byte_count == dropbox_byte_count,
        "sha256_match": jobadder_sha256 == dropbox_sha256,
        "jobadder_file_name": jobadder_file_name,
        "dropbox_file_name": dropbox_file_name,
        "jobadder_byte_count": jobadder_byte_count,
        "dropbox_byte_count": dropbox_byte_count,
        "jobadder_sha256": jobadder_sha256,
        "dropbox_sha256": dropbox_sha256,
    }


def main() -> int:
    """
    Run the one-file JobAdder vs Dropbox comparison.

    Returns
    -------
    int
        Process exit code.

    Example
    -------
    Running:

        uv run python scripts/compare_jobadder_dropbox_file.py ^
            --jobadder-account 2236 ^
            --candidate-id 17071060 ^
            --attachment-id 21562882 ^
            --dropbox-account-id "dbid:AAExample" ^
            --dropbox-path "/mirror/example.docx"

    prints a compact comparison and optionally writes the full JSON report.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    jobadder_proof = fetch_jobadder_download_proof(
        api_base_url=args.api_base_url,
        jobadder_account=args.jobadder_account,
        candidate_id=args.candidate_id,
        attachment_id=args.attachment_id,
    )

    dropbox_connection = load_ready_dropbox_connection(
        dropbox_account_id=args.dropbox_account_id
    )
    dropbox_access_token = dropbox_connection["access_token"]
    assert isinstance(dropbox_access_token, str)

    dropbox_proof = build_dropbox_file_proof(
        access_token=dropbox_access_token,
        path=args.dropbox_path,
    )

    comparison = compare_proofs(
        jobadder_proof=jobadder_proof,
        dropbox_proof=dropbox_proof,
    )

    report = {
        "jobadder_proof": jobadder_proof,
        "dropbox_proof": dropbox_proof,
        "comparison": comparison,
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

    print("JobAdder vs Dropbox file comparison completed.\n")
    print(f"JobAdder file: {comparison['jobadder_file_name']}")
    print(f"Dropbox file: {comparison['dropbox_file_name']}")
    print(f"File name match: {comparison['file_name_match']}")
    print(f"Byte count match: {comparison['byte_count_match']}")
    print(f"SHA-256 match: {comparison['sha256_match']}")
    print(f"JobAdder SHA-256: {comparison['jobadder_sha256']}")
    print(f"Dropbox SHA-256: {comparison['dropbox_sha256']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
