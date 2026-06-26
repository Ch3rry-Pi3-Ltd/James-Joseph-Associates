"""
Run rolling Outlook Inbox CV-export windows against the protected production route.

This script exists for one operational purpose:

    "Walk backwards through Outlook Inbox by received date, in bounded windows,
    and export only CV-like attachments into the Outlook Dropbox archive."

Notes
-----
- It calls the existing protected backend route instead of duplicating the
  mailbox/export logic locally.
- It uses date windows so runs are resumable and auditable.
- It can operate in `--dry-run` mode first, then be rerun without that flag
  once the window behavior looks correct.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, time as dt_time, timedelta
from typing import Any

DEFAULT_API_BASE_URL = "https://james-joseph-associates.vercel.app"
DEFAULT_MICROSOFT_USER_ID = "b4dd6a5f-8e27-4745-9369-e117121382ed"
DEFAULT_DROPBOX_ACCOUNT_ID = "dbid:AAD6tG3lvKRz-MJoBoYeedYkauD7t5D4IB0"
DEFAULT_DROPBOX_EXPORT_FOLDER = "/+++ Outlook CV Export"


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for rolling Outlook Inbox export windows.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Run rolling Outlook Inbox CV-export windows against the protected "
            "backend route."
        )
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Backend base URL hosting the protected Outlook export route.",
    )
    parser.add_argument(
        "--microsoft-user-id",
        default=DEFAULT_MICROSOFT_USER_ID,
        help="Microsoft user identifier used by the protected route.",
    )
    parser.add_argument(
        "--folder-segment",
        action="append",
        dest="folder_segments",
        default=None,
        help=(
            "One Outlook folder path segment. Repeat for deeper paths. "
            "Defaults to Inbox."
        ),
    )
    parser.add_argument(
        "--mailbox",
        default=None,
        help="Optional delegated mailbox identifier.",
    )
    parser.add_argument(
        "--anchor-end-date",
        default=None,
        help=(
            "UTC date in YYYY-MM-DD format for the newest window end. "
            "Defaults to today in UTC."
        ),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Number of whole UTC calendar days per window.",
    )
    parser.add_argument(
        "--window-count",
        type=int,
        default=1,
        help="How many consecutive backwards windows to run.",
    )
    parser.add_argument(
        "--message-limit",
        type=int,
        default=100,
        help="Per-page Outlook message batch size while scanning the full window.",
    )
    parser.add_argument(
        "--attachment-limit",
        type=int,
        default=100,
        help="Maximum supported attachments to process per window.",
    )
    parser.add_argument(
        "--dropbox-account-id",
        default=DEFAULT_DROPBOX_ACCOUNT_ID,
        help="Dropbox account identifier passed to the protected route.",
    )
    parser.add_argument(
        "--dropbox-export-folder",
        default=DEFAULT_DROPBOX_EXPORT_FOLDER,
        help="Dropbox base folder that receives exported Outlook CV files.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between windows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify attachments but do not upload any files to Dropbox.",
    )
    return parser


def load_local_env() -> dict[str, str]:
    """
    Load a small `.env.local` key-value mapping for local operator scripts.
    """

    env: dict[str, str] = {}
    env_path = pathlib.Path(".env.local")
    if not env_path.exists():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key.strip()] = value
    return env


def load_admin_token() -> str:
    """
    Load the bearer token expected by protected admin routes.
    """

    env = load_local_env()
    admin_token = (
        env.get("ADMIN_API_TOKEN")
        or env.get("INTERNAL_ADMIN_API_TOKEN")
        or env.get("MAKE_API_TOKEN")
    )
    if not admin_token:
        raise RuntimeError("No admin token found in .env.local")
    return admin_token


def parse_anchor_end_date(value: str | None) -> date:
    """
    Parse the newest UTC anchor date for rolling windows.
    """

    if value is None:
        return datetime.now(UTC).date()
    return date.fromisoformat(value)


def compute_window_bounds(
    *,
    anchor_end_date: date,
    window_days: int,
    window_index: int,
) -> tuple[datetime, datetime]:
    """
    Compute one backwards UTC date window as inclusive day bounds.
    """

    if window_days <= 0:
        raise ValueError("window_days must be positive.")

    newest_end_date = anchor_end_date - timedelta(days=window_index * window_days)
    oldest_start_date = newest_end_date - timedelta(days=window_days - 1)
    start_datetime = datetime.combine(oldest_start_date, dt_time.min, tzinfo=UTC)
    end_datetime = datetime.combine(newest_end_date, dt_time.max, tzinfo=UTC)
    return start_datetime, end_datetime


def format_iso8601_utc(value: datetime) -> str:
    """
    Format one UTC datetime as an API-safe ISO timestamp.
    """

    normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def call_export_route(
    *,
    api_base_url: str,
    admin_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Call the protected Outlook CV export route and return the parsed JSON body.
    """

    base_url = api_base_url.rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/api/v1/integrations/outlook/admin/export-cv-attachments",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            response_text = response.read().decode("utf-8")
            return json.loads(response_text)
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8")
        raise RuntimeError(
            f"Protected export route failed with HTTP {exc.code}: {response_text}"
        ) from exc


def print_window_summary(
    *,
    window_index: int,
    received_from: str,
    received_to: str,
    export_report: dict[str, Any],
) -> None:
    """
    Print one concise operator-facing summary for a completed window.
    """

    print(
        json.dumps(
            {
                "window_index": window_index,
                "received_from": received_from,
                "received_to": received_to,
                "message_count_scanned": export_report.get("message_count_scanned"),
                "messages_with_attachments": export_report.get(
                    "messages_with_attachments"
                ),
                "supported_attachment_count": export_report.get(
                    "supported_attachment_count"
                ),
                "detected_resume_count": export_report.get("detected_resume_count"),
                "exported_count": export_report.get("exported_count"),
                "non_resume_count": export_report.get("non_resume_count"),
                "failed_count": export_report.get("failed_count"),
            }
        )
    )


def main() -> None:
    """
    Run one or more backwards Outlook Inbox export windows.
    """

    parser = build_argument_parser()
    args = parser.parse_args()

    if args.window_days <= 0:
        raise SystemExit("--window-days must be positive.")
    if args.window_count <= 0:
        raise SystemExit("--window-count must be positive.")

    folder_segments = args.folder_segments or ["Inbox"]
    anchor_end_date = parse_anchor_end_date(args.anchor_end_date)
    admin_token = load_admin_token()

    totals = {
        "windows_run": 0,
        "message_count_scanned": 0,
        "messages_with_attachments": 0,
        "supported_attachment_count": 0,
        "detected_resume_count": 0,
        "exported_count": 0,
        "non_resume_count": 0,
        "failed_count": 0,
    }

    for window_index in range(args.window_count):
        received_from_dt, received_to_dt = compute_window_bounds(
            anchor_end_date=anchor_end_date,
            window_days=args.window_days,
            window_index=window_index,
        )
        received_from = format_iso8601_utc(received_from_dt)
        received_to = format_iso8601_utc(received_to_dt)

        payload = {
            "microsoft_user_id": args.microsoft_user_id,
            "folder_segments": folder_segments,
            "mailbox": args.mailbox,
            "message_limit": args.message_limit,
            "attachment_limit": args.attachment_limit,
            "received_from": received_from,
            "received_to": received_to,
            "dropbox_account_id": args.dropbox_account_id,
            "dropbox_export_folder": args.dropbox_export_folder,
            "dry_run": args.dry_run,
        }

        response_payload = call_export_route(
            api_base_url=args.api_base_url,
            admin_token=admin_token,
            payload=payload,
        )
        export_report = response_payload.get("export_report", {})
        print_window_summary(
            window_index=window_index,
            received_from=received_from,
            received_to=received_to,
            export_report=export_report,
        )

        totals["windows_run"] += 1
        for key in (
            "message_count_scanned",
            "messages_with_attachments",
            "supported_attachment_count",
            "detected_resume_count",
            "exported_count",
            "non_resume_count",
            "failed_count",
        ):
            value = export_report.get(key)
            if isinstance(value, int):
                totals[key] += value

        if args.pause_seconds > 0 and window_index < args.window_count - 1:
            time.sleep(args.pause_seconds)

    print(json.dumps({"totals": totals}))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
