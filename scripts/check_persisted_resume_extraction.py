"""
Inspect and verify one persisted accepted resume-extraction write.

Why this script exists
----------------------
The live extraction runner can now persist accepted JobAdder CV outputs into
the canonical schema. The next operational need is to verify that those writes
landed correctly before bulk-loading more data.

This script provides a narrow operator-facing verification path for that job.

What this script does
---------------------
It can:

1. read a saved extraction JSON artifact containing `persistence_result`
2. verify the expected canonical rows and provenance links in Postgres
3. print a concise human-readable verification summary
4. optionally write the full verification report to JSON

What this script does not do
----------------------------
It does not:

- rerun extraction
- persist new data
- reconcile multiple source systems
- replace later reporting or dashboards

Examples
--------
Verify one persisted extraction result from a saved JSON artifact:

    uv run python scripts/check_persisted_resume_extraction.py ^
        --result-json temp\\resume_extraction_result_persisted.json

Verify and save the full report:

    uv run python scripts/check_persisted_resume_extraction.py ^
        --result-json temp\\resume_extraction_result_persisted.json ^
        --output-json temp\\resume_extraction_verification.json
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_extraction_verification import (
    ResumeExtractionPersistenceVerification,
    verify_persisted_resume_extraction_result,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the persistence verification script.

    Example
    -------
    A caller can verify a persisted run with:

        --result-json temp\\resume_extraction_result_persisted.json
    """

    parser = argparse.ArgumentParser(
        description=(
            "Verify one persisted accepted resume-extraction write against the "
            "canonical Supabase/Postgres schema."
        )
    )
    parser.add_argument(
        "--result-json",
        type=Path,
        required=True,
        help=(
            "Saved extraction-result JSON containing a top-level "
            "`persistence_result` payload."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the full verification report as JSON.",
    )
    parser.add_argument(
        "--print-full-json",
        action="store_true",
        help="Print the full verification report as JSON to stdout.",
    )
    return parser


def load_persistence_result_from_json(*, result_json_path: Path) -> dict[str, Any]:
    """
    Load `persistence_result` from one saved extraction JSON artifact.

    Notes
    -----
    The verification flow intentionally consumes the same operator-facing JSON
    artifact produced by the live extraction script. That keeps the workflow
    concrete:

    - persist one accepted result
    - inspect that exact persisted result

    Example
    -------
    A saved extraction artifact with:

        {
            "persistence_result": {
                "candidate_id": "...",
                "person_id": "...",
            }
        }

    lets this helper return the embedded `persistence_result` dictionary
    directly.
    """

    payload = json.loads(result_json_path.read_text(encoding="utf-8"))
    persistence_result = payload.get("persistence_result")
    if not isinstance(persistence_result, dict):
        raise RuntimeError(
            "The supplied result JSON does not contain a top-level "
            "`persistence_result` dictionary."
        )
    return persistence_result


def build_console_summary(
    *,
    result_json_path: Path,
    report: ResumeExtractionPersistenceVerification,
) -> str:
    """
    Build a concise human-readable verification summary.

    Example
    -------
    The summary includes:

        Verification passed: yes
        Passed checks: 12
        Failed checks: 0
    """

    failed_checks = [check for check in report.checks if not check.passed]
    lines = [
        "Persistence verification completed.",
        "",
        f"Result JSON: {result_json_path}",
        f"Verification passed: {'yes' if report.verification_passed else 'no'}",
        f"Passed checks: {report.passed_check_count}",
        f"Failed checks: {report.failed_check_count}",
        f"Candidate ID: {report.expected.get('candidate_id')}",
        f"Person ID: {report.expected.get('person_id')}",
        f"Document ID: {report.expected.get('document_id')}",
    ]

    if failed_checks:
        first_failed_check = failed_checks[0]
        lines.extend(
            [
                "",
                f"First failed check: {first_failed_check.name}",
                f"Failure details: {first_failed_check.details}",
            ]
        )

    return "\n".join(lines)


def write_json_output(*, payload: dict[str, Any], output_path: Path) -> None:
    """
    Write one JSON payload to disk with parent-directory creation.

    Example
    -------
    A call with:

        output_path=Path(\"temp/report.json\")

    creates the parent folder if needed and writes the report in UTF-8 JSON.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """
    Run the persistence-verification CLI entrypoint.

    Example
    -------
    Running the module directly executes:

        raise SystemExit(main())
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        persistence_result = load_persistence_result_from_json(
            result_json_path=args.result_json,
        )
        report = verify_persisted_resume_extraction_result(
            persistence_result=persistence_result,
        )
        print(
            build_console_summary(
                result_json_path=args.result_json,
                report=report,
            )
        )

        report_payload = report.model_dump()

        if args.output_json is not None:
            write_json_output(payload=report_payload, output_path=args.output_json)
            print("")
            print(f"Wrote verification JSON to: {args.output_json}")

        if args.print_full_json:
            print("")
            print(json.dumps(report_payload, indent=2, ensure_ascii=False))

        return 0 if report.verification_passed else 1

    except RuntimeError as exc:
        print("Persistence verification failed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print("Persistence verification failed unexpectedly.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
