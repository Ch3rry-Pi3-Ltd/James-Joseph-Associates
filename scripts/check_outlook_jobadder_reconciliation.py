"""
Check whether one Outlook advert-response attachment matches a JobAdder candidate CV.

Why this script exists
----------------------
The first narrow Outlook ingestion slice for `tw394` is now real:

- one advert-response message attachment has been persisted
- the attachment is linked to the canonical `tw394` job
- the `tw...` vacancy bridge is working

The next question is narrower:

    "Can we safely reconcile this Outlook CV to one canonical JobAdder
    candidate/application using strong evidence rather than guesswork?"

This script answers that question conservatively.

What this script does
---------------------
For one Outlook attachment and one JobAdder job, it:

1. fetches a stable Outlook attachment proof from the live backend
2. fetches the applications for one specific JobAdder job through the live backend
3. walks the candidate attachments for those applications
4. fetches candidate-attachment proof metadata transiently
5. compares file hashes against the Outlook attachment hash
6. reports either:
   - an exact match
   - or an unresolved result

What this script does not do
----------------------------
It does not:

- create or update canonical candidate/person links
- attempt fuzzy name matching
- treat a filename match as sufficient evidence
- write anything to Supabase

Examples
--------
Run the current `tw394` reconciliation check:

    uv run python scripts/check_outlook_jobadder_reconciliation.py ^
        --output-json temp\\outlook_tw394_reconciliation_check.json

Target another job and Outlook attachment explicitly:

    uv run python scripts/check_outlook_jobadder_reconciliation.py ^
        --job-id 891841 ^
        --message-id "AAMk..." ^
        --attachment-id "AAMk...AAABEgAQ..." ^
        --output-json temp\\custom_reconciliation_check.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"
DEFAULT_MICROSOFT_USER_ID = "b4dd6a5f-8e27-4745-9369-e117121382ed"
DEFAULT_JOBADDER_ACCOUNT = 2236
DEFAULT_JOB_ID = 891841
DEFAULT_MESSAGE_ID = (
    "AAMkADBmM2ZjNmZjLTk0ZGQtNGI4Zi1iNjAyLTI5NDVjZDQxYzViZQBGAAAAAAC9M3xhcHUTSbyhEjXYWMWOBwCj0_Pmn_tuQIBroX6zsYZkAAfPRw74AACj0_Pmn_tuQIBroX6zsYZkAAfv1vQyAAA="
)
DEFAULT_ATTACHMENT_ID = (
    "AAMkADBmM2ZjNmZjLTk0ZGQtNGI4Zi1iNjAyLTI5NDVjZDQxYzViZQBGAAAAAAC9M3xhcHUTSbyhEjXYWMWOBwCj0_Pmn_tuQIBroX6zsYZkAAfPRw74AACj0_Pmn_tuQIBroX6zsYZkAAfv1vQyAAABEgAQAGWkHMiI7ixOvmfILATNIU0="
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the Outlook-vs-JobAdder reconciliation check.

    Example
    -------
    A typical operator invocation looks like:

        --job-id 891841 --output-json temp\\outlook_tw394_reconciliation_check.json
    """

    parser = argparse.ArgumentParser(
        description=(
            "Check whether one Outlook advert-response attachment matches a "
            "JobAdder candidate attachment for one specific job."
        )
    )
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--microsoft-user-id", default=DEFAULT_MICROSOFT_USER_ID)
    parser.add_argument("--mailbox", default=None)
    parser.add_argument("--message-id", default=DEFAULT_MESSAGE_ID)
    parser.add_argument("--attachment-id", default=DEFAULT_ATTACHMENT_ID)
    parser.add_argument("--jobadder-account", type=int, default=DEFAULT_JOBADDER_ACCOUNT)
    parser.add_argument("--job-id", type=int, default=DEFAULT_JOB_ID)
    parser.add_argument(
        "--application-limit",
        type=int,
        default=100,
        help="Maximum number of job applications to inspect in one run.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path for the final reconciliation report.",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate the high-signal local arguments before any provider calls start.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - a blank Outlook message ID
    - a non-positive JobAdder job ID
    """

    if not isinstance(args.api_base_url, str) or args.api_base_url.strip() == "":
        raise RuntimeError("API_BASE_URL must be a non-empty string.")
    if (
        not isinstance(args.microsoft_user_id, str)
        or args.microsoft_user_id.strip() == ""
    ):
        raise RuntimeError("MICROSOFT_USER_ID must be a non-empty string.")
    if not isinstance(args.message_id, str) or args.message_id.strip() == "":
        raise RuntimeError("MESSAGE_ID must be a non-empty string.")
    if not isinstance(args.attachment_id, str) or args.attachment_id.strip() == "":
        raise RuntimeError("ATTACHMENT_ID must be a non-empty string.")
    if args.jobadder_account < 1:
        raise RuntimeError("JOBADDER_ACCOUNT must be at least 1.")
    if args.job_id < 1:
        raise RuntimeError("JOB_ID must be at least 1.")
    if args.application_limit < 1:
        raise RuntimeError("APPLICATION_LIMIT must be at least 1.")


def fetch_outlook_attachment_proof(
    *,
    api_base_url: str,
    microsoft_user_id: str,
    mailbox: str | None,
    message_id: str,
    attachment_id: str,
) -> dict[str, Any]:
    """
    Fetch one Outlook attachment proof payload from the live backend.

    Example
    -------
    A successful payload looks like:

        {
            "file_name": "SULAIMAN MOHAMMED (... - Totaljobs).pdf",
            "byte_count": 326601,
            "sha256": "...",
        }
    """

    route_path = (
        f"/api/v1/integrations/outlook/accounts/{microsoft_user_id}"
        f"/messages/{message_id}/attachments/{attachment_id}/download-proof"
    )
    request_url = api_base_url.rstrip("/") + route_path
    params: dict[str, Any] | None = None

    if isinstance(mailbox, str) and mailbox.strip() != "":
        params = {"mailbox": mailbox.strip()}

    try:
        response = httpx.get(request_url, params=params, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError("Could not reach the live Outlook proof route.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("The live Outlook proof route did not return JSON.") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"Outlook download-proof route failed: status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError("The live Outlook proof route did not return an object.")

    return payload


def fetch_jobadder_job_applications_preview_from_live(
    *,
    api_base_url: str,
    jobadder_account: int,
    job_id: int,
    item_limit: int,
) -> dict[str, Any]:
    """
    Fetch one job-specific JobAdder applications preview from the live backend.

    Example
    -------
    A successful payload looks like:

        {
            "job_id": 891841,
            "item_count": 10,
            "total_count": 28,
            "applications": [...],
        }
    """

    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}"
        f"/jobs/{job_id}/applications-preview"
    )
    request_url = api_base_url.rstrip("/") + route_path
    params = {"item_limit": item_limit}

    try:
        response = httpx.get(request_url, params=params, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not reach the live JobAdder job-applications route."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The live JobAdder job-applications route did not return JSON."
        ) from exc

    if response.status_code >= 400:
        raise RuntimeError(
            "JobAdder job-applications route failed: "
            f"status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "The live JobAdder job-applications route did not return an object."
        )

    return payload


def extract_candidate_id_from_application(application: dict[str, Any]) -> int | None:
    """
    Extract the candidate identifier from one JobAdder application payload.

    Example
    -------
    A payload such as:

        {"candidate": {"candidateId": 17071060}}

    returns:

        17071060
    """

    raw_candidate = application.get("candidate")
    if isinstance(raw_candidate, dict):
        raw_candidate_id = raw_candidate.get("candidateId")
        try:
            candidate_id = int(raw_candidate_id)
        except (TypeError, ValueError):
            return None
        return candidate_id if candidate_id > 0 else None

    raw_candidate_id = application.get("candidateId")
    try:
        candidate_id = int(raw_candidate_id)
    except (TypeError, ValueError):
        return None
    return candidate_id if candidate_id > 0 else None


def fetch_jobadder_candidate_attachments_from_live(
    *,
    api_base_url: str,
    jobadder_account: int,
    candidate_id: int,
) -> dict[str, Any]:
    """
    Fetch one candidate-attachments preview from the live backend.

    Example
    -------
    A successful payload looks like:

        {
            "candidate_id": 17071060,
            "attachment_count": 1,
            "attachments": [...],
        }
    """
    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}"
        f"/candidates/{candidate_id}/attachments-preview"
    )
    request_url = api_base_url.rstrip("/") + route_path

    try:
        response = httpx.get(request_url, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not reach the live JobAdder candidate-attachments route."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The live JobAdder candidate-attachments route did not return JSON."
        ) from exc

    if response.status_code >= 400:
        raise RuntimeError(
            "JobAdder candidate-attachments route failed: "
            f"status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "The live JobAdder candidate-attachments route did not return an object."
        )

    return payload


def fetch_jobadder_candidate_attachment_proof_from_live(
    *,
    api_base_url: str,
    jobadder_account: int,
    candidate_id: int,
    attachment_id: int,
) -> dict[str, Any]:
    """
    Fetch one JobAdder candidate-attachment proof payload from the live backend.

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

    route_path = (
        f"/api/v1/integrations/jobadder/accounts/{jobadder_account}"
        f"/candidates/{candidate_id}/attachments/{attachment_id}/download-proof"
    )
    request_url = api_base_url.rstrip("/") + route_path

    try:
        response = httpx.get(request_url, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not reach the live JobAdder candidate-attachment proof route."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The live JobAdder candidate-attachment proof route did not return JSON."
        ) from exc

    if response.status_code >= 400:
        raise RuntimeError(
            "JobAdder candidate-attachment proof route failed: "
            f"status={response.status_code}, payload={payload}"
        )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "The live JobAdder candidate-attachment proof route did not return an object."
        )

    return payload


def run_reconciliation_check(
    *,
    api_base_url: str,
    microsoft_user_id: str,
    mailbox: str | None,
    message_id: str,
    attachment_id: str,
    jobadder_account: int,
    job_id: int,
    application_limit: int,
) -> dict[str, Any]:
    """
    Run one conservative Outlook-vs-JobAdder reconciliation pass.

    Returns
    -------
    dict[str, Any]
        Operator-facing report describing the exact-match outcome.

    Notes
    -----
    The matching rule is intentionally strict:

    - first resolve the specific JobAdder applications for the known job
    - then compare candidate-attachment hashes one by one
    - only return `matched` when the file hash is identical

    That keeps this first reconciliation slice safe. It refuses to invent a
    candidate link when the evidence is weaker than a byte-identical file.

    Example
    -------
    A successful match report contains:

        report["status"] == "matched"
        report["matched_candidate_id"] == 17071060

    An unresolved run contains:

        report["status"] == "unresolved"
        report["match_count"] == 0
    """

    outlook_proof = fetch_outlook_attachment_proof(
        api_base_url=api_base_url,
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        message_id=message_id,
        attachment_id=attachment_id,
    )

    applications_preview = fetch_jobadder_job_applications_preview_from_live(
        api_base_url=api_base_url,
        jobadder_account=jobadder_account,
        job_id=job_id,
        item_limit=application_limit,
    )
    application_items = applications_preview.get("applications", [])
    if not isinstance(application_items, list):
        raise RuntimeError(
            "The live JobAdder job-applications route did not return an applications list."
        )

    exact_matches: list[dict[str, Any]] = []
    inspected_candidates: list[dict[str, Any]] = []

    # Walk application by application so the report can explain exactly which
    # candidate attachments were considered before the script concluded
    # "matched" or "unresolved".
    for application in application_items:
        application_id = application.get("applicationId")
        candidate_id = extract_candidate_id_from_application(application)

        if candidate_id is None:
            inspected_candidates.append(
                {
                    "application_id": application_id,
                    "candidate_id": None,
                    "reason": "missing_candidate_id",
                }
            )
            continue

        try:
            attachments_result = fetch_jobadder_candidate_attachments_from_live(
                api_base_url=api_base_url,
                jobadder_account=jobadder_account,
                candidate_id=candidate_id,
            )
        except RuntimeError as exc:
            inspected_candidates.append(
                {
                    "application_id": application_id,
                    "candidate_id": candidate_id,
                    "reason": "candidate_attachments_read_failed",
                    "message": str(exc),
                }
            )
            continue

        attachment_summaries: list[dict[str, Any]] = []
        attachment_items = attachments_result.get("attachments", [])
        if not isinstance(attachment_items, list):
            inspected_candidates.append(
                {
                    "application_id": application_id,
                    "candidate_id": candidate_id,
                    "reason": "attachments_payload_missing_list",
                }
            )
            continue

        # Compare attachment by attachment so we only produce a positive match
        # when one concrete JobAdder file is byte-identical to the Outlook
        # advert-response attachment.
        for attachment in attachment_items:
            raw_attachment_id = attachment.get("attachmentId")
            try:
                candidate_attachment_id = int(raw_attachment_id)
            except (TypeError, ValueError):
                attachment_summaries.append(
                    {
                        "attachment_id": raw_attachment_id,
                        "file_name": attachment.get("name"),
                        "reason": "invalid_attachment_id",
                    }
                )
                continue

            try:
                jobadder_proof = fetch_jobadder_candidate_attachment_proof_from_live(
                    api_base_url=api_base_url,
                    jobadder_account=jobadder_account,
                    candidate_id=candidate_id,
                    attachment_id=candidate_attachment_id,
                )
            except RuntimeError as exc:
                attachment_summaries.append(
                    {
                        "attachment_id": candidate_attachment_id,
                        "file_name": attachment.get("name"),
                        "reason": "attachment_download_failed",
                        "message": str(exc),
                    }
                )
                continue

            sha256_match = jobadder_proof["sha256"] == outlook_proof["sha256"]
            file_name_match = jobadder_proof["file_name"] == outlook_proof["file_name"]

            attachment_summary = {
                "attachment_id": candidate_attachment_id,
                "file_name": jobadder_proof["file_name"],
                "sha256": jobadder_proof["sha256"],
                "sha256_match": sha256_match,
                "file_name_match": file_name_match,
            }
            attachment_summaries.append(attachment_summary)

            if sha256_match:
                exact_matches.append(
                    {
                        "application_id": application_id,
                        "candidate_id": candidate_id,
                        "candidate_name": application.get("candidate", {}).get("fullName")
                        if isinstance(application.get("candidate"), dict)
                        else None,
                        "jobadder_attachment": jobadder_proof,
                    }
                )

        inspected_candidates.append(
            {
                "application_id": application_id,
                "candidate_id": candidate_id,
                "candidate_name": application.get("candidate", {}).get("fullName")
                if isinstance(application.get("candidate"), dict)
                else None,
                "attachment_count": attachments_result["attachment_count"],
                "attachment_summaries": attachment_summaries,
            }
        )

    status_value = "matched" if exact_matches else "unresolved"

    return {
        "status": status_value,
        "jobadder_account": jobadder_account,
        "job_id": job_id,
        "application_limit": application_limit,
        "outlook_attachment": outlook_proof,
        "jobadder_applications_scanned": applications_preview["item_count"],
        "jobadder_total_applications": applications_preview["total_count"],
        "match_count": len(exact_matches),
        "exact_matches": exact_matches,
        "inspected_candidates": inspected_candidates,
    }


def main() -> int:
    """
    Run the Outlook-vs-JobAdder reconciliation check.

    Example
    -------
    Running:

        uv run python scripts/check_outlook_jobadder_reconciliation.py ^
            --output-json temp\\outlook_tw394_reconciliation_check.json

    writes a report that says either:

    - `matched`
    - or `unresolved`
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    report = run_reconciliation_check(
        api_base_url=args.api_base_url,
        microsoft_user_id=args.microsoft_user_id,
        mailbox=args.mailbox,
        message_id=args.message_id,
        attachment_id=args.attachment_id,
        jobadder_account=args.jobadder_account,
        job_id=args.job_id,
        application_limit=args.application_limit,
    )

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        print(f"[info] Wrote JSON report to {args.output_json}")

    print("Outlook vs JobAdder reconciliation completed.\n")
    print(f"status: {report['status']}")
    print(f"job_id: {report['job_id']}")
    print(f"jobadder_applications_scanned: {report['jobadder_applications_scanned']}")
    print(f"jobadder_total_applications: {report['jobadder_total_applications']}")
    print(f"match_count: {report['match_count']}")
    print(f"outlook_file_name: {report['outlook_attachment'].get('file_name')}")
    print(f"outlook_sha256: {report['outlook_attachment'].get('sha256')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
