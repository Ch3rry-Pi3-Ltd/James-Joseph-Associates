"""
List candidate records from JobAdder and export candidate IDs for inspection.

Why this script exists
----------------------
The batch extraction runner needs candidate IDs, but operators often do not
have a ready-made list of those IDs on hand.

The backend already has:

- stored JobAdder OAuth connections
- token-refresh helpers
- authenticated candidate-list API reads

The missing operational step is:

    "Can we quickly fetch a list of candidate IDs and basic metadata for one
    connected JobAdder account?"

This script answers that question.

What this script does
---------------------
It performs the following steps:

1. load the stored JobAdder OAuth connection for one account
2. refresh the access token if it is already expired
3. fetch candidate pages from JobAdder
4. follow `links.next` when present
5. trim the final result to an optional limit
6. optionally write CSV and/or JSON outputs
7. print a concise summary or an ID-only list

What this script does not do
----------------------------
It does not:

- run CV extraction
- call any LLM
- write to Supabase
- build a full candidate sync

This script is purely for candidate discovery and operator convenience.

Examples
--------
Print a quick first 20 candidate IDs:

    uv run python scripts/list_jobadder_candidates.py ^
        --jobadder-account 2236 ^
        --limit 20 ^
        --print-ids-only

Write a richer CSV and JSON export:

    uv run python scripts/list_jobadder_candidates.py ^
        --jobadder-account 2236 ^
        --limit 200 ^
        --output-csv temp\\jobadder_candidates.csv ^
        --output-json temp\\jobadder_candidates.json

In plain language:

- connect to the stored JobAdder account
- read candidate pages safely
- give the operator a usable list of candidate IDs and basic metadata
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.jobadder_oauth import get_jobadder_oauth_connection, save_jobadder_oauth_connection
from backend.services.jobadder_api import (
    JobAdderApiError,
    fetch_jobadder_candidates_page,
)
from backend.services.jobadder_oauth import (
    JobAdderOAuthExchangeError,
    is_jobadder_access_token_expired,
    refresh_jobadder_access_token,
)
from backend.settings import get_settings


DEFAULT_CANDIDATE_LIST_CSV_PATH = Path("temp/jobadder_candidates.csv")
DEFAULT_CANDIDATE_LIST_JSON_PATH = Path("temp/jobadder_candidates.json")


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the JobAdder candidate-list script.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser for JobAdder candidate-list runs.

    Notes
    -----
    This script is meant to be operator-friendly rather than framework-like,
    so the arguments stay explicit and narrowly scoped to:

    - one JobAdder account
    - one optional candidate limit
    - a small set of export/printing choices

    Example
    -------
    A caller can ask for a small preview:

        --jobadder-account 2236 --limit 20 --print-ids-only

    or a richer export:

        --jobadder-account 2236 --limit 200 --output-csv temp\\candidates.csv
    """

    parser = argparse.ArgumentParser(
        description=(
            "List candidates from one connected JobAdder account and export "
            "candidate IDs plus basic metadata."
        )
    )
    parser.add_argument(
        "--jobadder-account",
        type=int,
        required=True,
        help="JobAdder account identifier used to load the stored OAuth connection.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of candidates to collect before stopping.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Requested provider page size for each JobAdder list read.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional CSV output path. Defaults to no CSV unless explicitly requested.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to no JSON unless explicitly requested.",
    )
    parser.add_argument(
        "--write-default-outputs",
        action="store_true",
        help=(
            "Write both the default CSV and JSON outputs under temp/ even when "
            "explicit paths are not provided."
        ),
    )
    parser.add_argument(
        "--print-ids-only",
        action="store_true",
        help="Print candidate IDs only, one per line.",
    )
    return parser


def validate_listing_arguments(args: argparse.Namespace) -> None:
    """
    Validate the high-signal local arguments for candidate listing.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments for the current listing run.

    Notes
    -----
    These are cheap local checks that should fail before any provider work
    starts.

    Example
    -------
    This helper rejects clearly invalid states such as:

    - `--jobadder-account 0`
    - `--limit 0`
    - missing local JobAdder OAuth settings
    """

    if args.jobadder_account < 1:
        raise RuntimeError("JOBADDER_ACCOUNT must be at least 1.")

    if args.limit < 1:
        raise RuntimeError("LIMIT must be at least 1.")

    if args.page_size < 1:
        raise RuntimeError("PAGE_SIZE must be at least 1.")

    settings = get_settings()
    missing_settings: list[str] = []

    if settings.jobadder_client_id.strip() == "":
        missing_settings.append("JOBADDER_CLIENT_ID")
    if settings.jobadder_client_secret.strip() == "":
        missing_settings.append("JOBADDER_CLIENT_SECRET")
    if settings.jobadder_redirect_uri.strip() == "":
        missing_settings.append("JOBADDER_REDIRECT_URI")

    if missing_settings:
        raise RuntimeError(
            "The local JobAdder OAuth configuration is incomplete. Missing: "
            + ", ".join(missing_settings)
        )


def load_or_refresh_jobadder_connection(*, jobadder_account: int) -> dict[str, object]:
    """
    Load the stored JobAdder OAuth connection and refresh it if already expired.

    Parameters
    ----------
    jobadder_account : int
        Connected JobAdder account identifier whose stored OAuth row should be
        used for candidate-list reads.

    Returns
    -------
    dict[str, object]
        Usable stored connection row containing at least:

        - `access_token`
        - `refresh_token`
        - `api_url`
        - `jobadder_account`

    Notes
    -----
    This helper deliberately mirrors the same operational logic the ingest path
    already depends on:

    - load the stored connection
    - fail clearly if it does not exist
    - refresh once up front when the token is obviously expired

    Example
    -------
    A successful call returns a plain connection row that still contains the
    access token, API URL, and JobAdder account metadata needed for list reads.
    """

    stored_connection = get_jobadder_oauth_connection(jobadder_account)
    if stored_connection is None:
        raise RuntimeError(
            "No stored JobAdder OAuth connection exists for this account."
        )

    refresh_token_value = stored_connection.get("refresh_token")
    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        raise RuntimeError(
            "The stored JobAdder connection does not contain a usable refresh token."
        )

    if is_jobadder_access_token_expired(
        obtained_at=stored_connection.get("obtained_at"),
        expires_in_seconds=stored_connection.get("expires_in_seconds"),
    ):
        refreshed_token_set = refresh_jobadder_access_token(
            refresh_token=refresh_token_value,
        )
        refreshed_connection = save_jobadder_oauth_connection(refreshed_token_set)
        return refreshed_connection

    return stored_connection


def fetch_jobadder_candidate_rows(
    *,
    connection_row: dict[str, object],
    limit: int,
    page_size: int,
) -> list[dict[str, Any]]:
    """
    Fetch and flatten candidate rows from JobAdder up to a requested limit.

    Parameters
    ----------
    connection_row : dict[str, object]
        Stored JobAdder OAuth connection row with access token and API URL.

    limit : int
        Maximum number of candidates to collect before stopping.

    page_size : int
        Requested provider page size per API read.

    Returns
    -------
    list[dict[str, Any]]
        Flat candidate-row dictionaries suitable for CSV/JSON export.

    Notes
    -----
    - The first request is built from the stored API base and explicit page
      params.
    - Subsequent requests follow `links.next` when JobAdder supplies it.
    - A 401 on a later page triggers one token refresh and a single retry.

    Example
    -------
    The returned rows look like:

        {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "mobile": "07934 890 708",
            "updatedAt": "2026-04-20T10:02:24Z",
        }
    """

    access_token = connection_row.get("access_token")
    api_url = connection_row.get("api_url")
    refresh_token_value = connection_row.get("refresh_token")

    if not isinstance(access_token, str) or access_token.strip() == "":
        raise RuntimeError(
            "The stored JobAdder connection does not contain a usable access token."
        )

    if not isinstance(api_url, str) or api_url.strip() == "":
        raise RuntimeError(
            "The stored JobAdder connection does not contain a usable API URL."
        )

    if not isinstance(refresh_token_value, str) or refresh_token_value.strip() == "":
        raise RuntimeError(
            "The stored JobAdder connection does not contain a usable refresh token."
        )

    collected_rows: list[dict[str, Any]] = []
    next_page_url: str | None = None
    current_page = 1
    current_access_token = access_token

    while len(collected_rows) < limit:
        try:
            page_result = fetch_jobadder_candidates_page(
                api_url=api_url,
                access_token=current_access_token,
                page=current_page,
                page_size=page_size,
                page_url=next_page_url,
            )
        except JobAdderApiError as exc:
            # Handle one narrow operational recovery path here:
            # if a later page hits a 401, refresh the token once and retry the
            # same page immediately. Other statuses are treated as real failures.
            if exc.status_code != 401:
                raise

            refreshed_token_set = refresh_jobadder_access_token(
                refresh_token=refresh_token_value,
            )
            refreshed_connection = save_jobadder_oauth_connection(refreshed_token_set)

            refreshed_access_token = refreshed_connection.get("access_token")
            if not isinstance(refreshed_access_token, str) or refreshed_access_token.strip() == "":
                raise RuntimeError(
                    "The refreshed JobAdder connection did not return a usable access token."
                ) from exc

            current_access_token = refreshed_access_token
            page_result = fetch_jobadder_candidates_page(
                api_url=api_url,
                access_token=current_access_token,
                page=current_page,
                page_size=page_size,
                page_url=next_page_url,
            )

        items = page_result.get("items", [])

        # Flatten only the operator-relevant fields here. The goal is to make
        # the export easy to scan and easy to feed into the batch extraction
        # runner, not to mirror the full provider payload.
        for item in items:
            collected_rows.append(build_candidate_export_row(item))
            if len(collected_rows) >= limit:
                break

        # Prefer the provider-supplied `next` URL over locally reconstructing
        # later pages.
        #
        # That is the safer pagination strategy here because:
        # - it follows the provider's own navigation contract
        # - it reduces assumptions about JobAdder's paging parameters
        # - it keeps the list script simpler and easier to explain
        links = page_result.get("links", {})
        next_page_candidate = links.get("next") if isinstance(links, dict) else None
        if not isinstance(next_page_candidate, str) or next_page_candidate.strip() == "":
            break

        next_page_url = next_page_candidate
        current_page += 1

    return collected_rows[:limit]


def build_candidate_export_row(candidate: dict[str, Any]) -> dict[str, Any]:
    """
    Build one flat export row from a raw JobAdder candidate item.

    Notes
    -----
    This helper intentionally keeps a small shape. For candidate-ID discovery
    we mainly care about:

    - stable identifier
    - human-readable name
    - contact hints
    - freshness hint via `updatedAt`

    Example
    -------
    A raw JobAdder candidate item becomes a flatter row such as:

        {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "updatedAt": "2026-04-20T10:02:24Z",
            "status": "Active",
        }
    """

    return {
        "candidateId": candidate.get("candidateId"),
        "firstName": candidate.get("firstName"),
        "lastName": candidate.get("lastName"),
        "email": candidate.get("email"),
        "mobile": candidate.get("mobile"),
        "location": candidate.get("location"),
        "updatedAt": candidate.get("updatedAt"),
        "createdAt": candidate.get("createdAt"),
        "status": candidate.get("status", {}).get("name")
        if isinstance(candidate.get("status"), dict)
        else candidate.get("status"),
    }


def write_candidate_rows_csv(*, rows: list[dict[str, Any]], output_path: Path) -> None:
    """
    Write flat candidate rows to CSV.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Flat candidate export rows.

    output_path : Path
        Destination CSV path.

    Notes
    -----
    The CSV shape is intentionally fixed and narrow so operators can:

    - sort/filter it quickly
    - paste IDs into later workflows
    - compare candidate freshness by `updatedAt`
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "candidateId",
        "firstName",
        "lastName",
        "email",
        "mobile",
        "location",
        "updatedAt",
        "createdAt",
        "status",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_candidate_rows_json(*, rows: list[dict[str, Any]], output_path: Path) -> None:
    """
    Write flat candidate rows to JSON.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Flat candidate export rows.

    output_path : Path
        Destination JSON path.

    Notes
    -----
    JSON is useful here because it preserves the field names cleanly for later
    scripting or ad hoc analysis without requiring CSV parsing.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_candidate_rows(*, rows: list[dict[str, Any]], ids_only: bool) -> None:
    """
    Print either candidate IDs only or a concise preview table to stdout.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Flat candidate export rows.

    ids_only : bool
        When `True`, print just the candidate IDs, one per line.

    Notes
    -----
    - `ids_only` is for piping candidate IDs into later tools or temporary
      files.
    - the preview mode is for quick human inspection without immediately
      opening the exported CSV/JSON.
    """

    if ids_only:
        for row in rows:
            print(row.get("candidateId"))
        return

    print("JobAdder candidate listing completed.")
    print("")
    print(f"Candidate count: {len(rows)}")
    print("")

    for row in rows[:20]:
        print(
            f"{row.get('candidateId')} | "
            f"{row.get('firstName')} {row.get('lastName')} | "
            f"{row.get('email') or '(no email)'} | "
            f"{row.get('updatedAt') or '(no updatedAt)'}"
        )


def main(argv: list[str] | None = None) -> int:
    """
    Run the JobAdder candidate-list CLI entrypoint.

    Parameters
    ----------
    argv : list[str] | None
        Optional argument list. When omitted, `argparse` reads from
        `sys.argv`.

    Returns
    -------
    int
        Process exit code.

        - `0` for success
        - `1` for expected runtime/provider failures
        - `2` for unexpected top-level failures

    Notes
    -----
    This CLI is intentionally small and operator-oriented:

    - validate local config
    - load or refresh the JobAdder connection
    - fetch a bounded candidate list
    - optionally export it
    - print a usable console result

    Example
    -------
    Running the module directly executes:

        raise SystemExit(main())

    which gives the script a normal shell exit code.
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        validate_listing_arguments(args)
        connection_row = load_or_refresh_jobadder_connection(
            jobadder_account=args.jobadder_account,
        )
        rows = fetch_jobadder_candidate_rows(
            connection_row=connection_row,
            limit=args.limit,
            page_size=args.page_size,
        )

        # Keep the "should we write files?" decision separate from the
        # underlying fetch logic.
        #
        # That makes the script easier to reason about because export policy is
        # now entirely an operator concern:
        # - explicit output paths win
        # - otherwise the operator can opt into the default temp outputs
        output_csv = args.output_csv
        output_json = args.output_json

        if args.write_default_outputs:
            output_csv = output_csv or DEFAULT_CANDIDATE_LIST_CSV_PATH
            output_json = output_json or DEFAULT_CANDIDATE_LIST_JSON_PATH

        if output_csv is not None:
            write_candidate_rows_csv(rows=rows, output_path=output_csv)
            print(f"Wrote CSV output to: {output_csv}")

        if output_json is not None:
            write_candidate_rows_json(rows=rows, output_path=output_json)
            print(f"Wrote JSON output to: {output_json}")

        print_candidate_rows(rows=rows, ids_only=args.print_ids_only)
        return 0

    except (
        RuntimeError,
        JobAdderApiError,
        JobAdderOAuthExchangeError,
    ) as exc:
        print("JobAdder candidate listing failed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    except Exception as exc:
        print("JobAdder candidate listing failed unexpectedly.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
